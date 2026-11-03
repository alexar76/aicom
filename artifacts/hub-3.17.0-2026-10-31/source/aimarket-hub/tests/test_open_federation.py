"""Open federation: who may knock vs who is trusted.

Every test here defends one invariant. The point of open federation is that a
stranger's hub can appear on its own, and the point of *these* tests is that
appearing buys it nothing: no indexing, no search hit, no route, no place in the
document this hub publishes to the rest of the network.
"""

import json
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
STRANGER = "https://stranger.example"


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    """A hub built after `env` — create_app snapshots env into closure state."""
    env.setdefault("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    env.setdefault("AIMARKET_FEDERATION_ASSAY", "0")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


@pytest.fixture
def resolvable(monkeypatch):
    """`.example` is a reserved TLD that never resolves, and the SSRF guard resolves
    DNS. Tests about federation logic patch the guard so they exercise that logic;
    ``test_unsafe_urls_are_never_admitted`` deliberately does NOT use this fixture and
    runs against the real check."""
    import aimarket_hub.crawler as crawler

    def _syntactic(url: str) -> bool:
        return url.startswith(("http://", "https://")) and "localhost" not in url

    monkeypatch.setattr(crawler, "_url_is_safe", _syntactic)
    return _syntactic


def _wait_for(predicate, timeout: float = 3.0):
    """Inbound discovery runs off the request path, so results arrive slightly late."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# --- observation is always open; trust never is ---------------------------

def test_announce_without_token_is_visible_but_quarantined_by_default(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path) as client:
        r = client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        assert r.status_code == 200, r.text
        peers = client.get("/ai-market/v2/federation/peers").json()
        assert peers["pending_count"] == 1
        assert peers["observation_gossip"] is True


def test_open_flag_is_reported_so_operators_can_see_which_mode_they_run(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        assert client.get("/ai-market/v2/federation/peers").json()["open_federation"] is False
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        assert client.get("/ai-market/v2/federation/peers").json()["open_federation"] is True


# --- open mode admits, but only to quarantine -----------------------------

def test_open_announce_lands_pending_and_untrusted(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        r = client.post(
            "/ai-market/v2/federation/announce",
            json={"hub_url": STRANGER, "hub_name": "Stranger Hub", "capabilities_count": 999},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["trusted"] is False

        peers = client.get("/ai-market/v2/federation/peers").json()
        assert peers["pending_count"] == 1
        assert [p["url"] for p in peers["pending"]] == [STRANGER]
        # An approved-peer list must not gain a member because a stranger asked.
        assert STRANGER not in [p["url"] for p in peers["peers"]]

        stored = client.hub_db.get_peer(STRANGER)  # type: ignore[attr-defined]
        assert stored.trusted is False and stored.status == "pending"
        # A self-reported capability count is a claim, not evidence.
        assert stored.capabilities_count == 0


def test_open_announce_never_downgrades_a_known_trusted_peer(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_peer(Peer(url=STRANGER, name="Approved", trusted=True, public_key="pinned-key"))

        client.post(
            "/ai-market/v2/federation/announce",
            json={"hub_url": STRANGER, "hub_name": "Impostor", "signer_public_key": "attacker-key"},
        )

        peer = db.get_peer(STRANGER)
        assert peer.trusted is True, "an announcement must never revoke trust"
        assert peer.name == "Approved", "an announcement must never rewrite a known peer"
        assert peer.public_key == "pinned-key", "an announcement must never rotate a pinned key"


def test_pending_queue_is_capped(monkeypatch, tmp_path, resolvable):
    with _hub(
        monkeypatch, tmp_path,
        AIMARKET_FEDERATION_OPEN="1", AIMARKET_FEDERATION_GOSSIP_MAX_OBSERVED="2",
    ) as client:
        for i in range(2):
            r = client.post(
                "/ai-market/v2/federation/announce",
                json={"hub_url": f"https://peer{i}.example"},
            )
            assert r.status_code == 200
        r = client.post(
            "/ai-market/v2/federation/announce", json={"hub_url": "https://peer2.example"},
        )
        assert r.status_code == 429, "an open door must not be an unbounded write"


# --- quarantine actually quarantines --------------------------------------

def test_pending_peer_is_absent_from_the_published_well_known(monkeypatch, tmp_path, resolvable):
    """An observation is republished, but never laundered into approved peers."""
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        wk = client.get("/.well-known/ai-market.json").json()
        assert STRANGER not in [p["url"] for p in wk.get("peers", [])]
        assert STRANGER in [p["url"] for p in wk.get("observed_hubs", [])]
        assert wk["observed_hubs"][0]["status"] == "observed"


def test_preview_capabilities_are_never_searchable_or_indexed(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        before = db.count_capabilities()
        db.replace_preview_capabilities(STRANGER, [
            {"capability_id": "translate.quantum@v1", "product_id": "p1",
             "name": "Quantum Translate", "description": "translate anything",
             "price_per_call_usd": 0.05},
        ])

        # Visible to the operator...
        preview = client.get("/ai-market/v2/federation/preview", params={"url": STRANGER}).json()
        assert preview["count"] == 1
        assert preview["quarantined"] is True
        assert preview["capabilities"][0]["capability_id"] == "translate.quantum@v1"

        # ...and to nothing else. The real catalogue never grew.
        assert db.count_capabilities() == before
        assert db.find_by_capability_id("translate.quantum@v1") is None
        hits = client.get(
            "/ai-market/v2/search", params={"intent": "quantum translate", "budget": 1}
        ).json()
        blob = str(hits)
        assert "translate.quantum" not in blob
        assert STRANGER not in blob


def test_a_pending_row_separates_what_we_read_from_what_the_peer_claims(
    monkeypatch, tmp_path, resolvable
):
    """Two counts, two meanings — the landing page renders both or it misreports one.

    It used to publish only `preview_capabilities`, and the UI fell back through
    `a || b || 0`. A knocking hub advertising 28 capabilities therefore printed
    "claimed 0" on hub.attestedmemory.net: nothing previewed (closed door) and no
    declared number in the payload to fall back to.
    """
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})

        peer = db.get_peer(STRANGER)
        peer.capabilities_count = 28          # what the peer says in its well-known
        db.upsert_peer(peer, status="pending")

        def row():
            body = client.get("/ai-market/v2/federation/peers").json()
            return next(r for r in body["pending"] if r["url"] == STRANGER)

        # Nothing read yet: the claim survives on its own, and is not dressed up as ours.
        assert row()["declared_capabilities"] == 28
        assert row()["preview_capabilities"] == 0

        db.replace_preview_capabilities(STRANGER, [
            {"capability_id": "a@v1", "product_id": "p1"},
            {"capability_id": "b@v1", "product_id": "p2"},
        ])
        assert row()["preview_capabilities"] == 2
        assert row()["declared_capabilities"] == 28


def test_the_knock_rail_strings_exist_in_every_pack():
    """The rail is on the PUBLIC landing page, so a missing label ships an empty span."""
    packs = json.loads(
        (Path(__file__).parents[1] / "hub-ui-i18n.json").read_text(encoding="utf-8")
    )["ui"]
    needed = {"pending_caps", "pending_caps_read", "pending_show", "pending_note",
              "knock_find", "knock_found"}
    for lang, pack in packs.items():
        assert needed <= set(pack), lang
        assert all(str(pack[k]).strip() for k in needed), lang


def test_approval_promotes_the_peer_and_drops_the_stale_preview(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        client.post("/ai-market/v2/federation/announce", json={"hub_url": STRANGER})
        db.replace_preview_capabilities(STRANGER, [{"capability_id": "c@v1", "product_id": "p"}])

        r = client.post(
            "/ai-market/v2/federation/peers/approve",
            json={"url": STRANGER}, headers=ADMIN_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["trusted"] is True
        assert body["promoted_from_pending"] is True
        assert body["preview_rows_cleared"] == 1

        assert db.count_preview_capabilities(STRANGER) == 0
        assert db.get_peer(STRANGER).status == "active"
        assert client.get("/ai-market/v2/federation/peers").json()["pending_count"] == 0


# --- reciprocal discovery: a hub that reads us becomes visible -------------

def test_a_hub_that_crawls_us_is_recorded_and_admitted_as_pending(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        r = client.get(
            "/.well-known/ai-market.json",
            headers={"X-AIMarket-Crawler": STRANGER, "User-Agent": "AIMarketHub/2.0.0"},
        )
        assert r.status_code == 200

        assert _wait_for(lambda: db.count_pending_peers() == 1), "inbound crawl never admitted"
        assert db.get_peer(STRANGER).discoverer == "inbound-crawl"
        inbound = client.get("/ai-market/v2/federation/inbound", headers=ADMIN_HEADERS).json()
        assert [row["hub_url"] for row in inbound["inbound"]] == [STRANGER]


def test_default_mode_notes_and_quarantines_an_inbound_crawler(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path) as client:
        db = client.hub_db  # type: ignore[attr-defined]
        client.get("/.well-known/ai-market.json", headers={"X-AIMarket-Crawler": STRANGER})
        assert _wait_for(lambda: len(db.list_inbound_federation()) == 1), (
            "an operator should learn who reads them"
        )
        assert _wait_for(lambda: db.count_pending_peers() == 1)


@pytest.mark.parametrize("header", ["not-a-url", "ftp://x.example", "http://x\r\nInjected: 1", "x" * 400])
def test_malformed_crawler_headers_are_ignored(monkeypatch, tmp_path, header):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        try:
            client.get("/.well-known/ai-market.json", headers={"X-AIMarket-Crawler": header})
        except Exception:
            return  # the HTTP client itself refusing a CRLF header is a pass
        time.sleep(0.2)
        assert db.count_pending_peers() == 0
        assert db.list_inbound_federation() == []


def test_inbound_log_is_admin_only(monkeypatch, tmp_path):
    """Who reads this hub is the operator's business, not a public directory."""
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        assert client.get("/ai-market/v2/federation/inbound").status_code in (401, 403)


def test_unsafe_urls_are_never_admitted(monkeypatch, tmp_path):
    """No fixture here — the real DNS-resolving guard runs.

    An open door that admitted `http://127.0.0.1:9083` or an internal name would hand
    a stranger a crawler pointed at this hub's own network.
    """
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        for hostile in ("http://127.0.0.1:9083", "http://169.254.169.254", "http://192.168.1.10"):
            r = client.post("/ai-market/v2/federation/announce", json={"hub_url": hostile})
            assert r.status_code == 400, f"{hostile} was not rejected: {r.text}"
            client.get("/.well-known/ai-market.json", headers={"X-AIMarket-Crawler": hostile})
        time.sleep(0.3)
        assert db.count_pending_peers() == 0


# --- the preview path itself, not a stand-in for it ------------------------

def test_preview_reads_a_real_signed_manifest(monkeypatch, tmp_path, resolvable):
    """Exercise `_preview_pending_manifest`, not `replace_preview_capabilities`.

    Every other preview test writes rows straight into the database, which is why nobody
    noticed the crawler was reading `manifest["capabilities"]` — a key an AIMarket manifest
    does not have. It previewed zero rows against every real peer and every test stayed
    green. This one feeds a manifest of the shape the protocol actually ships.
    """
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "1")
    root = tmp_path / "crawl"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")

    manifest = {
        "protocol_version": "v1",
        "capabilities_count": 2,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Schema-valid on purpose: the preview path validates before it previews (§2.6),
        # and a half-built manifest would test the rejection, not the read.
        "tools": [
            {"capability_id": "translate.multi@v2", "product_id": "p1", "name": "Translate",
             "description": "translate text", "price_per_call_usd": 0.4,
             "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
            {"capability_id": "summarise@v1", "product_id": "p2", "name": "Summarise",
             "description": "summarise text", "price_per_call_usd": 0.1,
             "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
        ],
    }
    manifest["signature"] = signer.sign_manifest(manifest)

    crawler = Crawler(config=config, db=db, signer=signer)

    class _Resp:
        def json(self):
            return manifest

    async def _fake_get(url):
        return _Resp()

    monkeypatch.setattr(crawler, "_safe_get", _fake_get)
    monkeypatch.setattr(crawler, "_manifest_too_stale", lambda m: False)

    written = asyncio.run(
        crawler._preview_pending_manifest(
            {"manifest_url": "https://stranger.example/ai-market/manifest"},
            "https://stranger.example",
            signer.public_key_b64,
        )
    )

    assert written == 2, "the preview read zero rows — check which manifest key it reads"
    rows = db.list_preview_capabilities("https://stranger.example")
    assert {r["capability_id"] for r in rows} == {"translate.multi@v2", "summarise@v1"}
    assert all(r["quarantined"] for r in rows)
    # And still nothing in the real catalogue.
    assert db.find_by_capability_id("translate.multi@v2") is None


def test_preview_works_with_the_open_door_closed(monkeypatch, tmp_path, resolvable):
    """A closed-door hub still has pending peers, so it still needs the preview.

    Measured on hub.attestedmemory.net (2026-09-08): four knocking hubs, all discovered
    through the seed list and gossip rather than the open door, and every one of them
    rendered "capabilities: 0" with an empty "Show what it offers" — because the preview
    was gated on `federation_open` as well as its own switch. The operator was asked to
    approve strangers with nothing to look at. Its own switch is the one that decides.
    """
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "0")
    root = tmp_path / "crawl-closed"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    assert config.federation_open is False, "this test is about the CLOSED door"
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")

    manifest = {
        "protocol_version": "v1",
        "capabilities_count": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tools": [
            {"capability_id": "translate.multi@v2", "product_id": "p1", "name": "Translate",
             "description": "translate text", "price_per_call_usd": 0.4,
             "input_schema": {"type": "object"}, "output_schema": {"type": "object"}},
        ],
    }
    manifest["signature"] = signer.sign_manifest(manifest)

    crawler = Crawler(config=config, db=db, signer=signer)

    class _Resp:
        def json(self):
            return manifest

    async def _fake_get(url):
        return _Resp()

    monkeypatch.setattr(crawler, "_safe_get", _fake_get)
    monkeypatch.setattr(crawler, "_manifest_too_stale", lambda m: False)

    written = asyncio.run(
        crawler._preview_pending_manifest(
            {"manifest_url": "https://stranger.example/ai-market/manifest"},
            "https://stranger.example",
            signer.public_key_b64,
        )
    )
    assert written == 1
    assert db.count_preview_capabilities("https://stranger.example") == 1
    # Quarantine is unchanged: a preview is still not a catalogue entry.
    assert db.find_by_capability_id("translate.multi@v2") is None


def test_preview_can_still_be_turned_off_on_its_own(monkeypatch, tmp_path, resolvable):
    """`AIMARKET_FEDERATION_PREVIEW_CAPS=0` remains the way to refuse previews."""
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_PREVIEW_CAPS", "0")
    root = tmp_path / "crawl-preview-off"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")
    crawler = Crawler(config=config, db=db, signer=signer)

    async def _never(url):  # a refusal must not even fetch
        raise AssertionError("preview fetched a manifest while switched off")

    monkeypatch.setattr(crawler, "_safe_get", _never)
    written = asyncio.run(
        crawler._preview_pending_manifest(
            {"manifest_url": "https://stranger.example/ai-market/manifest"},
            "https://stranger.example",
            signer.public_key_b64,
        )
    )
    assert written == 0
    assert db.count_preview_capabilities("https://stranger.example") == 0


def test_preview_refuses_a_manifest_that_fails_validation(monkeypatch, tmp_path, resolvable):
    """§2.6(1): validate and verify exactly as for an admitted peer, before displaying.

    Found while writing the test above — a manifest missing required tool fields previews
    nothing, which is the correct behaviour and worth pinning so a future 'be lenient with
    strangers' change has to argue with a test.
    """
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "1")
    root = tmp_path / "crawl-invalid"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")

    manifest = {
        "protocol_version": "v1",
        "capabilities_count": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tools": [{"capability_id": "half.built@v1", "product_id": "p1", "name": "Half"}],
    }
    manifest["signature"] = signer.sign_manifest(manifest)

    crawler = Crawler(config=config, db=db, signer=signer)

    class _Resp:
        def json(self):
            return manifest

    async def _fake_get(url):
        return _Resp()

    monkeypatch.setattr(crawler, "_safe_get", _fake_get)
    monkeypatch.setattr(crawler, "_manifest_too_stale", lambda m: False)

    written = asyncio.run(
        crawler._preview_pending_manifest(
            {"manifest_url": "https://stranger.example/ai-market/manifest"},
            "https://stranger.example",
            signer.public_key_b64,
        )
    )
    assert written == 0
    assert db.count_preview_capabilities("https://stranger.example") == 0


def test_an_announced_peer_actually_gets_crawled(monkeypatch, tmp_path, resolvable):
    """Close the loop the documentation promises: announce → crawl → preview.

    A peer known only from an announcement is in no seed list and in nobody's `peers` array,
    so the BFS never reached it. Its catalogue was never previewed and approving it never led
    to indexing — the join path stopped at step one while every test passed.
    """
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "1")
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY", "0")
    monkeypatch.setenv("AIMARKET_SEED_LIST", "")
    root = tmp_path / "loop"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.seed_list = []
    db = HubDatabase(root / "hub.db")
    signer = Signer(root / "key")

    db.announce_peer(
        Peer(url=STRANGER, name="Stranger",
             well_known_url=f"{STRANGER}/.well-known/ai-market.json",
             discoverer="announce:open"),
        max_pending=10,
    )
    assert db.count_pending_peers() == 1

    crawler = Crawler(config=config, db=db, signer=signer)
    visited: list[str] = []

    async def _fake_crawl_one(url, depth, discoverer):
        visited.append(url)
        return {"capabilities_count": 0, "new_peer_urls": []}

    monkeypatch.setattr(crawler, "_crawl_one", _fake_crawl_one)
    asyncio.run(crawler.crawl())

    assert f"{STRANGER}/.well-known/ai-market.json" in visited, (
        "an announced peer was never fetched — the documented join path cannot complete"
    )


def test_the_frontier_reaches_peers_no_seed_links_to(monkeypatch, tmp_path, resolvable):
    """Active peers are not re-dialled every cycle — but the ones nothing links to still get
    reached.

    This test used to assert the opposite: that an active peer is NEVER enqueued from the
    database, because "active peers are already reachable through the BFS". Production
    disproved it. hunt.modelmarket.dev sat as an APPROVED peer with five capabilities of its
    own, last crawled 2026-08-11, and seventeen days later none of them had reached the
    catalogue — the seeds are satellites with no peer lists, so no BFS path ever led back to
    it, and approving a hub promises exactly that its capabilities are "indexed on the next
    crawl".

    The cost the original rule protected is still protected: the refresh pass is bounded
    (AIMARKET_CRAWL_REFRESH_MAX) and takes the stalest first, so a handful of dead rows cannot
    turn every cycle into minutes of DNS and connect timeouts.
    """
    import asyncio

    from aimarket_hub.config import HubConfig
    from aimarket_hub.crawler import Crawler
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_FEDERATION_OPEN", "1")
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY", "0")
    monkeypatch.setenv("AIMARKET_CRAWL_REFRESH_MAX", "1")
    root = tmp_path / "frontier"
    root.mkdir()
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.seed_list = []
    db = HubDatabase(root / "hub.db")

    db.upsert_peer(Peer(url="https://stale.example", name="Stale", trusted=True,
                        well_known_url="https://stale.example/.well-known/ai-market.json",
                        last_crawl="2026-08-11T09:12:03Z"))
    db.upsert_peer(Peer(url="https://fresher.example", name="Fresher", trusted=True,
                        well_known_url="https://fresher.example/.well-known/ai-market.json",
                        last_crawl="2026-08-28T09:12:03Z"))
    db.announce_peer(Peer(url=STRANGER, name="Stranger",
                          well_known_url=f"{STRANGER}/.well-known/ai-market.json"),
                     max_pending=10)

    crawler = Crawler(config=config, db=db, signer=Signer(root / "key"))
    visited: list[str] = []

    async def _fake_crawl_one(url, depth, discoverer):
        visited.append(url)
        return {"capabilities_count": 0, "new_peer_urls": []}

    monkeypatch.setattr(crawler, "_crawl_one", _fake_crawl_one)
    asyncio.run(crawler.crawl())

    # Pending peers still have no other way in.
    assert f"{STRANGER}/.well-known/ai-market.json" in visited
    # The approved peer nothing links to is reached…
    assert "https://stale.example/.well-known/ai-market.json" in visited
    # …and only as many as the cap allows, stalest first.
    assert "https://fresher.example/.well-known/ai-market.json" not in visited


# ── 2026-09 re-audit: the documented switch must actually switch something ──────────
#
# `AIMARKET_FEDERATION_OPEN` reads, in config.py, as the gate on both open doors:
# "When on, two doors open — POST /federation/announce accepts an unauthenticated
# announcement; a peer that crawls THIS hub identifies itself via X-AIMarket-Crawler and is
# recorded from that alone."  Neither door ever consulted it. It gated only the crawler's
# manifest PREVIEW and a reported status flag, so an operator who left it at its default 0 —
# believing open federation was off — still ran an open door, and with
# AIMARKET_FEDERATION_ASSAY and AIMARKET_FEDERATION_AUTO_ADMIT both defaulting on, all the
# way through to a stranger being trusted with no operator click.
#
# The dedicated cap `federation_open_max_pending` (default 50) was referenced nowhere in the
# package; both doors passed `federation_gossip_max_observed` (default 2000) instead.

def test_setting_the_open_pending_cap_actually_caps_something(monkeypatch, tmp_path,
                                                              resolvable):
    """AIMARKET_FEDERATION_OPEN_MAX_PENDING was documented as this door's cap and read by
    nothing in the package — an operator who set it got silence. It now applies when set."""
    with _hub(
        monkeypatch, tmp_path,
        AIMARKET_FEDERATION_OPEN="1", AIMARKET_FEDERATION_OPEN_MAX_PENDING="2",
    ) as client:
        codes = [
            client.post("/ai-market/v2/federation/announce", json={
                "hub_url": f"https://s{n}.example", "capabilities_count": 0,
            }).status_code
            for n in range(4)
        ]
        assert codes[:2] == [200, 200], codes
        assert 429 in codes[2:], f"the 2-peer cap was never enforced: {codes}"


def test_leaving_the_open_pending_cap_unset_keeps_the_existing_ceiling(monkeypatch, tmp_path,
                                                                       resolvable):
    """No silent tightening: unset, the door keeps the cap it has always enforced."""
    with _hub(
        monkeypatch, tmp_path,
        AIMARKET_FEDERATION_OPEN="1", AIMARKET_FEDERATION_GOSSIP_MAX_OBSERVED="3",
    ) as client:
        codes = [
            client.post("/ai-market/v2/federation/announce", json={
                "hub_url": f"https://u{n}.example", "capabilities_count": 0,
            }).status_code
            for n in range(4)
        ]
        assert codes[:3] == [200, 200, 200], codes
        assert codes[3] == 429, codes


# ── A hub that crawled us before it knocked ─────────────────────────────────────
# Reciprocal discovery files a crawling hub as pending before it ever knocks, and the knock
# then answered "known" and scheduled nothing: the newcomer waited for the next crawl cycle,
# an hour on modelmarket.dev, told `assay_scheduled: false` (end-to-end run, 2026-10-12).


def _stub_assay(monkeypatch):
    import aimarket_hub.federation_assay as fa

    calls: list[str] = []

    async def fake(url, **_kwargs):
        calls.append(url)
        return {"url": url, "verdict": "review"}

    monkeypatch.setattr(fa, "run_assay", fake)
    return calls


def test_the_knock_of_a_hub_already_pending_schedules_its_assay(monkeypatch, tmp_path, resolvable):
    calls = _stub_assay(monkeypatch)
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1",
              AIMARKET_FEDERATION_ASSAY="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_peer(Peer(url=STRANGER, name=STRANGER, trusted=False), status="pending")
        body = client.post(
            "/ai-market/v2/federation/announce", json={"hub_url": STRANGER, "hub_name": "S"},
        ).json()
        assert body["status"] == "known"
        assert body["assay_scheduled"] is True
        assert "assay_url" in body and "stranger.example" in body["assay_url"]
    assert calls == [STRANGER]


def test_knocking_again_buys_no_extra_probe(monkeypatch, tmp_path, resolvable):
    calls = _stub_assay(monkeypatch)
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1",
              AIMARKET_FEDERATION_ASSAY="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_peer(Peer(url=STRANGER, name=STRANGER, trusted=False), status="pending")
        db.save_peer_assay({"url": STRANGER, "verdict": "review",
                            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        body = client.post(
            "/ai-market/v2/federation/announce", json={"hub_url": STRANGER, "hub_name": "S"},
        ).json()
        assert body["assay_scheduled"] is False
    assert calls == []


def test_the_knock_of_an_admitted_hub_schedules_nothing(monkeypatch, tmp_path, resolvable):
    calls = _stub_assay(monkeypatch)
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1",
              AIMARKET_FEDERATION_ASSAY="1") as client:
        client.hub_db.upsert_peer(Peer(url=STRANGER, name="A", trusted=True))  # type: ignore[attr-defined]
        body = client.post(
            "/ai-market/v2/federation/announce", json={"hub_url": STRANGER, "hub_name": "S"},
        ).json()
        assert body["assay_scheduled"] is False
    assert calls == []


def test_deleting_a_peer_removes_what_was_indexed_from_it(tmp_path):
    db = HubDatabase(tmp_path / "hub.db")
    db.upsert_peer(Peer(url=STRANGER, name="A", trusted=True))
    db.upsert_capability(Capability(capability_id="x@v1", product_id="p", name="x",
                                    source_hub=STRANGER, price_per_call_usd=0.0))
    assert db.count_capabilities(source_hub=STRANGER) == 1
    assert db.delete_peer(STRANGER) is True
    assert db.count_capabilities(source_hub=STRANGER) == 0


# ── Both spellings: /.well-known/agent-marketplace and Agent-Marketplace-Crawler ──


def test_the_draft_discovery_document_is_served_beside_the_legacy_one(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        legacy = client.get("/.well-known/ai-market.json").json()
        r = client.get("/.well-known/agent-marketplace")
        assert r.status_code == 200
        draft = r.json()
        assert draft["catalogue_url"] == legacy["manifest_url"]
        assert draft["signer_public_key"] == legacy["signer_public_key"]
        assert draft["protocol_versions"] == legacy["protocol_versions"]
        assert draft["capabilities_count"] == legacy["capabilities_count"]
        assert draft["signature_profile"] == "ed25519-pipe-2"
        assert draft["legacy_discovery_url"].endswith("/.well-known/ai-market.json")
        assert isinstance(draft["peers"], list)
        # HEAD must succeed on the draft path too (the draft says MUST answer GET and HEAD).
        assert client.head("/.well-known/agent-marketplace").status_code == 200


def test_the_draft_document_lists_admitted_peers_by_discovery_uri(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.announce_peer(
            Peer(url="https://draft.example", name="Draft peer",
                 well_known_url="https://draft.example/.well-known/agent-marketplace",
                 depth=1, discoverer="seed"),
            max_pending=10,
        )
        db.announce_peer(
            Peer(url="https://legacy.example", name="Legacy peer",
                 well_known_url="https://legacy.example/.well-known/ai-market.json",
                 depth=1, discoverer="seed"),
            max_pending=10,
        )
        db.promote_pending_peer("https://draft.example")
        db.set_peer_trusted("https://draft.example", True)
        # legacy.example stays PENDING: it must not be listed (admission rule 5).
        draft = client.get("/.well-known/agent-marketplace").json()
        assert draft["peers"] == ["https://draft.example/.well-known/agent-marketplace"]


def test_the_draft_crawler_header_is_read_like_the_legacy_one(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        r = client.get(
            "/.well-known/agent-marketplace",
            headers={"Agent-Marketplace-Crawler": STRANGER, "User-Agent": "federator/0.1"},
        )
        assert r.status_code == 200
        assert _wait_for(lambda: db.count_pending_peers() == 1), "draft header never admitted"
        assert db.get_peer(STRANGER).discoverer == "inbound-crawl"


def test_when_both_headers_arrive_the_legacy_value_wins(monkeypatch, tmp_path, resolvable):
    with _hub(monkeypatch, tmp_path, AIMARKET_FEDERATION_OPEN="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        client.get(
            "/.well-known/ai-market.json",
            headers={"X-AIMarket-Crawler": STRANGER, "Agent-Marketplace-Crawler": "https://other.example"},
        )
        assert _wait_for(lambda: db.count_pending_peers() == 1)
        assert db.get_peer(STRANGER) is not None
        assert db.get_peer("https://other.example") is None


def test_the_draft_path_answers_first_on_a_cold_cache(monkeypatch, tmp_path):
    """Regression: the draft builder used to ask the (non-re-entrant) cache for the legacy
    document from inside the cache's own lock. The first draft request on a cold cache then
    hung forever and took every later well-known request with it."""
    import threading

    with _hub(monkeypatch, tmp_path, AIMARKET_WELL_KNOWN_CACHE_S="60") as client:
        out: dict[str, int] = {}

        def _first_request():
            out["status"] = client.get("/.well-known/agent-marketplace").status_code

        t = threading.Thread(target=_first_request, daemon=True)
        t.start()
        t.join(timeout=20)
        assert not t.is_alive(), "the first draft request on a cold cache hung (cache deadlock)"
        assert out["status"] == 200
        # And the legacy path still answers afterwards.
        assert client.get("/.well-known/ai-market.json").status_code == 200
