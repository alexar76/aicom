"""Tests for ProvenanceStorage — SQLite receipt persistence."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.signing import Signer
from aimarket_provenance.receipt import ProvenanceReceipt
from aimarket_provenance.storage import ProvenanceStorage


@pytest.fixture
def signer() -> Signer:
    with tempfile.TemporaryDirectory() as tmp:
        yield Signer(key_path=str(Path(tmp) / "test_key"))


@pytest.fixture
def storage() -> ProvenanceStorage:
    with tempfile.TemporaryDirectory() as tmp:
        s = ProvenanceStorage(db_path=str(Path(tmp) / "test_provenance.db"))
        yield s
        s.close()


@pytest.fixture
def sample_receipt(signer) -> ProvenanceReceipt:
    return ProvenanceReceipt.create(
        model_id="claude-sonnet-4@anthropic",
        provider_hub="https://hub.aimarket.org",
        input_payload={"prompt": "Hello"},
        output_payload={"response": "Hi there"},
        signer=signer,
    )


class TestStorage:
    def test_store_and_retrieve(self, storage, sample_receipt):
        storage.store(sample_receipt)
        retrieved = storage.get_by_receipt_id(sample_receipt.receipt_id)
        assert retrieved is not None
        assert retrieved.model_id == sample_receipt.model_id
        assert retrieved.input_hash == sample_receipt.input_hash

    def test_store_duplicate_raises(self, storage, sample_receipt):
        storage.store(sample_receipt)
        with pytest.raises(sqlite3.IntegrityError):
            storage.store(sample_receipt)

    def test_get_nonexistent(self, storage):
        assert storage.get_by_receipt_id("urn:uuid:nonexistent") is None

    def test_list_receipts(self, storage, signer):
        for i in range(3):
            r = ProvenanceReceipt.create(
                model_id=f"model-{i}@test",
                provider_hub="https://hub.aimarket.org",
                input_payload={"i": i},
                output_payload={"o": i},
                signer=signer,
            )
            storage.store(r)

        results = storage.list_receipts(limit=10)
        assert len(results) == 3

    def test_list_by_model(self, storage, signer):
        for i in range(2):
            r = ProvenanceReceipt.create(
                model_id="claude-sonnet-4@anthropic",
                provider_hub="https://hub.aimarket.org",
                input_payload={"i": i},
                output_payload={"o": i},
                signer=signer,
            )
            storage.store(r)
        r = ProvenanceReceipt.create(
            model_id="gpt-4o@openai",
            provider_hub="https://hub.aimarket.org",
            input_payload={"x": 1},
            output_payload={"y": 1},
            signer=signer,
        )
        storage.store(r)

        claude_results = storage.list_receipts(model_id="claude-sonnet-4@anthropic")
        assert len(claude_results) == 2
        gpt_results = storage.list_receipts(model_id="gpt-4o@openai")
        assert len(gpt_results) == 1

    def test_list_by_provider(self, storage, signer):
        r1 = ProvenanceReceipt.create(
            model_id="m1@test",
            provider_hub="https://hub1.example.com",
            input_payload={"a": 1},
            output_payload={"a": 1},
            signer=signer,
        )
        r2 = ProvenanceReceipt.create(
            model_id="m2@test",
            provider_hub="https://hub2.example.com",
            input_payload={"b": 1},
            output_payload={"b": 1},
            signer=signer,
        )
        storage.store(r1)
        storage.store(r2)

        assert len(storage.list_receipts(provider_hub="https://hub1.example.com")) == 1
        assert len(storage.list_receipts(provider_hub="https://hub2.example.com")) == 1

    def test_count(self, storage, signer):
        assert storage.count_receipts() == 0
        r = ProvenanceReceipt.create(
            model_id="m@test",
            provider_hub="https://hub.aimarket.org",
            input_payload={"a": 1},
            output_payload={"a": 1},
            signer=signer,
        )
        storage.store(r)
        assert storage.count_receipts() == 1

    def test_stored_receipt_verifies(self, storage, sample_receipt, signer):
        storage.store(sample_receipt)
        retrieved = storage.get_by_receipt_id(sample_receipt.receipt_id)
        assert retrieved is not None
        assert retrieved.verify(signer) is True
