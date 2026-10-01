from __future__ import annotations

import time
from pathlib import Path

import pytest

from agents.base_agent import AgentOutput
from orchestrator.async_sqlite_manager import AsyncSQLiteManager
from pipeline_worker import PipelineWorker


class _FakeAnalystAgent:
    async def execute(self, agent_input):
        return AgentOutput(
            task_id=agent_input.task_id,
            product_id=agent_input.product_id,
            agent_type="analyst",
            success=True,
            data={"market_analysis": "ok"},
            timestamp=time.time(),
            metrics={},
        )


@pytest.mark.asyncio
async def test_full_pipeline_smoke_sqlite(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "data"
    state_dir = data_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = state_dir / "pipeline.db"

    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data_root))
    monkeypatch.setenv("AIFACTORY_POLICY_AUDIT_ON_START", "0")

    sm = AsyncSQLiteManager(str(db_path))
    await sm.initialize()
    await sm.upsert_product(
        {
            "id": "prod-smoke",
            "idea": "Build AI product",
            "state": "IDEA_RECEIVED",
            "created_at": time.time(),
            "updated_at": time.time(),
            "metadata": {},
        }
    )

    worker = PipelineWorker()
    worker._agents = {"analyst": _FakeAnalystAgent()}
    await worker._process_cycle()

    state = await worker._load_state_async()
    assert state is not None
    products = state["products"]
    tasks = state["task_queue"]
    assert "prod-smoke" in products
    assert products["prod-smoke"]["state"] in ("MARKET_RESEARCHED", "SPEC_WRITTEN")
    assert any(t.get("agent_type") == "pm" and t.get("status") in ("pending", "running", "completed") for t in tasks)

    # Persistence verification: restart-style read from SQLite.
    sm2 = AsyncSQLiteManager(str(db_path))
    await sm2.initialize()
    persisted_products = await sm2.get_all_products()
    persisted_tasks = await sm2.get_all_tasks()
    assert any(
        t.get("agent_type") == "analyst" and t.get("status") == "completed" for t in persisted_tasks
    )
    assert any(p.get("id") == "prod-smoke" for p in persisted_products)
    assert any(t.get("product_id") == "prod-smoke" for t in persisted_tasks)
