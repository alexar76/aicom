"""m-of-n dispute-ruling quorum (O-1)."""

from pathlib import Path

import pytest
from aimarket_hub.oracle_quorum import RulingQuorum, ruling_canonical
from aimarket_hub.reputation_oracle import Dispute, ReputationOracle
from aimarket_hub.signing import Signer


@pytest.fixture
def setup(tmp_path: Path):
    oracle_signer = Signer(key_path=tmp_path / "oracle")
    authorities = [Signer(key_path=tmp_path / f"auth{i}") for i in range(3)]
    quorum = RulingQuorum(
        authorities=frozenset(a.public_key_b64 for a in authorities),
        threshold=2,
    )
    oracle = ReputationOracle(signer=oracle_signer, quorum=quorum)
    oracle.stake_bond(provider_hub="agent-evil", amount_usd=10_000.0)
    d = Dispute(dispute_id="d1", invocation_id="i", provider_hub="agent-evil",
                consumer_hub="c", reason="x")
    d.signature = oracle_signer.sign_canonical(d.canonical())
    d.consumer_pubkey = oracle_signer.public_key_b64
    oracle.submit_signed_dispute(d)
    return oracle, authorities


def _sig(signer: Signer, dispute_id: str, slash_pct: float, note: str = "confirmed") -> dict:
    canonical = ruling_canonical(dispute_id, slash_pct, note)
    return {"pubkey": signer.public_key_b64, "sig": signer.sign_canonical(canonical)}


def test_no_signatures_blocks_slash(setup):
    oracle, _auth = setup
    res = oracle.resolve_dispute("d1", slash_pct=0.5, ruling_note="confirmed")
    assert res["error"] == "quorum_not_met"
    assert res["valid_signers"] == 0


def test_below_threshold_blocks_slash(setup):
    oracle, auth = setup
    res = oracle.resolve_dispute("d1", slash_pct=0.5, ruling_note="confirmed",
                                 signatures=[_sig(auth[0], "d1", 0.5)])
    assert res["error"] == "quorum_not_met"
    assert res["valid_signers"] == 1


def test_threshold_met_slashes(setup):
    oracle, auth = setup
    res = oracle.resolve_dispute(
        "d1", slash_pct=0.5, ruling_note="confirmed",
        signatures=[_sig(auth[0], "d1", 0.5), _sig(auth[1], "d1", 0.5)],
    )
    assert res.get("resolved") is True
    assert res["slashed_usd"] > 0


def test_unauthorized_signer_does_not_count(setup, tmp_path):
    oracle, auth = setup
    outsider = Signer(key_path=tmp_path / "outsider")
    res = oracle.resolve_dispute(
        "d1", slash_pct=0.5, ruling_note="confirmed",
        signatures=[_sig(auth[0], "d1", 0.5), _sig(outsider, "d1", 0.5)],
    )
    assert res["error"] == "quorum_not_met"
    assert res["valid_signers"] == 1  # outsider ignored


def test_duplicate_authority_counts_once(setup):
    oracle, auth = setup
    res = oracle.resolve_dispute(
        "d1", slash_pct=0.5, ruling_note="confirmed",
        signatures=[_sig(auth[0], "d1", 0.5), _sig(auth[0], "d1", 0.5)],
    )
    assert res["error"] == "quorum_not_met"
    assert res["valid_signers"] == 1


def test_signature_over_wrong_ruling_rejected(setup):
    oracle, auth = setup
    # Authorities signed a DIFFERENT slash_pct than the one being executed.
    res = oracle.resolve_dispute(
        "d1", slash_pct=0.5, ruling_note="confirmed",
        signatures=[_sig(auth[0], "d1", 0.9), _sig(auth[1], "d1", 0.9)],
    )
    assert res["error"] == "quorum_not_met"


def test_from_env_majority_default(monkeypatch):
    keys = ",".join(f"key{i}" for i in range(5))
    monkeypatch.setenv("AIMARKET_ORACLE_AUTHORITIES", keys)
    monkeypatch.delenv("AIMARKET_ORACLE_THRESHOLD", raising=False)
    q = RulingQuorum.from_env()
    assert q is not None
    assert q.threshold == 3  # majority of 5
    monkeypatch.delenv("AIMARKET_ORACLE_AUTHORITIES", raising=False)
    assert RulingQuorum.from_env() is None
