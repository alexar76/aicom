"""Tests for extracted pipeline state persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.pipeline_worker_persistence import PipelineStatePersistence
from orchestrator.sqlite_manager import SQLiteManager


@pytest.mark.asyncio
async def test_save_json_compact_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data" / "state"
    root.mkdir(parents=True)
    pj = root / "pipeline.json"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.setenv("AIFACTORY_PIPELINE_JSON_COMPACT", "1")

    p = PipelineStatePersistence(use_sql_store=False)
    ok = await p.save_async({"products": {}, "task_queue": [], "current_task_id": None})
    assert ok is True
    raw = pj.read_text()
    assert "\n  " not in raw  # compact JSON (no indented pretty-print)


def test_load_json_with_recovery_from_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    db = state_dir / "pipeline.db"
    pj = state_dir / "pipeline.json"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))

    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {
            "id": "p-persist",
            "idea": "x",
            "state": "IDEA_RECEIVED",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        }
    )
    mgr.close()

    pj.write_text("{bad", encoding="utf-8")
    import os
    import time as _time

    os.utime(pj, (1, 1))
    os.utime(db, (_time.time() + 100, _time.time() + 100))
    monkeypatch.setenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", "1")
    p = PipelineStatePersistence(state_file=pj, use_sql_store=False)
    state = p.load_json_with_recovery()
    assert state is not None
    assert "p-persist" in state["products"]


@pytest.mark.asyncio
async def test_save_async_sql_dirty_upserts_subset_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_PIPELINE_SQL_DIRTY_SAVE", "1")
    store = MagicMock()
    store.upsert_product = AsyncMock()
    store.upsert_task = AsyncMock()

    p = PipelineStatePersistence(use_sql_store=True)
    p._async_store = store

    state = {
        "products": {
            "p1": {"id": "p1", "idea": "a", "state": "IDEA_RECEIVED"},
            "p2": {"id": "p2", "idea": "b", "state": "IDEA_RECEIVED"},
        },
        "task_queue": [
            {"id": "t1", "product_id": "p1", "agent_type": "pm", "status": "running"},
            {"id": "t2", "product_id": "p2", "agent_type": "pm", "status": "pending"},
        ],
        "_dirty_product_ids": ["p1"],
        "_dirty_task_ids": ["t1"],
    }
    ok = await p.save_async(state)
    assert ok is True
    assert store.upsert_product.await_count == 1
    assert store.upsert_product.await_args.args[0]["id"] == "p1"
    assert store.upsert_task.await_count == 1
    assert store.upsert_task.await_args.args[0]["id"] == "t1"


@pytest.mark.asyncio
async def test_save_async_sql_full_save_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_PIPELINE_SQL_DIRTY_SAVE", "1")
    store = MagicMock()
    store.upsert_product = AsyncMock()
    store.upsert_task = AsyncMock()

    p = PipelineStatePersistence(use_sql_store=True)
    p._async_store = store

    state = {
        "products": {"p1": {"id": "p1"}, "p2": {"id": "p2"}},
        "task_queue": [{"id": "t1"}, {"id": "t2"}],
        "_sql_full_save": True,
        "_dirty_product_ids": ["p1"],
    }
    ok = await p.save_async(state)
    assert ok is True
    assert store.upsert_product.await_count == 2
    assert store.upsert_task.await_count == 2
