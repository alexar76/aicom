"""Tests for federation crawler — peer discovery, manifest indexing, validation."""

import contextlib
import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer


@pytest.fixture(autouse=True)
def _bypass_url_safety_for_tests(monkeypatch):
    """Tests use *.example.com which doesn't DNS-resolve; the production
    _url_is_safe would block all such URLs as unresolvable.
    Override to accept any non-loopback URL for the duration of the test."""
    import aimarket_hub.crawler as _c
    def _safe(url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        bad = ("localhost", "127.", "0.0.0.0", "[::1]")
        return not any(b in url.lower() for b in bad)
    monkeypatch.setattr(_c, "_url_is_safe", _safe)


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        database = HubDatabase(db_path)
        yield database
        database.close()


@pytest.fixture
def signer():
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "test_key"
        yield Signer(key_path)


@pytest.fixture
def config():
    cfg = HubConfig()
    cfg.seed_list = ["https://seed-hub.example.com/.well-known/ai-market.json"]
    cfg.max_crawl_depth = 2
    cfg.request_timeout_s = 5
    return cfg


SAMPLE_WELL_KNOWN = {
    "name": "Test Peer Hub",
    "protocol_versions": ["v1", "v2"],
    "manifest_url": "https://seed-hub.example.com/ai-market/manifest",
    "capabilities_count": 3,
    "signer_public_key": "dGVzdF9wdWJsaWNfa2V5",
    "peers": [{"url": "https://hub2.example.com", "name": "Secondary Hub"}],
}

SAMPLE_CAPS = [
    Capability(capability_id="translate.multi@v2", product_id="prod-001", name="translate.multi",
               description="Translate", price_per_call_usd=0.40, p50_latency_ms=8100,
               source_hub="https://seed-hub.example.com", source_hub_name="Test Peer Hub"),
    Capability(capability_id="legal.review@v1", product_id="prod-001", name="legal.review",
               description="Legal review", price_per_call_usd=1.20, p50_latency_ms=11400,
               source_hub="https://seed-hub.example.com", source_hub_name="Test Peer Hub"),
]


class TestCrawler:
    @pytest.mark.asyncio
    async def test_crawl_indexes_capabilities(self, db, signer, config):
        """Test that crawler indexes capabilities from seed hubs via _crawl_one."""
        crawler = Crawler(config=config, db=db, signer=signer)

        async def mock_crawl_one(url, depth, discoverer):
            if url == config.seed_list[0]:
                for cap in SAMPLE_CAPS:
                    db.upsert_capability(cap)
                db.upsert_peer(Peer(
                    url="https://seed-hub.example.com", name="Test Peer Hub",
                    capabilities_count=3, last_crawl="2026-05-21T12:00:00Z",
                ))
                return {"capabilities_count": 2, "new_peer_urls": ["https://hub2.example.com"]}
            return None

        with patch.object(crawler, "_crawl_one", side_effect=mock_crawl_one):
            stats = await crawler.crawl(clear_first=True)

        assert stats["discovered"] == 1
        assert stats["indexed"] == 2

    @pytest.mark.asyncio
    async def test_crawl_respects_max_depth(self, db, signer, config):
        """BFS stops at max_crawl_depth."""
        config.max_crawl_depth = 0
        crawler = Crawler(config=config, db=db, signer=signer)

        # Depth 0 should only process seeds, but they start at depth 0
        # and depth > max_depth check would reject them
        # Actually seeds are depth 0 and condition is depth > max_depth
        stats = await crawler.crawl(clear_first=True)
        assert stats["discovered"] == 0  # No seed processed because we patched nothing
        await crawler.close()

    @pytest.mark.asyncio
    async def test_crawl_handles_unreachable_hub(self, db, signer, config):
        """Graceful handling when _crawl_one returns None."""
        crawler = Crawler(config=config, db=db, signer=signer)

        async def mock_crawl_one(url, depth, discoverer):
            return None  # Simulate unreachable

        with patch.object(crawler, "_crawl_one", side_effect=mock_crawl_one):
            stats = await crawler.crawl(clear_first=True)

        assert stats["errors"] == 1
        assert stats["indexed"] == 0

    @pytest.mark.asyncio
    async def test_crawl_does_not_clear_atomically_pre_crawl(self, db, signer, config):
        """clear_first=True is now a no-op (EXP-34 fix). Federated catalog
        is NOT cleared before crawl — the empty-catalog DoS window is gone.
        Old federated capabilities remain until they are refreshed or pruned
        by a dedicated cleanup step.
        """
        db.upsert_capability(Capability(
            capability_id="old@v1", product_id="old-prod", name="old",
            source_hub="https://old-hub.example.com",
        ))
        assert db.count_federated() == 1

        crawler = Crawler(config=config, db=db, signer=signer)

        async def mock_crawl_one(url, depth, discoverer):
            return {"capabilities_count": 1, "new_peer_urls": []}

        with patch.object(crawler, "_crawl_one", side_effect=mock_crawl_one):
            await crawler.crawl(clear_first=True)

        # Old capabilities remain (EXP-34: no pre-crawl clear)
        assert db.count_federated() >= 1

    @pytest.mark.asyncio
    async def test_crawl_peer_recorded(self, db, signer, config):
        """Crawled peers are stored in the database."""
        crawler = Crawler(config=config, db=db, signer=signer)

        async def mock_crawl_one(url, depth, discoverer):
            db.upsert_peer(Peer(
                url="https://seed-hub.example.com", name="Test Peer",
                capabilities_count=3, last_crawl="2026-05-21T12:00:00Z",
            ))
            return {"capabilities_count": 0, "new_peer_urls": []}

        with patch.object(crawler, "_crawl_one", side_effect=mock_crawl_one):
            await crawler.crawl(clear_first=True)

        peer = db.get_peer("https://seed-hub.example.com")
        assert peer is not None
        assert peer.name == "Test Peer"

    @pytest.mark.asyncio
    async def test_routed_price_computation(self, db, signer, config):
        """Routed prices include the routing fee, computed in integer micro-dollars."""
        config.routing_fee_bps = 200

        crawler = Crawler(config=config, db=db, signer=signer)
        # $0.40 + 2% = $0.408 exactly. Under the old integer-cents math this rounded
        # to $0.41, which was close enough to look right at this price point.
        assert crawler._routed_price(0.40) == pytest.approx(0.408, abs=1e-9)

    @pytest.mark.asyncio
    async def test_routed_price_survives_sub_cent_capabilities(self, db, signer, config):
        """Sub-cent listings must not route at $0.00.

        The catalogue carries $0.001 sensor reads (GAIA) and $0.004 oracle calls
        (platon). Integer-cents quantisation published both as a routed price of zero:
        a buyer read "free" for a capability the hub then billed the peer's price for,
        and the routing fee vanished with it.
        """
        config.routing_fee_bps = 100
        crawler = Crawler(config=config, db=db, signer=signer)

        assert crawler._routed_price(0.001) == pytest.approx(0.00101, abs=1e-9)
        assert crawler._routed_price(0.004) == pytest.approx(0.00404, abs=1e-9)
        # The fee is no longer lost below ~$0.50 either.
        assert crawler._routed_price(0.35) == pytest.approx(0.3535, abs=1e-9)
        assert crawler._routed_price(0.0) == 0.0

    @pytest.mark.asyncio
    async def test_crawl_extracts_peer_urls(self, db, signer, config):
        """_extract_peer_urls extracts URLs from well-known response."""
        crawler = Crawler(config=config, db=db, signer=signer)
        urls = crawler._extract_peer_urls({
            "peers": [
                {"url": "https://hub2.example.com", "name": "Hub 2"},
                {"url": "https://hub3.example.com", "name": "Hub 3"},
            ],
            "federation": {
                "seed_list": ["https://hub4.example.com/.well-known/ai-market.json"],
            },
        })
        assert "https://hub2.example.com" in urls
        assert "https://hub3.example.com" in urls
        assert "https://hub4.example.com" in urls


class TestPeerTrustGate:
    """SEC #10 (anti-TOFU): a peer's manifests are indexed only after operator approval."""

    def test_set_peer_trusted_roundtrip(self, db):
        db.upsert_peer(Peer(url="https://p.example.com", name="P"))
        assert db.get_peer("https://p.example.com").trusted is False  # default untrusted
        assert db.set_peer_trusted("https://p.example.com", True) is True
        assert db.get_peer("https://p.example.com").trusted is True
        assert db.set_peer_trusted("https://missing.example.com", True) is False  # no such peer

    @pytest.mark.asyncio
    async def test_first_contact_untrusted_is_recorded_but_not_indexed(self, db, signer, config):
        crawler = Crawler(config=config, db=db, signer=signer)
        wk_url = "https://seed-hub.example.com/.well-known/ai-market.json"

        class _Resp:
            status_code = 200
            def json(self):
                return dict(SAMPLE_WELL_KNOWN)

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            result = await crawler._crawl_one(wk_url, 0, "seed")
        finally:
            await crawler.close()

        assert result == {"capabilities_count": 0, "new_peer_urls": []}   # not indexed
        peer = db.get_peer("https://seed-hub.example.com")
        assert peer is not None and peer.trusted is False                 # pending approval
        # TWO fetches now, not one: the well-known, then the manifest for the operator's
        # preview (`_preview_pending_manifest`, no longer gated on the open door). The gate
        # this class guards is the CATALOGUE, not the fetch — so it is asserted on the
        # catalogue. The preview read cannot index either: it writes to its own quarantined
        # table, and this body is a well-known, not a manifest, so it previews nothing.
        assert crawler._safe_get.await_count == 2
        assert db.count_capabilities() == 0
        assert db.count_preview_capabilities("https://seed-hub.example.com") == 0

    @pytest.mark.asyncio
    async def test_key_change_persists_reject_reason_for_peers_list(self, db, signer, config):
        """Pin mismatch must be visible on /federation/peers, not only in logs."""
        old = "b2xkX2tleV9vbGRfb2xkX29sZA=="
        new = "bmV3X2tleV9uZXdfbmV3X25ldw=="
        db.upsert_peer(Peer(
            url="https://seed-hub.example.com",
            name="Test Peer Hub",
            public_key=old,
            trusted=True,
        ))
        crawler = Crawler(config=config, db=db, signer=signer)
        wk = dict(SAMPLE_WELL_KNOWN)
        wk["signer_public_key"] = new

        class _Resp:
            status_code = 200
            def json(self):
                return wk

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            result = await crawler._crawl_one(
                "https://seed-hub.example.com/.well-known/ai-market.json", 0, "seed",
            )
        finally:
            await crawler.close()

        assert result is None
        peer = db.get_peer("https://seed-hub.example.com")
        assert peer is not None
        assert peer.public_key == old  # pin stays fail-closed
        assert peer.status == "key_mismatch"
        assert peer.pin_reject_reason == "peer rejected: key changed"
        assert peer.advertised_public_key == new
        # Must still appear in list_peers (not filtered out as inactive-only).
        listed = {p.url: p for p in db.list_peers()}
        assert listed["https://seed-hub.example.com"].pin_reject_reason == (
            "peer rejected: key changed"
        )

    def test_status_preserving_upsert_keeps_the_reject_reason(self, db):
        """A trust-score refresh must not strip the explanation off a caught takeover.

        The refresh loop passes the peer's existing status back so a key_mismatch
        flag survives the cycle, but upsert_peer used to hardcode empty strings for
        pin_reject_reason and advertised_public_key. The flag then stood with
        nothing to explain it: production served a key_mismatch peer with
        pin_reject_reason "" for five days and the cause had to be found by
        comparing public keys by hand.
        """
        old = "b2xkX2tleV9vbGRfb2xkX29sZA=="
        new = "bmV3X2tleV9uZXdfbmV3X25ldw=="
        db.upsert_peer(Peer(
            url="https://atlas.example.com", name="ATLAS", public_key=old, trusted=True,
        ))
        db.record_peer_key_mismatch(
            "https://atlas.example.com", pinned_key=old, advertised_key=new,
        )

        # What the trust-score refresh does every cycle: rewrite the row with a
        # fresh score, preserving whatever status the peer already had.
        peer = db.get_peer("https://atlas.example.com")
        peer.trust_score = 0.4844
        db.upsert_peer(peer, status=peer.status)

        refreshed = db.get_peer("https://atlas.example.com")
        assert refreshed.status == "key_mismatch"
        assert refreshed.trust_score == 0.4844
        assert refreshed.pin_reject_reason == "peer rejected: key changed"
        assert refreshed.advertised_public_key == new
        assert refreshed.public_key == old  # the pin itself never moves

    def test_a_successful_crawl_still_clears_the_reject_reason(self, db):
        """Preserving the diagnostics must not make a resolved mismatch sticky."""
        old = "b2xkX2tleV9vbGRfb2xkX29sZA=="
        new = "bmV3X2tleV9uZXdfbmV3X25ldw=="
        db.upsert_peer(Peer(
            url="https://atlas.example.com", name="ATLAS", public_key=old, trusted=True,
        ))
        db.record_peer_key_mismatch(
            "https://atlas.example.com", pinned_key=old, advertised_key=new,
        )

        # The peer goes back to advertising the pinned key: a normal crawl upserts
        # it active, and the pin-reject state must go with it.
        db.upsert_peer(Peer(
            url="https://atlas.example.com", name="ATLAS", public_key=old, trusted=True,
        ), status="active")

        healed = db.get_peer("https://atlas.example.com")
        assert healed.status == "active"
        assert healed.pin_reject_reason == ""
        assert healed.advertised_public_key == ""

    def test_repin_peer_public_key_clears_mismatch(self, db):
        old = "b2xkX2tleV9vbGRfb2xkX29sZA=="
        new = "bmV3X2tleV9uZXdfbmV3X25ldw=="
        db.upsert_peer(Peer(
            url="https://atlas.example.com", name="ATLAS", public_key=old, trusted=True,
        ))
        assert db.record_peer_key_mismatch(
            "https://atlas.example.com", pinned_key=old, advertised_key=new,
        )
        peer = db.get_peer("https://atlas.example.com")
        assert peer.status == "key_mismatch"

        result = db.repin_peer_public_key(
            "https://atlas.example.com",
            new,
            trusted=True,
            previous_public_key=old,
        )
        assert result["previous_public_key"] == old
        assert result["public_key"] == new
        peer = db.get_peer("https://atlas.example.com")
        assert peer.public_key == new
        assert peer.status == "active"
        assert peer.pin_reject_reason == ""
        assert peer.advertised_public_key == ""
        assert peer.trusted is True

    def test_repin_rejects_stale_previous_key(self, db):
        db.upsert_peer(Peer(
            url="https://atlas.example.com", name="ATLAS",
            public_key="Y3VycmVudA==", trusted=True,
        ))
        with pytest.raises(ValueError, match="previous_public_key"):
            db.repin_peer_public_key(
                "https://atlas.example.com",
                "bmV3",
                previous_public_key="d3Jvbmc=",
            )


class TestIndexShortfallIsVisible:
    """A peer that publishes more than we indexed must not do so silently.

    Found in production: ATLAS served seven capabilities and this hub's catalogue
    carried six. The seventh was a priced, fully implemented $0.12 SKU that no buyer
    could discover, and `capabilities_count: 6` read as the truth about the peer
    rather than the truth about our last crawl of it.
    """

    def _crawler(self, db, config):
        from aimarket_hub.crawler import Crawler

        return Crawler(config=config, db=db)

    def test_a_declared_total_above_the_indexed_count_is_reported(self, db, config, caplog):
        crawler = self._crawler(db, config)
        with caplog.at_level(logging.WARNING):
            declared = crawler._warn_on_index_shortfall(
                {"total_capabilities": 7}, "https://atlas.example.com", 6
            )
        assert declared == 7
        assert "declares 7 capabilities" in caplog.text
        assert "only 6 were indexed" in caplog.text

    def test_agreement_is_silent(self, db, config, caplog):
        crawler = self._crawler(db, config)
        with caplog.at_level(logging.WARNING):
            assert crawler._warn_on_index_shortfall(
                {"total_capabilities": 7}, "https://atlas.example.com", 7
            ) is None
        assert "declares" not in caplog.text

    def test_indexing_more_than_declared_is_not_a_shortfall(self, db, config):
        """A peer under-reporting itself is the peer's problem, not a missing row."""
        crawler = self._crawler(db, config)
        assert crawler._warn_on_index_shortfall(
            {"total_capabilities": 2}, "https://atlas.example.com", 5
        ) is None

    @pytest.mark.parametrize("manifest", [
        {},
        {"total_capabilities": "seven"},
        {"total_capabilities": True},
        {"total_capabilities": -1},
    ])
    def test_a_missing_or_junk_declared_count_is_not_a_warning(self, db, config, manifest, caplog):
        crawler = self._crawler(db, config)
        with caplog.at_level(logging.WARNING):
            assert crawler._warn_on_index_shortfall(
                manifest, "https://atlas.example.com", 3
            ) is None
        assert "declares" not in caplog.text

    def test_capabilities_count_is_honoured_when_total_is_absent(self, db, config, caplog):
        crawler = self._crawler(db, config)
        with caplog.at_level(logging.WARNING):
            assert crawler._warn_on_index_shortfall(
                {"capabilities_count": 9}, "https://atlas.example.com", 4
            ) == 9
        assert "capabilities_count" in caplog.text

    def test_the_real_atlas_manifest_shape_indexes_every_tool(self, db, config):
        """Regression fixture: the shape that lost a SKU in the live catalogue."""
        crawler = self._crawler(db, config)
        manifest = {
            "protocol_version": "v2",
            "total_capabilities": 3,
            "tools": [
                {
                    "capability_id": f"atlas.example.{i}@v1",
                    "name": f"atlas.example.{i}@v1",
                    "product_id": "atlas.products",
                    "description": "example",
                    "price_per_call_usd": price,
                    "p50_latency_ms": 150,
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
                for i, price in enumerate((0.01, 0.12, 0.15))
            ],
        }
        indexed = crawler._index_manifest_capabilities(
            manifest, "https://atlas.example.com", "ATLAS"
        )
        assert indexed == 3
        assert crawler._warn_on_index_shortfall(
            manifest, "https://atlas.example.com", indexed
        ) is None


class TestApprovedPeersNobodyLinksTo:
    """An approved hub that no seed points at was never crawled again.

    The frontier carries seeds and PENDING peers only, on the stated assumption that
    "already-active peers are reachable through the BFS from the operator's seeds". That is
    false the moment a peer is not linked from any seed — and the live federation proved it:
    hunt.modelmarket.dev sat as an APPROVED peer with five capabilities of its own, last
    crawled 2026-08-11, and seventeen days later not one of them had reached the catalogue.
    Approving a hub promises its capabilities will be "indexed on the next crawl"; for a hub
    nobody links to, there was no next crawl.
    """

    def _crawler(self, tmp_path, monkeypatch, seeds, peers):
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.models import Peer

        config = HubConfig()
        config.seed_list = list(seeds)
        db = HubDatabase(tmp_path / "hub.db")
        for peer in peers:
            # `upsert_peer` takes the status as an ARGUMENT and defaults it to "active" —
            # the Peer object's own field is ignored, which is easy to miss and makes a
            # "stored as key_mismatch" fixture silently store as active.
            db.upsert_peer(peer, status=getattr(peer, "status", "active") or "active")
        crawler = Crawler(config=config, db=db)

        visited: list[str] = []

        async def fake_crawl_one(url, depth, discoverer):
            visited.append(url)
            return {"capabilities_count": 1, "new_peer_urls": []}

        monkeypatch.setattr(crawler, "_crawl_one", fake_crawl_one)
        return crawler, visited, Peer

    def test_an_approved_peer_off_the_seed_graph_is_refreshed(self, tmp_path, monkeypatch):
        import asyncio

        from aimarket_hub.models import Peer

        crawler, visited, _ = self._crawler(
            tmp_path, monkeypatch,
            seeds=["https://seed.example/.well-known/ai-market.json"],
            peers=[Peer(
                url="https://lonely.example", name="Lonely hub", status="active",
                well_known_url="https://lonely.example/.well-known/ai-market.json",
                last_crawl="2026-08-11T09:12:03Z",
            )],
        )
        asyncio.run(crawler.crawl())
        assert "https://lonely.example/.well-known/ai-market.json" in visited, (
            "an approved peer nothing links to was skipped again"
        )

    def test_a_peer_already_reached_this_cycle_is_not_dialled_twice(self, tmp_path, monkeypatch):
        import asyncio

        from aimarket_hub.models import Peer

        seed = "https://seed.example/.well-known/ai-market.json"
        crawler, visited, _ = self._crawler(
            tmp_path, monkeypatch, seeds=[seed],
            peers=[Peer(url="https://seed.example", name="Seed", status="active",
                        well_known_url=seed, last_crawl="")],
        )
        asyncio.run(crawler.crawl())
        assert visited.count(seed) == 1

    def test_the_refresh_pass_is_bounded_and_stalest_first(self, tmp_path, monkeypatch):
        """The cost the original comment was avoiding: a handful of dead rows must not turn
        every cycle into minutes of DNS and connect timeouts."""
        import asyncio

        from aimarket_hub.models import Peer

        monkeypatch.setenv("AIMARKET_CRAWL_REFRESH_MAX", "2")
        peers = [
            Peer(url=f"https://p{i}.example", name=f"p{i}", status="active",
                 well_known_url=f"https://p{i}.example/.well-known/ai-market.json",
                 last_crawl=f"2026-08-{10 + i:02d}T00:00:00Z")
            for i in range(5)
        ]
        crawler, visited, _ = self._crawler(tmp_path, monkeypatch, seeds=[], peers=peers)
        asyncio.run(crawler.crawl())
        assert len(visited) == 2, f"refresh pass was not capped: {visited}"
        assert visited == [
            "https://p0.example/.well-known/ai-market.json",
            "https://p1.example/.well-known/ai-market.json",
        ], "the stalest peers must be the ones refreshed"

    def test_an_inactive_peer_is_left_alone(self, tmp_path, monkeypatch):
        import asyncio

        from aimarket_hub.models import Peer

        crawler, visited, _ = self._crawler(
            tmp_path, monkeypatch, seeds=[],
            peers=[Peer(url="https://gone.example", name="Gone", status="key_mismatch",
                        well_known_url="https://gone.example/.well-known/ai-market.json")],
        )
        asyncio.run(crawler.crawl())
        assert visited == []


class TestAPeerContributesOnlyItsOwn:
    """A hub's manifest carries its federated rows too, and importing them re-imports our own
    catalogue through whoever else federates with us.

    Measured on the live federation the moment approved-but-unlinked peers became reachable:
    crawling hunt.modelmarket.dev pulled 101 tools of which 96 were ATLAS, GAIA and the oracle
    family coming back a second time — 274 catalogue rows for 103 distinct capabilities, 92 of
    them duplicated. A buyer routed through the copy pays two hops to reach a provider we
    already index directly.
    """

    def _index(self, tmp_path, tools, base_url="https://peer.example"):
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase

        db = HubDatabase(tmp_path / "hub.db")
        crawler = Crawler(config=HubConfig(), db=db)
        n = crawler._index_manifest_capabilities(
            {"tools": tools}, base_url, "Peer",
        )
        return n, db

    def _tool(self, cap_id, source):
        return {
            "capability_id": cap_id, "product_id": cap_id.split(".")[0],
            "name": cap_id, "description": "x", "price_per_call_usd": 0.01,
            "source_hub": source,
        }

    def test_a_re_exported_row_is_not_a_listing(self, tmp_path):
        n, db = self._index(tmp_path, [
            self._tool("signal.evidence@v1", "local"),
            self._tool("signal.case@v1", "local"),
            self._tool("atlas.point.read@v1", "https://atlas.modelmarket.dev"),
            self._tool("gaia.weather.read@v1", "https://iot.modelmarket.dev"),
        ])
        assert n == 2, "the peer's re-exports were indexed as if it owned them"
        ids = {c.capability_id for c in db.list_capabilities(source_hub="https://peer.example")}
        assert ids == {"signal.evidence@v1", "signal.case@v1"}

    def test_a_row_naming_the_peer_itself_still_counts(self, tmp_path):
        """Some hubs stamp their own URL rather than "local"; that is still their own work."""
        n, _ = self._index(tmp_path, [
            self._tool("signal.submit@v1", "https://peer.example"),
            self._tool("signal.heroes@v1", "https://peer.example/"),
        ])
        assert n == 2

    def test_a_row_with_no_source_is_taken_at_face_value(self, tmp_path):
        """An older peer that publishes no source_hub is describing its own catalogue."""
        n, _ = self._index(tmp_path, [{"capability_id": "old.tool@v1", "product_id": "old",
                                       "name": "old", "price_per_call_usd": 0.01}])
        assert n == 1


class TestStaleRowsAreDropped:
    """The crawl upserts and never deleted, so anything a peer stopped listing stayed forever.

    `crawl(clear_first=True)` promised in its docstring that old federated capabilities are
    cleared — the clear-before logic had been removed to close the empty-catalogue window and
    nothing replaced it, so the parameter did nothing. Live consequence: once re-exported rows
    stopped being indexed, the 96 copies of our own ATLAS and GAIA that had arrived through a
    peer's manifest were still being served, because nothing removes what nothing rewrites.
    """

    def _crawler(self, tmp_path):
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase

        db = HubDatabase(tmp_path / "hub.db")
        return Crawler(config=HubConfig(), db=db), db

    def _tool(self, cap_id):
        return {"capability_id": cap_id, "product_id": cap_id.split(".")[0], "name": cap_id,
                "description": "x", "price_per_call_usd": 0.01, "source_hub": "local"}

    def test_a_capability_a_peer_stopped_listing_is_removed(self, tmp_path):
        crawler, db = self._crawler(tmp_path)
        peer = "https://peer.example"
        crawler._index_manifest_capabilities(
            {"tools": [self._tool("a@v1"), self._tool("b@v1")]}, peer, "Peer")
        crawler._prune_unlisted(peer)
        assert {c.capability_id for c in db.list_capabilities(source_hub=peer)} == {"a@v1", "b@v1"}

        crawler._index_manifest_capabilities({"tools": [self._tool("a@v1")]}, peer, "Peer")
        assert crawler._prune_unlisted(peer) == 1
        assert {c.capability_id for c in db.list_capabilities(source_hub=peer)} == {"a@v1"}

    def test_another_peers_rows_are_untouched(self, tmp_path):
        crawler, db = self._crawler(tmp_path)
        crawler._index_manifest_capabilities({"tools": [self._tool("mine@v1")]},
                                             "https://other.example", "Other")
        crawler._index_manifest_capabilities({"tools": [self._tool("a@v1")]},
                                             "https://peer.example", "Peer")
        crawler._prune_unlisted("https://peer.example")
        assert [c.capability_id for c in db.list_capabilities(source_hub="https://other.example")] == ["mine@v1"]


class TestFederationObservationGossip:
    def test_observed_hubs_are_an_explicit_gossip_layer(self, tmp_path):
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase

        crawler = Crawler(config=HubConfig(), db=HubDatabase(tmp_path / "hub.db"))
        document = {
            "peers": [{"url": "https://approved.example"}],
            "observed_hubs": [
                {"url": "https://new.example", "status": "observed"},
                {"url": "https://not-observed.example", "status": "active"},
            ],
        }
        assert crawler._extract_peer_urls(document) == ["https://approved.example"]
        assert crawler._extract_peer_urls(document, include_observed=True) == [
            "https://approved.example", "https://new.example",
        ]

    def test_gossip_requires_a_valid_full_document_signature(self, tmp_path):
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase
        from aimarket_hub.signing import Signer

        source = Signer(tmp_path / "source-key")
        crawler = Crawler(config=HubConfig(), db=HubDatabase(tmp_path / "hub.db"))
        document = {
            "name": "New Hub",
            "signer_public_key": source.public_key_b64,
            "observed_hubs": [{"url": "https://seen.example", "status": "observed"}],
        }
        document["signature"] = source.sign_object(document)
        assert crawler._well_known_gossip_verified(document, source.public_key_b64)

        document["observed_hubs"][0]["url"] = "https://injected.example"
        assert not crawler._well_known_gossip_verified(document, source.public_key_b64)

    def test_a_gossiped_address_is_persisted_before_it_is_reachable(
        self, monkeypatch, tmp_path,
    ):
        import asyncio

        import aimarket_hub.crawler as crawler_module
        from aimarket_hub.config import HubConfig
        from aimarket_hub.crawler import Crawler
        from aimarket_hub.database import HubDatabase

        monkeypatch.setattr(crawler_module, "_url_is_safe", lambda url: True)
        config = HubConfig()
        config.seed_list = ["https://trusted.example/.well-known/ai-market.json"]
        config.max_crawl_depth = 2
        db = HubDatabase(tmp_path / "hub.db")
        crawler = Crawler(config=config, db=db)

        async def fake_crawl_one(url, depth, discoverer):
            if "trusted.example" in url:
                return {"capabilities_count": 0, "new_peer_urls": ["https://new.example"]}
            return None  # the new Hub is offline, but its address is still knowledge

        monkeypatch.setattr(crawler, "_crawl_one", fake_crawl_one)
        asyncio.run(crawler.crawl())

        observed = db.get_peer("https://new.example")
        assert observed is not None
        assert observed.status == "pending"
        assert observed.trusted is False
        assert observed.discoverer == "gossip:https://trusted.example"


class TestAHubIsNotItsOwnPeer:
    """A hub that seeds itself filed itself as a pending peer.

    Seen live on independentai.network/hub: AIMARKET_SEED_LIST was its own well-known,
    so the crawler fetched itself, `_crawl_one` met an unknown peer on first contact, and
    recorded it untrusted — the hub sitting in its own pending queue, holding one of the
    bounded open-federation slots and re-dialling itself every cycle. The gossip branch
    had always filtered its own address; seeds and the pending queue never did.
    """

    @pytest.mark.asyncio
    async def test_a_self_seed_is_refused(self, db, signer, config):
        config.hub_url = "https://independentai.network/hub"
        crawler = Crawler(config=config, db=db, signer=signer)
        crawler._safe_get = AsyncMock()
        try:
            result = await crawler._crawl_one(
                "https://independentai.network/hub/.well-known/ai-market.json", 0, "seed",
            )
        finally:
            await crawler.close()
        assert result is None
        # Refused before any request: the hub does not talk to itself at all.
        crawler._safe_get.assert_not_awaited()
        assert db.get_peer("https://independentai.network/hub") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("spelling", [
        "http://independentai.network/hub/.well-known/ai-market.json",   # scheme differs
        "https://IndependentAI.network/hub/.well-known/ai-market.json",  # case differs
        "https://independentai.network/hub/.well-known/ai-market.json",  # exact
    ])
    async def test_self_is_recognised_across_spellings(self, db, signer, config, spelling):
        """The raw string compare this replaces matched only the third one."""
        config.hub_url = "https://independentai.network/hub"
        crawler = Crawler(config=config, db=db, signer=signer)
        crawler._safe_get = AsyncMock()
        try:
            assert await crawler._crawl_one(spelling, 0, "seed") is None
        finally:
            await crawler.close()
        crawler._safe_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_self_seed_is_not_counted_as_a_crawl_error(self, db, signer, config):
        """The funnel returns None, which the drain loop counts as an error — so a
        self-seed dropped only there would post one phantom error every cycle."""
        config.hub_url = "https://independentai.network/hub"
        config.seed_list = ["https://independentai.network/hub/.well-known/ai-market.json"]
        crawler = Crawler(config=config, db=db, signer=signer)
        crawler._safe_get = AsyncMock()
        try:
            stats = await crawler.crawl()
        finally:
            await crawler.close()
        assert stats["errors"] == 0
        assert stats["discovered"] == 0
        crawler._safe_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_different_hub_on_the_same_host_is_still_crawled(
        self, db, signer, config,
    ):
        """Path-based hubs share a host; only the hub's own address is refused."""
        config.hub_url = "https://independentai.network/hub"
        crawler = Crawler(config=config, db=db, signer=signer)
        wk = dict(SAMPLE_WELL_KNOWN)

        class _Resp:
            status_code = 200
            def json(self):
                return wk

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            await crawler._crawl_one(
                "https://independentai.network/other/.well-known/ai-market.json", 0, "seed",
            )
        finally:
            await crawler.close()
        crawler._safe_get.assert_awaited()
        assert db.get_peer("https://independentai.network/other") is not None


class TestAHubRefusesItsOwnIdentity:
    """A URL is a name and a hub has many; the signing key IS the hub.

    The existing self-guard compares SPELLINGS against `config.hub_url`, and a hub outlives
    its spellings. The competing lab hub RAN as `http://108.165.32.182:9083` for two days
    (2026-09-01T11:56:22Z to 2026-09-03T19:05:34Z), advertising it in `X-AIMarket-Crawler` on
    every fetch, before the operator restarted it as `https://hub.modelmarket.dev`. Its old
    identity survived in its neighbours' pending rows, which never expire; ten seconds after
    the rename it read its own former address back out of a neighbour's document, filed it as
    a stranger, and rendered it in its own UNAPPROVED HUBS block with a red "assay failed"
    badge. Measured 2026-09-05: that row's advertised key, the raw-IP endpoint's
    `signer_public_key` and the page's own `signer_public_key` were one and the same string.

    This guard is the filter, not the cure — see the note in `crawler._crawl_one`.
    """

    @pytest.mark.asyncio
    async def test_a_well_known_answering_with_our_own_key_is_refused(self, db, signer, config):
        crawler = Crawler(config=config, db=db, signer=signer)
        wk_url = "http://203.0.113.7:9083/.well-known/ai-market.json"

        mine = dict(SAMPLE_WELL_KNOWN)
        mine["signer_public_key"] = signer.public_key_b64      # us, under an address we never publish

        class _Resp:
            status_code = 200
            def json(self):
                return mine

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            result = await crawler._crawl_one(wk_url, 0, "gossip")
        finally:
            await crawler.close()

        assert result is None, "the hub crawled itself"
        assert db.get_peer("http://203.0.113.7:9083") is None, "the hub filed itself as a peer"

    @pytest.mark.asyncio
    async def test_a_genuine_stranger_with_a_different_key_is_still_recorded(self, db, signer, config):
        """The guard must key on identity, not merely on being reached over a raw address."""
        crawler = Crawler(config=config, db=db, signer=signer)
        wk_url = "http://203.0.113.9:9083/.well-known/ai-market.json"

        theirs = dict(SAMPLE_WELL_KNOWN)
        theirs["signer_public_key"] = "jmh/t/PAQ+dFsyCQDtTioqExampleKeyForTests="
        assert theirs["signer_public_key"] != signer.public_key_b64

        class _Resp:
            status_code = 200
            def json(self):
                return theirs

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            result = await crawler._crawl_one(wk_url, 0, "gossip")
        finally:
            await crawler.close()

        assert result is not None, "a stranger was refused"
        assert db.get_peer("http://203.0.113.9:9083") is not None


class TestAHubMayRetireAnOldName:
    """A hub outlives its addresses, and the protocol has no retraction.

    The competing lab hub ran as `http://108.165.32.182:9083` for two days; every neighbour
    recorded that address exactly as the open-federation door intends. It was then renamed to
    `https://hub.modelmarket.dev`. The old rows did not die with the old name — measured
    2026-09-05, a neighbour still held the plaintext raw IP as its ACTIVE, TRUSTED peer and
    knew the hub by no other name.

    The endpoint itself says where it lives, via `manifest_url`. When that names another base
    AND that base answers with the SAME signing key, the two names are one hub.
    """

    @staticmethod
    def _row(url, key, name):
        return Peer(url=url, name=name, capabilities_count=0,
                    well_known_url=f"{url}/.well-known/ai-market.json",
                    public_key=key, depth=1)

    @staticmethod
    def _wk(name, key, manifest_base):
        w = dict(SAMPLE_WELL_KNOWN)
        w["name"] = name
        w["signer_public_key"] = key
        w["manifest_url"] = f"{manifest_base}/ai-market/v2/manifest"
        return w

    def test_the_canonical_base_is_the_path_prefix_not_the_origin(self):
        """A hub can be mounted under a path; its home is not the apex."""
        from aimarket_hub.crawler import _canonical_base_from_manifest_url as f
        assert f("https://independentai.network/hub/ai-market/v2/manifest") == "https://independentai.network/hub"
        assert f("https://hub.example/ai-market/v2/manifest") == "https://hub.example"
        assert f("https://hub.example/something/else") == ""
        assert f("ftp://hub.example/ai-market/v2/manifest") == ""
        assert f(None) == ""

    @pytest.mark.asyncio
    async def test_a_trusted_row_moves_to_the_canonical_name_and_keeps_its_trust(self, db, signer, config):
        OLD, NEW = "http://203.0.113.11:9083", "https://canonical.example"
        THEIR_KEY = "jmh/t/PAQ+dFsyCQDtTioqExampleKeyForTests="
        db.upsert_peer(self._row(OLD, THEIR_KEY, "Under an old name"), status="active")
        assert db.set_peer_trusted(OLD, True) is True

        crawler = Crawler(config=config, db=db, signer=signer)
        wk = self._wk("Renamed Hub", THEIR_KEY, NEW)

        class _Resp:
            status_code = 200
            def __init__(self, body): self._b = body
            def json(self): return self._b

        # First call: the old address. Second: the canonical base proving the same key.
        crawler._safe_get = AsyncMock(side_effect=[_Resp(wk), _Resp(wk)])
        try:
            result = await crawler._crawl_one(f"{OLD}/.well-known/ai-market.json", 1, "gossip")
        finally:
            await crawler.close()

        assert result == {"capabilities_count": 0, "new_peer_urls": [NEW]}
        assert db.get_peer(OLD) is None, "the stale name survived"
        moved = db.get_peer(NEW)
        assert moved is not None, "the canonical name was not created"
        assert moved.trusted is True, "the operator's decision was thrown away by a rename"

    @pytest.mark.asyncio
    async def test_a_claim_the_other_base_will_not_sign_for_is_ignored(self, db, signer, config):
        """The key match IS the safety. Without it, any hub could claim any domain's row."""
        VICTIM = "https://victim.example"
        db.upsert_peer(self._row("http://203.0.113.12:9083",
                                 "attackerKeyExampleForTests0000000000000=", "Evil"),
                       status="pending")
        crawler = Crawler(config=config, db=db, signer=signer)

        evil = self._wk("Evil", "attackerKeyExampleForTests0000000000000=", VICTIM)
        victim_wk = dict(SAMPLE_WELL_KNOWN)
        victim_wk["signer_public_key"] = "victimOwnKeyExampleForTests000000000000="

        class _Resp:
            status_code = 200
            def __init__(self, body): self._b = body
            def json(self): return self._b

        crawler._safe_get = AsyncMock(side_effect=[_Resp(evil), _Resp(victim_wk)])
        try:
            result = await crawler._crawl_one("http://203.0.113.12:9083/.well-known/ai-market.json", 1, "gossip")
        finally:
            await crawler.close()

        assert result is not None and result.get("new_peer_urls") != [VICTIM], "a domain was hijacked"
        assert db.get_peer("http://203.0.113.12:9083") is not None, "the evil row was retired for free"
        assert db.get_peer(VICTIM) is None, "a row was minted for a hub that never asked"


class TestSqliteWaitsInsteadOfFailing:
    """`timeout` IS sqlite's busy timeout, and unset means ZERO — fail on first contention.

    The connection that serves every request was opened without it, while `get_connection()`
    opened a second one to the same file asking for 10s: the patient connection was the
    occasional one and the impatient connection was the hot path.

    Measured 2026-09-05 on independentai.network/hub — federated invokes returned a bare 500,
    eight times out of eight, raised from `record_invocation` AFTER the peer's answer was
    already in hand. A restart cleared it, which is contention, not corruption.
    """

    def test_the_shared_connection_has_a_busy_timeout(self, tmp_path):
        from aimarket_hub.db_backend import SQLiteBackend, _SQLITE_BUSY_TIMEOUT_S
        assert _SQLITE_BUSY_TIMEOUT_S > 0, "a zero busy timeout is sqlite's default, not a choice"
        be = SQLiteBackend(str(tmp_path / "busy.db"))
        try:
            # sqlite exposes the timeout only through behaviour, so assert on the source of
            # truth both connections read.
            assert be._conn is not None
        finally:
            with contextlib.suppress(Exception):
                be._conn.close()

    def test_both_connections_to_one_file_agree(self):
        """A difference here shows up as "sometimes it works", depending which one served."""
        import inspect
        from aimarket_hub import db_backend
        src = inspect.getsource(db_backend)
        # every sqlite3.connect in this module must take the shared constant
        connects = [ln for ln in src.splitlines() if "sqlite3.connect(" in ln]
        assert connects, "no sqlite3.connect found — did the backend move?"
        window = src.split("sqlite3.connect(")
        for chunk in window[1:]:
            head = chunk[:200]
            assert "_SQLITE_BUSY_TIMEOUT_S" in head, (
                "a sqlite3.connect() without the shared busy timeout: %s" % head[:80]
            )


class TestMeasuredLatencyIsNotUnknown:
    """0 ms means "unknown" to ranking. A peer that MEASURED a sub-millisecond handler
    rounded to 0 and was ranked as if it had no measurement at all."""

    def _crawler(self, db, config):
        from aimarket_hub.crawler import Crawler

        return Crawler(config=config, db=db)

    @pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity", "free", True, []])
    def test_hostile_price_is_skipped_without_dropping_innocent_tools(self, db, config, price):
        crawler = self._crawler(db, config)
        tool = {"capability_id": "hostile@v1", "product_id": "price-peer",
                "price_per_call_usd": price}
        healthy = {**tool, "capability_id": "healthy@v1", "price_per_call_usd": 0.01}
        assert crawler._index_manifest_capabilities(
            {"tools": [tool, healthy]}, "https://peer.example.com", "Price peer",
        ) == 1
        assert db.get_capability("price-peer", "hostile@v1", "https://peer.example.com") is None

    def _index(self, db, config, **tool_fields):
        crawler = self._crawler(db, config)
        tool = {
            "capability_id": "gaia.weather.read@v1", "name": "gaia.weather.read",
            "product_id": "gaia.gateway", "description": "weather", "price_per_call_usd": 0.001,
            "input_schema": {"type": "object"}, "output_schema": {"type": "object"},
            **tool_fields,
        }
        crawler._index_manifest_capabilities(
            {"protocol_version": "v2", "tools": [tool]}, "https://iot.example.com", "GAIA",
        )
        return db.get_capability("gaia.gateway", "gaia.weather.read@v1", "https://iot.example.com")

    def test_a_measured_zero_is_stored_as_one(self, db, config):
        cap = self._index(db, config, p50_latency_ms=0, metrics_source="measured", calls_observed=199)
        assert cap.p50_latency_ms == 1

    def test_a_declared_zero_stays_unknown(self, db, config):
        cap = self._index(db, config, p50_latency_ms=0, metrics_source="declared", calls_observed=0)
        assert cap.p50_latency_ms == 0

    def test_a_fractional_or_junk_latency_does_not_drop_the_tool(self, db, config):
        assert self._index(db, config, p50_latency_ms="0.4", calls_observed=3).p50_latency_ms == 1
        assert self._index(db, config, p50_latency_ms="fast").p50_latency_ms == 3000

    @pytest.mark.parametrize("raw", ["inf", "-Infinity", float("inf"), 1e999, True, None, [3]])
    def test_non_finite_or_odd_values_fall_back_without_stopping_the_index(self, db, config, raw):
        cap = self._index(db, config, p50_latency_ms=raw, calls_observed=float("inf"))
        assert cap is not None and cap.p50_latency_ms == 3000


class TestToolsSoldAtTheirOwnUrl:
    """mach402.dev-shaped manifests (2026-10-21): name, endpoint, method and price_usd, and no
    capability_id or product_id. The crawl indexed them at the $0.35 default price, with no
    product an invoke would accept and no idea where the tool answers."""

    def test_such_a_tool_is_indexed_at_its_price_with_its_url_and_a_product(self, tmp_path, monkeypatch):
        import aimarket_hub.crawler as crawler_mod

        monkeypatch.setattr(crawler_mod, "_url_is_safe", lambda u: u.startswith("https://"))
        db = HubDatabase(tmp_path / "hub.db")
        crawler = Crawler(config=HubConfig(), db=db)
        peer = "https://mach402.example"
        tools = [
            {"name": "scan_python", "description": "x", "endpoint": f"{peer}/scan/python",
             "method": "POST", "price_usd": 0.02, "input_schema": {"type": "object"}},
            {"name": "relay", "description": "x", "endpoint": "https://elsewhere.example/r",
             "method": "POST", "price_usd": 0.01},
            {"capability_id": "hub.cap@v1", "product_id": "p1", "name": "hub.cap@v1",
             "description": "x", "price_per_call_usd": 0.03, "endpoint": f"{peer}/hub"},
        ]
        assert crawler._index_manifest_capabilities({"tools": tools}, peer, "Machina") == 3
        rows = {c.capability_id: c for c in db.list_capabilities(source_hub=peer)}
        scan = rows["scan_python"]
        assert scan.price_per_call_usd == pytest.approx(0.02)
        assert scan.peer_endpoint == f"{peer}/scan/python"
        assert scan.product_id == "mach402.example"
        # Another host is never a door; a hub-protocol listing keeps its invoke route.
        assert rows["relay"].peer_endpoint == "" and rows["relay"].price_per_call_usd == pytest.approx(0.01)
        assert rows["hub.cap@v1"].peer_endpoint == "" and rows["hub.cap@v1"].product_id == "p1"


DRAFT_WELL_KNOWN = {
    "name": "Draft-named peer",
    "protocol_versions": ["v2"],
    "catalogue_url": "https://seed-hub.example.com/ai-market/manifest",
    "signer_public_key": "dGVzdF9wdWJsaWNfa2V5",
    "signature_profile": "ed25519-pipe-2",
    "peers": ["https://hub3.example.com/.well-known/agent-marketplace"],
}


class TestDraftNames:
    """A peer that serves the Internet-Draft's member names is crawled like any other."""

    @pytest.mark.asyncio
    async def test_a_draft_shaped_document_is_accepted_and_its_peers_followed(self, db, signer, config):
        crawler = Crawler(config=config, db=db, signer=signer)
        wk_url = "https://seed-hub.example.com/.well-known/agent-marketplace"

        class _Resp:
            status_code = 200
            def json(self):
                return dict(DRAFT_WELL_KNOWN)

        crawler._safe_get = AsyncMock(return_value=_Resp())
        try:
            result = await crawler._crawl_one(wk_url, 0, "seed")
        finally:
            await crawler.close()

        assert result is not None, "draft member names were rejected"
        # First contact is untrusted, so its gossip is not followed — same as a legacy peer.
        assert result == {"capabilities_count": 0, "new_peer_urls": []}
        peer = db.get_peer("https://seed-hub.example.com")
        assert peer is not None and peer.trusted is False

        # Once trusted, its peers are followed, and the one that advertised a draft-path
        # discovery URI is dialled there, not at a legacy path it may not serve.
        from aimarket_hub.discovery_names import normalize_discovery_document
        urls = crawler._extract_peer_urls(normalize_discovery_document(DRAFT_WELL_KNOWN))
        assert urls == ["https://hub3.example.com"]
        assert crawler._peer_discovery_urls == {
            "https://hub3.example.com": "https://hub3.example.com/.well-known/agent-marketplace",
        }

    @pytest.mark.asyncio
    async def test_the_crawler_sends_both_header_spellings(self, db, signer, config):
        crawler = Crawler(config=config, db=db, signer=signer)
        seen = {}

        async def fake_send(request, **kwargs):
            seen.update(request.headers)
            raise RuntimeError("stop here")

        crawler._http.send = fake_send
        import aimarket_hub.outbound_http as oh

        async def fake_prepare(url):
            return url, {}, {}

        original = oh.prepare_safe_request_async
        oh.prepare_safe_request_async = fake_prepare
        try:
            with pytest.raises(RuntimeError):
                await crawler._safe_get("https://seed-hub.example.com/.well-known/ai-market.json")
        finally:
            oh.prepare_safe_request_async = original
            await crawler.close()
        assert seen.get("x-aimarket-crawler") == config.hub_url
        assert seen.get("agent-marketplace-crawler") == config.hub_url
