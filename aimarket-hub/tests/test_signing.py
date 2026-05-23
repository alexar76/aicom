"""Tests for Ed25519 signing and verification."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import Signer


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
