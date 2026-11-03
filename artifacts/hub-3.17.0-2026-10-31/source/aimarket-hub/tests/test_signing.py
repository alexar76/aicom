"""Tests for Ed25519 signing and verification."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import (
    Signer,
    receipt_signature_version,
    resolve_receipt_version,
    unsigned_receipt_fields,
)


@pytest.fixture
def signer():
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "test_key"
        s = Signer(key_path)
        yield s


class TestSigning:
    def test_generates_keypair(self, signer):
        assert signer.public_key_b64
        assert len(signer.public_key_b64) > 10

    def test_keypair_is_stable(self, signer):
        pk1 = signer.public_key_b64
        pk2 = signer.public_key_b64
        assert pk1 == pk2

    def test_sign_and_verify_roundtrip(self, signer):
        canonical = "test message to sign"
        sig_b64 = signer.sign_canonical(canonical)
        assert signer.verify(signer.public_key_b64, sig_b64, canonical)

    def test_wrong_public_key_fails(self, signer):
        canonical = "test message"
        sig_b64 = signer.sign_canonical(canonical)
        # A valid-length Ed25519 public key different from signer's
        wrong_bytes = b"\x00" * 32
        wrong_pk = __import__("base64").b64encode(wrong_bytes).decode()
        assert not signer.verify(wrong_pk, sig_b64, canonical)

    def test_wrong_message_fails(self, signer):
        canonical = "original message"
        sig_b64 = signer.sign_canonical(canonical)
        assert not signer.verify(signer.public_key_b64, sig_b64, "tampered message")

    def test_sign_manifest(self, signer):
        manifest = {
            "protocol_version": "v1",
            "generated_at": "2026-05-21T12:00:00Z",
            "capabilities_count": 5,
        }
        sig = signer.sign_manifest(manifest)
        assert sig["algorithm"] == "ed25519"
        assert sig["public_key"] == signer.public_key_b64
        assert len(sig["value"]) > 10

    def test_verify_manifest_signature(self, signer):
        manifest = {
            "protocol_version": "v1",
            "generated_at": "2026-05-21T12:00:00Z",
            "capabilities_count": 5,
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        # Verification requires a known pinned pubkey (no self-verifying).
        assert signer.verify_manifest_signature(manifest, signer.public_key_b64)

    def test_verify_manifest_no_known_key_fails(self, signer):
        """Without a pinned pubkey, verification fails (fail-closed)."""
        manifest = {
            "protocol_version": "v1",
            "generated_at": "2026-05-21T12:00:00Z",
            "capabilities_count": 5,
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        assert not signer.verify_manifest_signature(manifest)
        assert not signer.verify_manifest_signature(manifest, "")

    def test_verify_manifest_signature_tampered(self, signer):
        manifest = {
            "protocol_version": "v1",
            "generated_at": "2026-05-21T12:00:00Z",
            "capabilities_count": 5,
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        manifest["capabilities_count"] = 999  # Tampered
        assert not signer.verify_manifest_signature(manifest, signer.public_key_b64)

    def test_sign_receipt(self, signer):
        receipt = {
            "nonce": "rcpt_001",
            "product_id": "prod-001",
            "capability_id": "test@v1",
            "price_usd": 0.40,
            "timestamp": "2026-05-21T12:00:00Z",
        }
        sig = signer.sign_receipt(receipt)
        assert sig["algorithm"] == "ed25519"
        assert len(sig["value"]) > 10

    def test_verify_manifest_no_signature(self, signer):
        manifest = {"protocol_version": "v1", "generated_at": "", "capabilities_count": 0}
        assert not signer.verify_manifest_signature(manifest)


# ── Receipt canonical version: derived from content, not from the call site ──────────
#
# The hub was split-brained about this. `verified_settlement` signed its rejection receipt
# at v2 (so the refund evidence is inside the signature) while
# `safety_gate.build_rejection_receipt` and the api's plugin-block path signed the SAME
# SHAPE of receipt at the v1 default — where every field v1 covers on a rejection is a
# constant, so the signature authenticated which invoke was rejected and nothing about why.


class TestReceiptCanonicalVersioning:
    def test_an_interop_invoke_receipt_stays_on_the_v1_canonical(self, signer):
        """No v2-only field present ⇒ v1, byte-stable, no `version` key. oracle_core,
        platon and the protocol vectors verify this exact 7-field string."""
        receipt = {
            "nonce": "rcpt_001", "product_id": "prod-001", "capability_id": "test@v1",
            "price_usd": 0.40, "timestamp": "2026-05-21T12:00:00Z",
            "success": True, "latency_ms": 12, "list_price_usd": 0.5, "sandbox": True,
        }
        assert resolve_receipt_version(receipt) == 1
        sig = signer.sign_receipt(receipt)
        assert "version" not in sig
        assert sig["value"] == signer.sign_canonical(signer.receipt_canonical(receipt, 1))
        receipt["signature"] = sig
        assert signer.verify_receipt_signature(receipt) is True
        assert receipt_signature_version(receipt) == 1
        assert unsigned_receipt_fields(receipt) == ()

    def test_a_rejection_receipt_is_signed_at_v2_without_the_call_site_asking(self, signer):
        """This is the fix: the safety gate calls `sign_receipt(receipt)` with no version,
        and the reason/category/refund evidence is bound anyway."""
        receipt = {
            "type": "safety_rejection", "product_id": "p", "capability_id": "c",
            "channel_id": "ch_1", "category": "class:illegal",
            "reason": "blocked by provider policy", "refunded": True,
            "timestamp": "2026-07-25T00:00:00Z", "nonce": "safety_1_p",
        }
        assert resolve_receipt_version(receipt) == 2
        receipt["signature"] = signer.sign_receipt(receipt)
        assert receipt["signature"]["version"] == 2
        assert receipt_signature_version(receipt) == 2
        assert signer.verify_receipt_signature(receipt) is True
        for field, tampered in (
            ("reason", "buyer changed their mind"),
            ("category", "class:none"),
            ("refunded", False),
            ("channel_id", "ch_other"),
            ("type", "invoke"),
        ):
            assert signer.verify_receipt_signature({**receipt, field: tampered}) is False, field

    def test_the_v1_default_would_have_left_that_evidence_unsigned(self, signer):
        """Pinning v1 on a rejection is exactly the old behaviour — and it is visibly
        weaker: the reason can be rewritten under a still-valid signature."""
        receipt = {
            "type": "safety_rejection", "product_id": "p", "capability_id": "c",
            "channel_id": "ch_1", "category": "class:illegal", "reason": "policy",
            "refunded": True, "timestamp": "2026-07-25T00:00:00Z", "nonce": "safety_1_p",
        }
        receipt["signature"] = signer.sign_receipt(receipt, version=1)
        assert signer.verify_receipt_signature(
            {**receipt, "reason": "buyer changed their mind", "refunded": False}) is True
        # …and the gap is reportable rather than invisible.
        assert set(unsigned_receipt_fields(receipt)) == {
            "type", "channel_id", "category", "reason", "refunded"}

    def test_a_legacy_v1_signed_rejection_still_verifies(self, signer):
        """Back-compat is non-negotiable: receipts signed before v2 existed carry no
        `version` and must keep verifying against the v1 canonical forever."""
        receipt = {
            "type": "safety_rejection", "product_id": "p", "capability_id": "c",
            "channel_id": "ch_1", "category": "class:illegal", "reason": "policy",
            "refunded": True, "timestamp": "2026-07-25T00:00:00Z", "nonce": "safety_1_p",
        }
        legacy_sig = {
            "algorithm": "ed25519",
            "value": signer.sign_canonical(signer.receipt_canonical(receipt, 1)),
        }
        receipt["signature"] = legacy_sig
        assert "version" not in legacy_sig
        assert receipt_signature_version(receipt) == 1
        assert signer.verify_receipt_signature(receipt) is True

    def test_an_unreadable_or_missing_version_fails_closed(self, signer):
        receipt = {
            "type": "safety_rejection", "reason": "policy", "nonce": "n",
            "timestamp": "t", "refunded": True,
        }
        receipt["signature"] = signer.sign_receipt(receipt)
        good = receipt["signature"]["value"]
        for block in (
            {"algorithm": "ed25519", "value": good, "version": "two"},
            {"algorithm": "ed25519", "value": good, "version": 0},
            {"algorithm": "ed25519", "value": good, "version": None},
            {"algorithm": "ed25519"},
            None,
            "not-a-block",
        ):
            broken = {**receipt, "signature": block}
            assert signer.verify_receipt_signature(broken) is False, block
            assert receipt_signature_version(broken) == 0, block
            assert unsigned_receipt_fields(broken), block

    def test_verification_envelope_version_reading_is_the_same_rule(self, signer):
        env = {"nonce": "rcpt_n1", "capability_id": "c", "verdict": "passed",
               "verify_score": 0.9, "trace_id": "t1", "timestamp": "2026-01-01T00:00:00Z",
               "status": "settled", "settled": True, "audit_score": 0.9,
               "delivery_reasons": ["ok"]}
        env["signature"] = signer.sign_verification(env)
        assert env["signature"]["version"] == 2
        assert signer.verify_verification_signature(env) is True
        assert signer.verify_verification_signature(
            {**env, "signature": {**env["signature"], "version": "two"}}) is False
        assert signer.verify_verification_signature(
            {**env, "delivery_reasons": ["it was terrible"]}) is False
