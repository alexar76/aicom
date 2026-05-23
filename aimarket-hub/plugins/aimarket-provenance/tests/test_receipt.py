"""Tests for ProvenanceReceipt — creation, signing, verification, serialization."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import Signer
from aimarket_provenance.receipt import (
    ProvenanceReceipt,
    compute_hash,
    credential_subject_canonical,
    public_key_from_jwk,
    public_key_to_jwk,
)


@pytest.fixture
def signer() -> Signer:
    """Create a signer with a fresh ephemeral key."""
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "test_key"
        s = Signer(key_path=str(key_path))
        yield s


@pytest.fixture
def sample_input() -> dict:
    return {"prompt": "What is the capital of France?", "temperature": 0.7}


@pytest.fixture
def sample_output() -> dict:
    return {"response": "The capital of France is Paris.", "tokens": 12}


class TestReceiptCreation:
    def test_create_and_sign(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
            hub_name="Test Hub",
            hub_version="1.0.0",
        )
        assert receipt.receipt_id.startswith("urn:uuid:")
        assert receipt.model_id == "claude-sonnet-4@anthropic"
        assert receipt.proof_value
        assert len(receipt.input_hash) == 64
        assert len(receipt.output_hash) == 64
        assert receipt.issuer_public_key_b64

    def test_create_with_parent_receipts(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
            parent_receipts=["urn:uuid:parent-001", "urn:uuid:parent-002"],
        )
        assert len(receipt.parent_receipts) == 2

    def test_create_with_tee_attestation(self, signer, sample_input, sample_output):
        tee = {
            "platform": "AWS_NITRO",
            "enclaveId": "i-test",
            "codeHash": "sha256:abc",
            "timestamp": "2026-05-23T12:00:00Z",
            "signature": "sig_test",
        }
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
            tee_attestation=tee,
        )
        assert receipt.tee_attestation == tee


class TestReceiptVerification:
    def test_verify_valid_receipt(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        assert receipt.verify(signer) is True

    def test_verify_tampered_output_hash(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        receipt.output_hash = "f" * 64
        assert receipt.verify(signer) is False

    def test_verify_tampered_signature(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        receipt.proof_value = "tampered_signature"
        assert receipt.verify(signer) is False

    def test_verify_no_signature(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        receipt.proof_value = ""
        assert receipt.verify(signer) is False

    def test_verify_with_tampered_public_key(self, signer, sample_input, sample_output):
        """Receipt with a different issuer public key should not verify."""
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        with tempfile.TemporaryDirectory() as tmp:
            other_signer = Signer(key_path=str(Path(tmp) / "other_key"))
            # Tamper: swap the embedded public key to the other signer's key
            receipt.issuer_public_key_b64 = other_signer.public_key_b64
            assert receipt.verify(signer) is False


class TestSerialization:
    def test_round_trip_to_dict(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        d = receipt.to_dict()
        r2 = ProvenanceReceipt.from_dict(d)
        assert r2.model_id == receipt.model_id
        assert r2.input_hash == receipt.input_hash
        assert r2.output_hash == receipt.output_hash
        assert r2.proof_value == receipt.proof_value

    def test_round_trip_via_json(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        d = receipt.to_dict()
        j = json.dumps(d)
        r2 = ProvenanceReceipt.from_dict(json.loads(j))
        assert r2.verify(signer) is True

    def test_w3c_vc_structure(self, signer, sample_input, sample_output):
        receipt = ProvenanceReceipt.create(
            model_id="claude-sonnet-4@anthropic",
            provider_hub="https://hub.aimarket.org",
            input_payload=sample_input,
            output_payload=sample_output,
            signer=signer,
        )
        d = receipt.to_dict()
        assert "@context" in d
        assert "id" in d
        assert "type" in d
        assert "VerifiableCredential" in d["type"]
        assert "issuer" in d
        assert "publicKeyJwk" in d["issuer"]
        assert "issuanceDate" in d
        assert "credentialSubject" in d
        assert "proof" in d
        assert d["proof"]["type"] == "Ed25519Signature2018"

    def test_jwk_round_trip(self, signer):
        b64 = signer.public_key_b64
        jwk = public_key_to_jwk(b64)
        assert jwk["kty"] == "OKP"
        assert jwk["crv"] == "Ed25519"
        assert jwk["x"]
        b64_round = public_key_from_jwk(jwk)
        assert b64_round == b64


class TestHelpers:
    def test_compute_hash_deterministic(self):
        data = {"a": 1, "b": 2}
        h1 = compute_hash(data)
        h2 = compute_hash(data)
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_hash_different_data(self):
        h1 = compute_hash({"a": 1})
        h2 = compute_hash({"a": 2})
        assert h1 != h2

    def test_canonical_deterministic(self):
        s1 = {"modelId": "x", "providerHub": "y"}
        c1 = credential_subject_canonical(s1)
        c2 = credential_subject_canonical({"providerHub": "y", "modelId": "x"})
        assert c1 == c2  # sorted keys
