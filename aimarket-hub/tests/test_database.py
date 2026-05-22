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
        db.record_invocation(InvocationStat(
            capability_id="a@v1", product_id="p1", source_hub="local",
            price_usd=1.0, latency_ms=100, success=True,
            timestamp="2026-05-21T12:00:00Z",
        ))
        db.record_invocation(InvocationStat(
            capability_id="b@v1", product_id="p2", source_hub="local",
            price_usd=2.0, latency_ms=200, success=False,
            timestamp="2026-05-21T12:00:00Z",
        ))
        s = db.stats_summary()
        assert s["total_invocations"] == 2
        assert s["successful_invocations"] == 1
        assert s["avg_price_usd"] == 1.5
        assert s["avg_latency_ms"] == 150.0


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
