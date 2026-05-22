"""Tests for anonymized dataset exporter."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.dataset_exporter import export_dataset, export_all_time
from aimarket_hub.models import InvocationStat


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        database = HubDatabase(db_path)
        # Load with sample data
        for i in range(10):
            database.record_invocation(InvocationStat(
                capability_id=f"cap{i}@v1",
                product_id=f"prod-{i}",
                source_hub="local" if i % 2 == 0 else "https://hub2.example.com",
                price_usd=0.1 * (i + 1),
                latency_ms=100 * i,
                success=i % 3 != 0,
                timestamp=f"2026-05-{20 + i % 3:02d}T12:00:00Z",
            ))
        yield database
        database.close()


class TestDatasetExporter:
    def test_export_creates_file(self, db):
        with tempfile.TemporaryDirectory() as tmp:
            path = export_dataset(db, tmp, week_number=21)
            assert path.exists()
            assert path.suffix == ".jsonl"

    def test_export_is_valid_jsonl(self, db):
        with tempfile.TemporaryDirectory() as tmp:
            path = export_dataset(db, tmp, week_number=21)
            lines = path.read_text().strip().split("\n")
            assert len(lines) > 0
            for line in lines:
                record = json.loads(line)
                assert "week" in record
                assert "capability_id" in record
                assert "price_usd" in record
                assert "protocol_version" in record

    def test_export_anonymizes_ids(self, db):
        with tempfile.TemporaryDirectory() as tmp:
            path = export_dataset(db, tmp, week_number=21)
            lines = path.read_text().strip().split("\n")
            record = json.loads(lines[0])
            # Product IDs should be hashed (12-char hex), not original
            assert record["product_id"] != "prod-0"
            assert len(record["product_id"]) == 12

    def test_export_all_time(self, db):
        with tempfile.TemporaryDirectory() as tmp:
            path = export_all_time(db, tmp)
            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) > 0

    def test_export_no_pii_in_output(self, db):
        db.record_invocation(InvocationStat(
            capability_id="test@v1",
            product_id="prod-email",
            source_hub="local",
            price_usd=0.40,
            latency_ms=100,
            success=True,
            timestamp="2026-05-21T12:00:00Z",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            path = export_dataset(db, tmp, week_number=21)
            content = path.read_text()
            # No emails, no SSN patterns in output
            assert "@" not in content or "[email]" in content
            assert "prod-email" not in content  # Should be hashed

    def test_export_creates_readme(self, db):
        with tempfile.TemporaryDirectory() as tmp:
            export_dataset(db, tmp, week_number=21)
            readme = Path(tmp) / "README-week-21.md"
            assert readme.exists()
            content = readme.read_text()
            assert "AI Market Corpus" in content
            assert "CC-BY 4.0" in content
