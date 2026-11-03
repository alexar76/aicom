"""The hub's post-quantum verification — the gap that made PQ fields decoration.

`verify_manifest_signature` read only `signature.value`, so a federated peer could publish an
ML-DSA-65 signature and the busiest verification path in the ecosystem never looked at it. These
tests pin the hybrid contract AND the migration order, which is the part that can break a live
federation: a verifier that lags its signers rejects perfectly good traffic.
"""

from __future__ import annotations

import pytest
from aimarket_hub.signing import PQCMisconfigured, Signer, pqc_available, pqc_required

pqc_only = pytest.mark.skipif(not pqc_available(), reason="dilithium-py not installed")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("AIMARKET_PQC_REQUIRE", raising=False)


@pytest.fixture()
def signer(tmp_path):
    return Signer(tmp_path / "hub_key")


def _manifest():
    return {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z",
            "protocol_version": "v2", "tools": [{"name": "t"}]}


def _pq_sign(canonical: str):
    """A peer's ML-DSA-65 signature over the same canonical the hub computes."""
    import base64

    from dilithium_py.ml_dsa import ML_DSA_65

    pk, sk = ML_DSA_65.keygen()
    return (base64.b64encode(pk).decode(),
            base64.b64encode(ML_DSA_65.sign(sk, canonical.encode())).decode())


# ─────────────────────────────────────────── the classical path is untouched


def test_a_classical_manifest_still_verifies(signer):
    m = _manifest()
    m["signature"] = {"algorithm": "ed25519",
                      "value": signer.sign_canonical(signer.manifest_canonical(m))}
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is True


def test_an_unpinned_key_is_still_refused(signer):
    """Unchanged and load-bearing: the key must come from the peer DB, not the signature."""
    m = _manifest()
    m["signature"] = {"value": signer.sign_canonical(signer.manifest_canonical(m))}
    assert signer.verify_manifest_signature(m, "") is False


def test_a_tampered_classical_manifest_fails(signer):
    m = _manifest()
    m["signature"] = {"value": signer.sign_canonical(signer.manifest_canonical(m))}
    m["capabilities_count"] = 99
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is False


def test_require_is_off_by_default():
    """Peers are third parties. Requiring PQ globally would de-federate everyone mid-migration."""
    assert pqc_required() is False


# ─────────────────────────────────────────── hybrid


@pqc_only
def test_a_peers_pq_signature_is_now_actually_checked(signer):
    """The gap. Before this, a wrong pq_value verified fine because nothing read it."""
    m = _manifest()
    canonical = signer.manifest_canonical(m)
    pk, value = _pq_sign(canonical)
    m["signature"] = {"value": signer.sign_canonical(canonical),
                      "pq_algorithm": "ml-dsa-65", "pq_public_key": pk, "pq_value": value}
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is True

    _other_pk, other_value = _pq_sign("a different canonical")
    m["signature"]["pq_value"] = other_value
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is False


@pqc_only
def test_ed25519_is_checked_first_and_still_decides(signer):
    """A valid PQ signature must not rescue an invalid classical one during migration."""
    m = _manifest()
    canonical = signer.manifest_canonical(m)
    pk, value = _pq_sign(canonical)
    m["signature"] = {"value": "AAAA", "pq_public_key": pk, "pq_value": value}
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is False


@pqc_only
def test_a_malformed_pq_field_fails_closed(signer):
    m = _manifest()
    canonical = signer.manifest_canonical(m)
    m["signature"] = {"value": signer.sign_canonical(canonical),
                      "pq_public_key": "not base64 at all!!", "pq_value": "also not"}
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is False


# ─────────────────────────────────────────── phase 3: require


@pqc_only
def test_stripping_the_pq_fields_is_refused_once_pq_is_required(signer):
    """The downgrade attack, on the federated path."""
    m = _manifest()
    canonical = signer.manifest_canonical(m)
    m["signature"] = {"value": signer.sign_canonical(canonical)}
    assert signer.verify_hybrid(signer.public_key_b64, m["signature"], canonical,
                                require_pq=False) is True
    assert signer.verify_hybrid(signer.public_key_b64, m["signature"], canonical,
                                require_pq=True) is False


@pqc_only
def test_require_can_be_set_per_peer_not_only_globally(signer, monkeypatch):
    """Mid-migration a hub needs to demand PQ from peers that HAVE migrated while still
    accepting the ones that have not."""
    monkeypatch.setenv("AIMARKET_PQC_REQUIRE", "1")
    m = _manifest()
    canonical = signer.manifest_canonical(m)
    classical = {"value": signer.sign_canonical(canonical)}
    assert signer.verify_hybrid(signer.public_key_b64, classical, canonical) is False
    assert signer.verify_hybrid(signer.public_key_b64, classical, canonical,
                                require_pq=False) is True


def test_requiring_pq_without_the_library_is_loud(signer, monkeypatch):
    """A hub that demands proof it cannot evaluate is broken, not strict — and a silent False
    would blame every peer for a local install problem."""
    import aimarket_hub.signing as mod

    monkeypatch.setattr(mod, "_PQ_LIB", False)
    with pytest.raises(PQCMisconfigured, match="dilithium-py"):
        signer.verify_hybrid(signer.public_key_b64, {"value": "x"}, "canon", require_pq=True)


def test_a_pq_signed_manifest_is_refused_by_a_hub_without_the_library(signer, monkeypatch):
    """THE migration-order rule, as a test: a verifier that lags its signers rejects good
    traffic. This is why the [pqc] extra must reach every hub BEFORE any peer signs hybrid."""
    import aimarket_hub.signing as mod

    m = _manifest()
    canonical = signer.manifest_canonical(m)
    m["signature"] = {"value": signer.sign_canonical(canonical),
                      "pq_algorithm": "ml-dsa-65", "pq_public_key": "AAAA", "pq_value": "AAAA"}
    monkeypatch.setattr(mod, "_PQ_LIB", False)
    assert signer.verify_manifest_signature(m, signer.public_key_b64) is False


# ─────────────────────────────── pinning the peer's PQ identity (phase-3 prerequisite)


def _hybrid(signer, manifest: dict) -> tuple[dict, str, str]:
    """A manifest the hub signed classically, augmented with a real ML-DSA signature.

    Built here rather than by the hub's own signer because the hub SIGNS classically only — the
    PQ signature on the wire comes from a migrated peer, not from us.
    """
    import base64

    from dilithium_py.ml_dsa import ML_DSA_65

    signed = dict(manifest)
    signed["signature"] = signer.sign_manifest(manifest)
    canonical = signer.manifest_canonical(signed)
    pk, sk = ML_DSA_65.keygen()
    signed["signature"]["pq_algorithm"] = "ml-dsa-65"
    signed["signature"]["pq_public_key"] = base64.b64encode(pk).decode()
    signed["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(sk, canonical.encode())).decode()
    return signed, canonical, signed["signature"]["pq_public_key"]


@pqc_only
def test_pinned_peer_pq_key_accepts_that_peer(signer):
    signed, _canonical, pq_key = _hybrid(signer, _manifest())
    assert signer.verify_manifest_signature(signed, signer.public_key_b64, pq_key)


@pqc_only
def test_pinned_peer_pq_key_refuses_a_substituted_one(signer):
    import base64

    from dilithium_py.ml_dsa import ML_DSA_65

    signed, canonical, pq_key = _hybrid(signer, _manifest())

    forged = {k: dict(v) if isinstance(v, dict) else v for k, v in signed.items()}
    pk2, sk2 = ML_DSA_65.keygen()
    forged["signature"]["pq_public_key"] = base64.b64encode(pk2).decode()
    forged["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(sk2, canonical.encode())).decode()

    # Unpinned, the swap is accepted: the PQ signature is valid for the key it names. Recording
    # this keeps the suite honest about what today's deployment does and does not prove.
    assert signer.verify_manifest_signature(forged, signer.public_key_b64) is True
    # Pinned, it is refused.
    assert signer.verify_manifest_signature(forged, signer.public_key_b64, pq_key) is False


@pqc_only
def test_pinning_never_substitutes_for_the_ed25519_pin(signer):
    """An unpinned classical key still fails closed, PQ key pinned or not."""
    signed, _canonical, pq_key = _hybrid(signer, _manifest())
    assert signer.verify_manifest_signature(signed, "", pq_key) is False


# ─────────────────────────────── durable economic evidence is hybrid too


@pqc_only
def test_receipt_is_hybrid_and_both_layers_are_checked(tmp_path):
    signer = Signer(tmp_path / "receipt-key", pqc=True)
    receipt = {
        "nonce": "rcpt_1", "product_id": "echo", "capability_id": "echo@v1",
        "price_usd": 0.4, "timestamp": "2026-09-08T00:00:00Z",
        "success": True, "latency_ms": 12,
    }
    receipt["signature"] = signer.sign_receipt(receipt)
    assert receipt["signature"]["pq_algorithm"] == "ml-dsa-65"
    assert receipt["signature"]["pq_public_key"] == signer.pq_public_key_b64
    assert signer.verify_receipt_signature(receipt) is True

    broken = {**receipt, "signature": {**receipt["signature"], "pq_value": "AAAA"}}
    assert signer.verify_receipt_signature(broken) is False


@pqc_only
def test_browser_zero_price_round_trip_keeps_hybrid_receipt_valid(tmp_path):
    """JavaScript has one Number type: JSON.parse('0.0') then stringify emits '0'.

    The old Python-repr canonical made every free browser receipt fail when posted
    back to the verifier even though local Ed25519 (which tried both spellings) passed.
    """
    signer = Signer(tmp_path / "browser-key", pqc=True)
    signed = {
        "nonce": "rcpt_browser", "product_id": "echo",
        "capability_id": "echo@v1", "price_usd": 0.0,
        "timestamp": "2026-09-08T00:00:00Z", "success": True,
        "latency_ms": 7,
    }
    signed["signature"] = signer.sign_receipt(signed)
    browser_round_trip = {**signed, "price_usd": 0}
    assert signer.verify_receipt_signature(browser_round_trip) is True
    assert len(signer.receipt_canonical_candidates(browser_round_trip, 1)) == 2


@pqc_only
def test_receipt_pq_key_is_pinned_to_the_hub_identity(tmp_path):
    import base64
    from dilithium_py.ml_dsa import ML_DSA_65

    signer = Signer(tmp_path / "receipt-key", pqc=True)
    receipt = {
        "nonce": "rcpt_2", "product_id": "echo", "capability_id": "echo@v1",
        "price_usd": 0.0, "timestamp": "2026-09-08T00:00:00Z",
        "success": True, "latency_ms": 4,
    }
    receipt["signature"] = signer.sign_receipt(receipt)
    canonical = signer.receipt_canonical(receipt, 1)
    attacker_pk, attacker_sk = ML_DSA_65.keygen()
    receipt["signature"]["pq_public_key"] = base64.b64encode(attacker_pk).decode()
    receipt["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(attacker_sk, canonical.encode())
    ).decode()
    assert signer.verify_receipt_signature(receipt) is False


@pqc_only
def test_verification_envelope_is_hybrid_and_downgrade_fails(tmp_path, monkeypatch):
    signer = Signer(tmp_path / "verification-key", pqc=True)
    envelope = {
        "nonce": "rcpt_3", "capability_id": "guard@v1", "verdict": "passed",
        "verify_score": 0.96, "trace_id": "trace_3",
        "timestamp": "2026-09-08T00:00:00Z", "status": "settled",
        "verified": True, "settled": True, "delivery_fulfils": True,
        "delivery_reasons": ["matches intent"], "audit_score": 0.97,
        "threshold": 0.9,
    }
    envelope["signature"] = signer.sign_verification(envelope)
    assert envelope["signature"]["pq_algorithm"] == "ml-dsa-65"
    assert signer.verify_verification_signature(envelope) is True

    stripped = {**envelope, "signature": {
        key: value for key, value in envelope["signature"].items()
        if not key.startswith("pq_")
    }}
    # Migration-compatible by default, but impossible to downgrade once this hub's
    # policy requires post-quantum proof.
    assert signer.verify_verification_signature(stripped) is True
    monkeypatch.setenv("AIMARKET_PQC_REQUIRE", "1")
    assert signer.verify_verification_signature(stripped) is False
