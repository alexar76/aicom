"""Tests for pipeline product extras SQLite round-trip."""

from __future__ import annotations

import tempfile
from pathlib import Path

from orchestrator.product_extras import extract_product_extras, merge_product_extras
from orchestrator.sqlite_manager import SQLiteManager


def test_product_extras_sqlite_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pipeline.db"
        mgr = SQLiteManager(str(db))
        mgr.connect()
        product = {
            "id": "prod-test-1",
            "idea": "Test idea",
            "state": "DEV_FIXING",
            "created_at": 1.0,
            "updated_at": 2.0,
            "quality_repair_round": 3,
            "delivery_profile": "marketing_landing",
            "name": "Test Product",
            "metadata": {"spec": {"product_name": "Test Product"}},
        }
        mgr.upsert_product(product)
        loaded = mgr.get_product("prod-test-1")
        assert loaded is not None
        assert loaded.get("quality_repair_round") == 3
        assert loaded.get("delivery_profile") == "marketing_landing"
        assert loaded.get("name") == "Test Product"
        mgr.close()


def test_extract_product_extras():
    extras = extract_product_extras(
        {"id": "x", "quality_repair_round": 2, "state": "DEV_FIXING", "ignored": True}
    )
    assert extras == {"quality_repair_round": 2}
    merged = merge_product_extras({"id": "x"}, extras)
    assert merged["quality_repair_round"] == 2
