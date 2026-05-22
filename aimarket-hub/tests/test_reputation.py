"""Tests for reputation oracle — bonds, signed outcomes, disputes, slashing."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.reputation_oracle import (
    Bond,
    Dispute,
    OutcomeStatus,
    ReputationOracle,
    SignedOutcome,
)
from aimarket_hub.signing import Signer


@pytest.fixture
def signer():
    with tempfile.TemporaryDirectory() as tmp:
        yield Signer(Path(tmp) / "key")


@pytest.fixture
def oracle(signer):
    return ReputationOracle(signer)


class TestBond:
    def test_stake_bond(self, oracle):
        bond = oracle.stake_bond("hub1", 1000.0)
        assert bond.provider_hub == "hub1"
        assert bond.amount_usd == 1000.0
        assert bond.active
        assert bond.remaining_usd == 1000.0

    def test_stake_accumulates(self, oracle):
        oracle.stake_bond("hub1", 100.0)
        oracle.stake_bond("hub1", 50.0)
        bond = oracle.get_bond("hub1")
        assert bond.amount_usd == 150.0

    def test_total_bonded(self, oracle):
        oracle.stake_bond("hub1", 100.0)
        oracle.stake_bond("hub2", 200.0)
        assert oracle.total_bonded_usd() == 300.0

    def test_slash_reduces_remaining(self, oracle):
        bond = oracle.stake_bond("hub1", 1000.0)
        bond.slashed_amount_usd = 300.0
        assert bond.remaining_usd == 700.0


class TestSignedOutcome:
    def test_sign_and_verify(self, signer, oracle):
        outcome = oracle.record_outcome(
            "inv_001", "cap@v1", "p1", "hub1", "consumer1",
            OutcomeStatus.SUCCESS, 0.40, 8000, 0.95,
        )
        assert outcome.signature
        assert outcome.status == OutcomeStatus.SUCCESS
        # Verify with the same signer's public key
        consumer_signer = Signer()  # Different signer for consumer
        outcome2 = SignedOutcome(
            invocation_id="inv_002", capability_id="cap@v1", product_id="p1",
            provider_hub="hub1", consumer_hub="consumer1",
            status=OutcomeStatus.SUCCESS, price_usd=0.40, latency_ms=8000, quality_score=0.95,
        ).sign(consumer_signer)
        assert outcome2.verify(consumer_signer.public_key_b64, consumer_signer)

    def test_canonical_string(self):
        outcome = SignedOutcome(
            invocation_id="inv_001", capability_id="cap@v1", product_id="p1",
            provider_hub="hub1", consumer_hub="c1",
            status=OutcomeStatus.SUCCESS, price_usd=0.40, latency_ms=100, quality_score=0.9,
        )
        canonical = outcome.canonical()
        assert "inv_001" in canonical
        assert "cap@v1" in canonical
        assert "success" in canonical


class TestReputationOracle:
    def test_record_and_retrieve_outcomes(self, oracle):
        oracle.record_outcome("inv_001", "cap@v1", "p1", "hub1", "c1",
                              OutcomeStatus.SUCCESS, 0.40, 100, 0.9)
        oracle.record_outcome("inv_002", "cap@v1", "p1", "hub1", "c1",
                              OutcomeStatus.FAILURE, 0.40, 100, 0.3)
        outcomes = oracle.get_outcomes_for_provider("hub1")
        assert len(outcomes) == 2

    def test_success_rate(self, oracle):
        for i in range(8):
            oracle.record_outcome(f"inv_{i}", "cap@v1", "p1", "hub1", "c1",
                                  OutcomeStatus.SUCCESS, 0.40, 100, 0.9)
        for i in range(2):
            oracle.record_outcome(f"inv_fail_{i}", "cap@v1", "p1", "hub1", "c1",
                                  OutcomeStatus.FAILURE, 0.40, 5000, 0.2)
        rate = oracle.success_rate("hub1")
        assert rate == 0.8

    def test_success_rate_no_data(self, oracle):
        assert oracle.success_rate("unknown_hub") == 0.5

    def test_avg_quality_score(self, oracle):
        oracle.record_outcome("inv_001", "cap@v1", "p1", "hub1", "c1",
                              OutcomeStatus.SUCCESS, 0.40, 100, 0.8)
        oracle.record_outcome("inv_002", "cap@v1", "p1", "hub1", "c1",
                              OutcomeStatus.SUCCESS, 0.40, 100, 1.0)
        assert oracle.avg_quality_score("hub1") == 0.9

    def test_file_dispute(self, oracle):
        oracle.stake_bond("hub1", 1000.0)
        dispute = oracle.file_dispute("inv_001", "hub1", "c1",
                                       "Provider returned garbage output", 0.2)
        assert dispute.dispute_id
        assert dispute.signature

    def test_resolve_dispute_slashes_bond(self, oracle):
        oracle.stake_bond("hub1", 1000.0)
        dispute = oracle.file_dispute("inv_001", "hub1", "c1", "Bad quality", 0.2)
        result = oracle.resolve_dispute(dispute.dispute_id, 0.15)
        assert result["resolved"]
        assert result["slashed_usd"] == pytest.approx(150.0, abs=0.01)
        bond = oracle.get_bond("hub1")
        assert bond.remaining_usd == pytest.approx(850.0, abs=0.01)

    def test_resolve_unknown_dispute(self, oracle):
        result = oracle.resolve_dispute("nonexistent", 0.1)
        assert "error" in result

    def test_dispute_count(self, oracle):
        oracle.stake_bond("hub1", 1000.0)
        oracle.file_dispute("inv_001", "hub1", "c1", "reason 1")
        oracle.file_dispute("inv_002", "hub1", "c1", "reason 2")
        assert oracle.dispute_count("hub1") == 2

    def test_slash_ratio(self, oracle):
        oracle.stake_bond("hub1", 1000.0)
        dispute = oracle.file_dispute("inv_001", "hub1", "c1", "reason", 0.3)
        oracle.resolve_dispute(dispute.dispute_id, 0.3)
        assert oracle.slash_ratio("hub1") == pytest.approx(0.3, abs=0.01)

    def test_compute_reputation_score(self, oracle):
        oracle.stake_bond("hub1", 500.0)
        for i in range(10):
            oracle.record_outcome(f"inv_{i}", "cap@v1", "p1", "hub1", "c1",
                                  OutcomeStatus.SUCCESS, 0.40, 100, 0.95)
        score = oracle.compute_reputation_score("hub1")
        assert 0.0 <= score["score"] <= 1.0
        assert score["bond_usd"] == 500.0
        assert score["success_rate_30d"] == 1.0
        assert score["dispute_count"] == 0

    def test_compute_score_with_slash_penalty(self, oracle):
        oracle.stake_bond("hub1", 500.0)
        for i in range(10):
            oracle.record_outcome(f"inv_{i}", "cap@v1", "p1", "hub1", "c1",
                                  OutcomeStatus.SUCCESS, 0.40, 100, 0.95)
        dispute = oracle.file_dispute("inv_001", "hub1", "c1", "bad", 0.5)
        oracle.resolve_dispute(dispute.dispute_id, 0.5)

        score_with_slash = oracle.compute_reputation_score("hub1")

        # Compare with a clean hub (no slashes)
        oracle2 = ReputationOracle()
        oracle2.stake_bond("hub_clean", 500.0)
        for i in range(10):
            oracle2.record_outcome(f"inv_{i}", "cap@v1", "p1", "hub_clean", "c1",
                                   OutcomeStatus.SUCCESS, 0.40, 100, 0.95)
        score_clean = oracle2.compute_reputation_score("hub_clean")

        # Slashed hub should have lower score than clean hub
        assert score_with_slash["score"] < score_clean["score"]
        assert score_with_slash["slash_ratio"] > 0
