"""Tests for HubDatabase — capability CRUD, peers, stats, reputation."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability, InvocationStat, Peer, ReputationEvent


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        database = HubDatabase(db_path)
        yield database
        database.close()


class TestCapabilities:
    def test_upsert_and_get(self, db):
        cap = Capability(
            capability_id="translate.multi@v2",
            product_id="prod-001",
            name="translate.multi",
            version="v2",
            description="Translate text to multiple locales",
            price_per_call_usd=0.40,
            p50_latency_ms=8100,
            source_hub="https://hub2.example.com",
            source_hub_name="Test Hub 2",
            trust_score=0.85,
        )
        db.upsert_capability(cap)

        retrieved = db.get_capability("prod-001", "translate.multi@v2", "https://hub2.example.com")
        assert retrieved is not None
        assert retrieved.price_per_call_usd == 0.40
        assert retrieved.source_hub == "https://hub2.example.com"
        assert retrieved.trust_score == 0.85

    def test_upsert_replaces(self, db):
        cap1 = Capability(capability_id="test@v1", product_id="p1", name="test")
        db.upsert_capability(cap1)
        cap2 = Capability(capability_id="test@v1", product_id="p1", name="test", price_per_call_usd=0.99)
        db.upsert_capability(cap2)
        retrieved = db.get_capability("p1", "test@v1")
        assert retrieved.price_per_call_usd == 0.99

    def test_list_all(self, db):
        for i in range(5):
            db.upsert_capability(Capability(
                capability_id=f"cap{i}@v1", product_id=f"prod-{i}", name=f"cap{i}",
            ))
        caps = db.list_capabilities()
        assert len(caps) == 5

    def test_list_by_source(self, db):
        db.upsert_capability(Capability(capability_id="a@v1", product_id="p1", name="a", source_hub="hub1"))
        db.upsert_capability(Capability(capability_id="b@v1", product_id="p2", name="b", source_hub="hub2"))
        db.upsert_capability(Capability(capability_id="c@v1", product_id="p3", name="c", source_hub="hub1"))
        caps = db.list_capabilities(source_hub="hub1")
        assert len(caps) == 2

    def test_count_capabilities(self, db):
        db.upsert_capability(Capability(capability_id="a@v1", product_id="p1", name="a", source_hub="local"))
        db.upsert_capability(Capability(capability_id="b@v1", product_id="p2", name="b", source_hub="hub2"))
        assert db.count_capabilities() == 2
        assert db.count_capabilities("local") == 1
        assert db.count_federated() == 1

    def test_search(self, db):
        db.upsert_capability(Capability(
            capability_id="translate.multi@v2", product_id="p1", name="translate.multi",
            description="Translate text to multiple languages",
        ))
        db.upsert_capability(Capability(
            capability_id="legal.review@v1", product_id="p2", name="legal.review",
            description="Review legal documents",
        ))
        results = db.search_capabilities("translate")
        assert len(results) == 1
        assert results[0].name == "translate.multi"

    def test_clear_federated(self, db):
        db.upsert_capability(Capability(capability_id="a@v1", product_id="p1", name="a", source_hub="local"))
        db.upsert_capability(Capability(capability_id="b@v1", product_id="p2", name="b", source_hub="hub2"))
        db.clear_federated()
        assert db.count_capabilities() == 1
        assert db.count_federated() == 0


class TestPeers:
    def test_upsert_and_list(self, db):
        peer = Peer(url="https://hub1.example.com", name="Hub 1", capabilities_count=5, trust_score=0.9)
        db.upsert_peer(peer)
        peers = db.list_peers()
        assert len(peers) == 1
        assert peers[0].name == "Hub 1"

    def test_get_peer(self, db):
        db.upsert_peer(Peer(url="https://hub1.example.com", name="Hub 1"))
        peer = db.get_peer("https://hub1.example.com")
        assert peer is not None
        assert peer.name == "Hub 1"

    def test_peer_count(self, db):
        assert db.peer_count() == 0
        db.upsert_peer(Peer(url="https://hub1.example.com", name="Hub 1"))
        db.upsert_peer(Peer(url="https://hub2.example.com", name="Hub 2"))
        assert db.peer_count() == 2


class TestStats:
    def test_record_and_list(self, db):
        stat = InvocationStat(
            capability_id="test@v1", product_id="p1", source_hub="local",
            price_usd=0.40, latency_ms=100, success=True,
            timestamp="2026-05-21T12:00:00Z",
        )
        db.record_invocation(stat)
        stats = db.recent_stats(limit=10)
        assert len(stats) == 1
        assert stats[0]["price_usd"] == 0.40
        assert stats[0]["success"] == 1

    def test_summary(self, db):
        import time
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.record_invocation(InvocationStat(
            capability_id="a@v1", product_id="p1", source_hub="local",
            price_usd=1.0, latency_ms=100, success=True,
            timestamp=now_iso,
        ))
        db.record_invocation(InvocationStat(
            capability_id="b@v1", product_id="p2", source_hub="local",
            price_usd=2.0, latency_ms=200, success=False,
            timestamp=now_iso,
        ))
        s = db.stats_summary()
        assert s["total_invocations"] == 2
        assert s["successful_invocations"] == 1
        assert s["avg_price_usd"] == 1.5
        assert s["avg_latency_ms"] == 150.0
        assert s["failed_invocations_24h"] == 1
        assert s["invocations_24h"] == 2
        assert s["volume_24h_usd"] == 3.0
        assert s["volume_total_usd"] == 3.0
        assert s["success_rate"] == 0.5
        assert s["refused_invocations"] == 0

    def test_incomplete_input_is_not_a_failed_percent(self, db):
        import time
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.record_invocation(InvocationStat(
            capability_id="atlas.nearest.read@v1", product_id="atlas.products",
            source_hub="https://atlas.modelmarket.dev",
            price_usd=0, latency_ms=800, success=False, outcome="refused",
            timestamp=now_iso,
        ))
        db.record_invocation(InvocationStat(
            capability_id="atlas.nearest.read@v1", product_id="atlas.products",
            source_hub="https://atlas.modelmarket.dev",
            price_usd=0.03, latency_ms=200, success=True, outcome="ok",
            timestamp=now_iso,
        ))
        s = db.stats_summary()
        assert s["total_invocations"] == 2
        assert s["successful_invocations"] == 1
        assert s["refused_invocations"] == 1
        assert s["failed_invocations"] == 0
        assert s["success_rate"] == 1.0
        assert s["failed_invocations_24h"] == 0
        row = db.recent_stats(limit=5)
        assert {r["outcome"] for r in row} == {"ok", "refused"}

    def test_volume_is_windowed_like_the_counters(self, db):
        """A consumer asking for "volume over 24h" must not have to use a lifetime figure.

        The only volume this summary used to carry came from the channel ledger
        (`settled_volume_usd`), which has no time window at all — so the ecosystem monitor
        printed an all-time total in a cell labelled "VOLUME 24H".
        """
        import time
        now = time.time()
        fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 600))
        stale = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 10 * 86400))
        db.record_invocation(InvocationStat(
            capability_id="a@v1", product_id="p1", source_hub="local",
            price_usd=0.25, latency_ms=10, success=True, timestamp=fresh,
        ))
        db.record_invocation(InvocationStat(
            capability_id="b@v1", product_id="p2", source_hub="local",
            price_usd=5.00, latency_ms=10, success=True, timestamp=stale,
        ))
        s = db.stats_summary()
        assert s["invocations_24h"] == 1
        assert s["volume_24h_usd"] == 0.25
        assert s["volume_total_usd"] == 5.25


class TestReputation:
    def test_record_and_list(self, db):
        event = ReputationEvent(
            event_type="invocation_success",
            provider_hub="https://hub2.example.com",
            capability_id="test@v1",
            timestamp="2026-05-21T12:00:00Z",
            price_usd=0.40,
            latency_ms=100,
            consumer_hub="local",
            signature="test_sig",
        )
        db.record_reputation_event(event)
        events = db.reputation_events_for("https://hub2.example.com")
        assert len(events) == 1
        assert events[0].event_type == "invocation_success"


class TestOfferableInStats:
    def test_stats_summary_separates_offerable_from_table_count(self, db):
        """The storefront number must exclude local rows the hub cannot execute.

        modelmarket.dev advertised "12 capabilities" for a day while `/manifest` and
        `/search` — which filter on an execution path — served none of them. The landing
        card read `capabilities_count`, i.e. COUNT(*) of the table, and the twelve rows
        were the seeded showcase: no `invoke_url`, no static pack, unfulfillable by
        construction. `offerable_capabilities_count` is the same figure the manifest uses.
        """
        db.upsert_capability(Capability(
            capability_id="demo@v1", product_id="seed", name="demo",
            invoke_url="", prompt_template="", is_demo=True,
        ))
        db.upsert_capability(Capability(
            capability_id="real@v1", product_id="prod", name="real",
            invoke_url="https://factory.example.com/invoke/real",
        ))
        db.upsert_capability(Capability(
            capability_id="peer@v1", product_id="oracle", name="peer",
            source_hub="https://oracles.example.com", invoke_url="",
        ))

        s = db.stats_summary()
        assert s["capabilities_count"] == 3          # the table, warts and all
        assert s["offerable_capabilities_count"] == 2  # federated row + the executable local one
        assert s["offerable_capabilities_count"] == db.count_offerable()
        assert s["federated_capabilities_count"] == 1
        assert s["demo_capabilities_count"] == 1
        assert s["real_local_capabilities_count"] == 1
