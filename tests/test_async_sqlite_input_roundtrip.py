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
    await mgr.close()

