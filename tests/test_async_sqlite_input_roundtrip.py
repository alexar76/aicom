from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.async_sqlite_manager import AsyncSQLiteManager


@pytest.mark.asyncio
async def test_async_sqlite_roundtrip_preserves_input_data(tmp_path: Path):
    db = tmp_path / "pipeline.db"
    mgr = AsyncSQLiteManager(str(db))
    await mgr.initialize()
    await mgr.upsert_task(
        {
            "id": "task-1",
            "product_id": "prod-1",
            "agent_type": "pm",
            "status": "pending",
            "state": "SPEC_WRITTEN",
            "created_at": 1.0,
            "input_data": {"idea": "x", "clarification_pack": {"q": ["a"]}},
            "output_data": {},
            "retry_count": 0,
            "priority": 1,
        }
    )
    tasks = await mgr.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0]["input_data"].get("idea") == "x"
    assert isinstance(tasks[0]["input_data"].get("clarification_pack"), dict)
    # Retry ceiling comes from config (default 7), not a hardcoded 3.
    assert tasks[0]["max_retries"] == 7
    await mgr.close()


@pytest.mark.asyncio
async def test_async_sqlite_roundtrip_preserves_extras_and_generic(tmp_path: Path):
    db = tmp_path / "pipeline.db"
    mgr = AsyncSQLiteManager(str(db))
    await mgr.initialize()
    await mgr.upsert_product(
        {
            "id": "prod-1",
            "idea": "an idea",
            "state": "COMPLETED",
            "created_at": 1.0,
            "updated_at": 2.0,
            "metadata": {"category": "saas"},
            "delivery_profile": "managed",   # PRODUCT_EXTRA_KEYS → extras column
            "operator_locked": True,         # PRODUCT_EXTRA_KEYS → extras column
            "owner_email": "a@b.co",         # PRODUCT_EXTRA_KEYS → extras column
            "roadmap_v2": {"phase": 1},      # unknown field → generic_metadata column
        }
    )
    products = await mgr.get_all_products()
    assert len(products) == 1
    p = products[0]
    assert p["delivery_profile"] == "managed"
    assert p["operator_locked"] is True
    assert p["owner_email"] == "a@b.co"
    assert p["roadmap_v2"] == {"phase": 1}  # generic_metadata survived the round-trip
    await mgr.close()

