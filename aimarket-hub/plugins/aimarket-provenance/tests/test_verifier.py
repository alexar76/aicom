"""Tests for standalone verifier logic."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import Signer
from aimarket_provenance.receipt import ProvenanceReceipt
from aimarket_provenance.verifier import VerificationResult, verify_receipt


@pytest.fixture
def signer() -> Signer:
    with tempfile.TemporaryDirectory() as tmp:
        yield Signer(key_path=str(Path(tmp) / "test_key"))


@pytest.fixture
def valid_receipt(signer) -> ProvenanceReceipt:
    return ProvenanceReceipt.create(
        model_id="claude-sonnet-4@anthropic",
        provider_hub="https://hub.aimarket.org",
        input_payload={"prompt": "Hello"},
        output_payload={"response": "Hi there"},
        signer=signer,
    )


class TestVerifier:
    def test_verify_valid(self, signer, valid_receipt):
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_verify_tampered_signature(self, signer, valid_receipt):
        valid_receipt.proof_value = "tampered"
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is False
        assert any("signature" in e.lower() for e in result.errors)

    def test_verify_missing_model_id(self, signer, valid_receipt):
        valid_receipt.model_id = ""
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is False
        assert any("model_id" in e.lower() for e in result.errors)

    def test_verify_future_timestamp(self, signer, valid_receipt):
        valid_receipt.timestamp = "2099-01-01T00:00:00Z"
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is False
        assert any("future" in e.lower() for e in result.errors)

    def test_verify_invalid_hash_format(self, signer, valid_receipt):
        valid_receipt.input_hash = "short"
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is False
        assert any("hash" in e.lower() for e in result.errors)

    def test_verify_invalid_parent_format(self, signer, valid_receipt):
        valid_receipt.parent_receipts = ["not-a-valid-receipt-id"]
        result = verify_receipt(valid_receipt, signer)
        assert result.valid is False
        assert any("parent" in e.lower() for e in result.errors)

    def test_checks_list_populated(self, signer, valid_receipt):
        result = verify_receipt(valid_receipt, signer)
        check_names = [c["check"] for c in result.checks]
        assert "structure" in check_names
        assert "signature" in check_names
        assert "timestamp" in check_names
        assert "hash_format" in check_names

    def test_to_dict(self, signer, valid_receipt):
        result = verify_receipt(valid_receipt, signer)
        d = result.to_dict()
        assert d["valid"] is True
        assert isinstance(d["checks"], list)
        assert isinstance(d["errors"], list)
