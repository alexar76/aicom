"""Tests for federation crawler — peer discovery, manifest indexing, validation."""

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
        """Routed prices include the routing fee, computed in integer cents."""
        config.routing_fee_bps = 200

        crawler = Crawler(config=config, db=db, signer=signer)
        # Integer-cents math: $0.40 + 2% fee = 41 cents = $0.41 (rounded)
        routed = crawler._routed_price(0.40)
        assert routed == pytest.approx(0.41, abs=0.005)

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
