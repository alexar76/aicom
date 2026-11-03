"""Signing-envelope conformance (F1).

Structural defense against the "some signatures lack replay protection" class: every signed
message canonical in the hub MUST carry a freshness / anti-replay field (nonce, timestamp,
deadline, seq, or generated_at). This test enumerates the signed surfaces and fails if any
canonical lacks one.

When you add a NEW signed message type, add its canonical here. The cost of forgetting is a
red test, not a silent replay vulnerability in production.
"""

from pathlib import Path

import pytest
from aimarket_hub.reputation_oracle import Dispute
from aimarket_hub.signing import Signer
from aimarket_hub.slash_sync import SlashAttestation

# Any one of these tokens in a canonical proves it binds a freshness/replay dimension.
_FRESHNESS_TOKENS = ("nonce:", "timestamp:", "deadline:", "seq:", "ts:", "generated_at:")


def _has_freshness(canonical: str) -> bool:
    return any(tok in canonical for tok in _FRESHNESS_TOKENS)


@pytest.fixture
def signer(tmp_path: Path) -> Signer:
    return Signer(key_path=tmp_path / "key")


def test_every_signed_canonical_carries_a_freshness_field(signer):
    canonicals = {
        "receipt": signer.receipt_canonical(
            {"nonce": "n1", "timestamp": "2026-01-01T00:00:00Z", "product_id": "p", "capability_id": "c"}
        ),
        "manifest": signer.manifest_canonical(
            {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z", "tools": []}
        ),
        "slash_attestation": SlashAttestation(
            issuer_hub="h", provider_hub="a", slashed_usd=1.0, dispute_id="d",
            reason="x", seq=1, timestamp=1700000000.0,
        ).canonical(),
        "dispute": Dispute(
            dispute_id="d", invocation_id="i", provider_hub="a",
            consumer_hub="c", reason="x",
        ).canonical(),
        "verification": signer.verification_canonical(
            {"nonce": "rcpt_n1", "capability_id": "c", "verdict": "passed",
             "verify_score": 0.9, "trace_id": "t1", "timestamp": "2026-01-01T00:00:00Z"}
        ),
    }
    missing = [name for name, c in canonicals.items() if not _has_freshness(c)]
    assert not missing, f"signed canonicals missing an anti-replay/freshness field: {missing}"


def test_freshness_detector_rejects_a_stale_canonical():
    # Guard the guard: a canonical with no freshness token must be flagged.
    assert not _has_freshness("provider:a|amount:5|reason:x")
    assert _has_freshness("provider:a|amount:5|timestamp:123")
