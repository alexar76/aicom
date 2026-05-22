"""Tests for TrustScorer — score computation, weights, edge cases."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import InvocationStat, Peer, ReputationEvent
from aimarket_hub.trust import TrustScorer


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        database = HubDatabase(db_path)
        yield database
        database.close()


class TestTrustScorer:
    def test_local_hub_always_max_score(self, db):
        scorer = TrustScorer(db)
        score = scorer.compute_score("local")
        assert score == 1.0

    def test_unknown_hub_gets_low_score(self, db):
        scorer = TrustScorer(db)
        score = scorer.compute_score("https://unknown.example.com")
        assert 0.0 <= score <= 0.5  # Unknown, no data → low score

    def test_score_increases_with_successful_invocations(self, db):
        scorer = TrustScorer(db)
        hub = "https://good-hub.example.com"
        db.upsert_peer(Peer(
            url=hub, name="Good Hub",
            last_crawl="2026-01-01T00:00:00Z",  # Old hub
        ))

        # Record many successful invocations
        for i in range(50):
            db.record_invocation(InvocationStat(
                capability_id=f"cap{i}@v1",
                product_id=f"prod-{i}",
                source_hub=hub,
                price_usd=1.0,
                latency_ms=100,
                success=True,
                timestamp="2026-05-21T12:00:00Z",
            ))

        score = scorer.compute_score(hub)
        assert score > 0.5, f"Expected > 0.5, got {score}"
        assert score < 1.0  # Not perfect without bond

    def test_score_decreases_with_failures(self, db):
        scorer = TrustScorer(db)
        hub = "https://bad-hub.example.com"
        db.upsert_peer(Peer(
            url=hub, name="Bad Hub",
            last_crawl="2026-05-01T00:00:00Z",
        ))

        # Record many failed invocations
        for i in range(20):
            db.record_invocation(InvocationStat(
                capability_id=f"cap{i}@v1",
                product_id=f"prod-{i}",
                source_hub=hub,
                price_usd=1.0,
                latency_ms=5000,
                success=False,
                timestamp="2026-05-21T12:00:00Z",
            ))

        score = scorer.compute_score(hub)
        assert score < 0.4, f"Expected < 0.4, got {score}"

    def test_high_volume_increases_score(self, db):
        scorer = TrustScorer(db)
        hub = "https://high-volume.example.com"
        db.upsert_peer(Peer(
            url=hub, name="High Volume",
            last_crawl="2026-01-01T00:00:00Z",
        ))

        # High volume, high success
        for i in range(100):
            db.record_invocation(InvocationStat(
                capability_id=f"cap{i}@v1",
                product_id=f"prod-{i}",
                source_hub=hub,
                price_usd=10.0,  # High per-call price
                latency_ms=100,
                success=True,
                timestamp="2026-05-21T12:00:00Z",
            ))

        score = scorer.compute_score(hub)
        assert score > 0.6, f"Expected > 0.6, got {score}"

    def test_empty_hub_neutral_score(self, db):
        scorer = TrustScorer(db)
        hub = "https://new-hub.example.com"
        db.upsert_peer(Peer(
            url=hub, name="New Hub",
            last_crawl="2026-05-21T00:00:00Z",  # Brand new
        ))

        score = scorer.compute_score(hub)
        # New hub with no data gets a low-but-not-zero score
        assert 0.1 <= score <= 0.5, f"Expected 0.1-0.5, got {score}"

    def test_score_details_includes_breakdown(self, db):
        scorer = TrustScorer(db)
        details = scorer.score_details("https://test.example.com")
        assert "trust_score" in details
        assert "weights" in details
        assert "provider_hub" in details
        assert details["weights"]["age"] == 0.2
        assert details["weights"]["bond"] == 0.3
        assert details["weights"]["success_rate"] == 0.35
        assert details["weights"]["volume"] == 0.15

    def test_score_bounded_0_to_1(self, db):
        scorer = TrustScorer(db)
        for hub in ["local", "https://good.example.com", "https://bad.example.com", "https://new.example.com"]:
            if hub != "local":
                db.upsert_peer(Peer(url=hub, name=hub, last_crawl="2026-05-01T00:00:00Z"))
            score = scorer.compute_score(hub)
            assert 0.0 <= score <= 1.0, f"Score {score} out of bounds for {hub}"

    def test_reputation_events_affect_score(self, db):
        scorer = TrustScorer(db)
        hub = "https://reputed.example.com"
        db.upsert_peer(Peer(url=hub, name="Reputed", last_crawl="2026-01-01T00:00:00Z"))

        # Add reputation events
        for i in range(10):
            db.record_reputation_event(ReputationEvent(
                event_type="invocation_success",
                provider_hub=hub,
                capability_id=f"cap{i}@v1",
                timestamp="2026-05-21T12:00:00Z",
                price_usd=5.0,
                latency_ms=100,
                consumer_hub="local",
                signature="test_sig",
            ))

        # Add invocations (these directly affect score)
        for i in range(30):
            db.record_invocation(InvocationStat(
                capability_id=f"cap{i}@v1",
                product_id=f"prod-{i}",
                source_hub=hub,
                price_usd=1.0,
                latency_ms=100,
                success=True,
                timestamp="2026-05-21T12:00:00Z",
            ))

        score = scorer.compute_score(hub)
        assert score > 0.4, f"Expected > 0.4 with reputation events and invocations, got {score}"
