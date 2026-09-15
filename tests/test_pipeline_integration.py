"""
Integration tests for pipeline worker cycles (SQLite, no real LLM).

Covers multi-step agent handoff, dirty-only SQL persistence, and restart-style reads.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import web.backend.services.feedback_guardrail as feedback_guardrail
import web.backend.services.policy_audit as policy_audit
from agents.base_agent import AgentOutput
from orchestrator.async_sqlite_manager import AsyncSQLiteManager
from pipeline_worker import PipelineWorker


def _pipeline_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    state_dir = data_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    db_path = state_dir / "pipeline.db"
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data_root))
    monkeypatch.setenv("AIFACTORY_POLICY_AUDIT_ON_START", "0")
    monkeypatch.setenv("AIFACTORY_PIPELINE_SQL_DIRTY_SAVE", "1")
    return db_path


class _SequenceAgent:
    """Returns predetermined successful outputs per agent_type."""

    def __init__(self, payloads: dict[str, dict] | None = None):
        self._payloads = payloads or {}

    async def execute(self, agent_input):
        agent_type = agent_input.agent_type
        data = self._payloads.get(agent_type, {"ok": True})
        return AgentOutput(
            task_id=agent_input.task_id,
            product_id=agent_input.product_id,
            agent_type=agent_type,
            success=True,
            data=data,
            timestamp=time.time(),
            metrics={},
        )


@pytest.mark.asyncio
async def test_pipeline_cycle_analyst_completes_and_queues_pm(monkeypatch, tmp_path: Path):
    db_path = _pipeline_env(monkeypatch, tmp_path)
    now = time.time()

    sm = AsyncSQLiteManager(str(db_path))
    await sm.initialize()
    await sm.upsert_product(
        {
            "id": "prod-cycle",
            "idea": "SaaS analytics dashboard",
            "state": "IDEA_RECEIVED",
            "created_at": now,
            "updated_at": now,
            "metadata": {},
        }
    )
    await sm.close()

    worker = PipelineWorker()
    worker._agents = {
        "analyst": _SequenceAgent({"analyst": {"market_analysis": "TAM ok"}}),
        "pm": _SequenceAgent({"pm": {"specification": {"product_name": "Dash"}}}),
    }
    await worker._process_cycle()

    state = await worker._load_state_async()
    assert state is not None
    product = state["products"]["prod-cycle"]
    assert product["state"] in ("MARKET_RESEARCHED", "SPEC_WRITTEN")
    tasks = state["task_queue"]
    assert any(
        t.get("agent_type") == "pm" and t.get("status") in ("pending", "running", "completed")
        for t in tasks
    )

    sm2 = AsyncSQLiteManager(str(db_path))
    await sm2.initialize()
    all_tasks = await sm2.get_all_tasks()
    await sm2.close()
    assert any(
        t.get("agent_type") == "analyst" and t.get("status") == "completed" for t in all_tasks
    )


@pytest.mark.asyncio
async def test_pipeline_dirty_save_leaves_untouched_product_timestamp(monkeypatch, tmp_path: Path):
    """After a cycle that only runs one task, dirty SQL save must not rewrite other products."""
    db_path = _pipeline_env(monkeypatch, tmp_path)
    t0 = time.time() - 3600
    t1 = time.time() - 1800

    sm = AsyncSQLiteManager(str(db_path))
    await sm.initialize()
    await sm.upsert_product(
        {
            "id": "prod-active",
            "idea": "Active product",
            "state": "MARKET_RESEARCHED",
            "created_at": t0,
            "updated_at": t0,
            "metadata": {},
        }
    )
    await sm.upsert_product(
        {
            "id": "prod-idle",
            "idea": "Idle product",
            "state": "COMPLETED",
            "created_at": t0,
            "updated_at": t1,
            "metadata": {},
        }
    )
    await sm.upsert_task(
        {
            "id": "task-run",
            "product_id": "prod-active",
            "agent_type": "analyst",
            "status": "running",
            "state": "IDEA_RECEIVED",
            "created_at": t0,
            "started_at": time.time() - 60,
            "completed_at": None,
            "input_data": {},
            "output_data": {},
            "retry_count": 0,
        }
    )
    await sm.close()

    worker = PipelineWorker()
    worker._agents = {"analyst": _SequenceAgent()}
    monkeypatch.setattr(worker, "_enforce_marketplace_readiness", lambda *_a, **_k: False)
    await worker._process_cycle()

    sm2 = AsyncSQLiteManager(str(db_path))
    await sm2.initialize()
    rows = {p["id"]: p for p in await sm2.get_all_products()}
    await sm2.close()

    assert rows["prod-active"]["state"] in ("MARKET_RESEARCHED", "SPEC_WRITTEN")
    assert float(rows["prod-active"]["updated_at"]) > t1
    assert float(rows["prod-idle"]["updated_at"]) == pytest.approx(t1, rel=0, abs=1.0)


@pytest.mark.asyncio
async def test_pipeline_restart_reads_sqlite_task_queue(monkeypatch, tmp_path: Path):
    """Simulate worker restart: second worker instance loads the same queue from SQLite."""
    db_path = _pipeline_env(monkeypatch, tmp_path)
    now = time.time()

    sm = AsyncSQLiteManager(str(db_path))
    await sm.initialize()
    await sm.upsert_product(
        {
            "id": "prod-restart",
            "idea": "Restart test",
            "state": "MARKET_RESEARCHED",
            "created_at": now,
            "updated_at": now,
            "metadata": {},
        }
    )
    await sm.upsert_task(
        {
            "id": "task-pm",
            "product_id": "prod-restart",
            "agent_type": "pm",
            "status": "pending",
            "state": "SPEC_WRITTEN",
            "created_at": now,
            "input_data": {},
            "output_data": {},
            "retry_count": 0,
        }
    )
    await sm.close()

    w1 = PipelineWorker()
    w2 = PipelineWorker()
    state = await w2._load_state_async()
    assert state is not None
    assert "prod-restart" in state["products"]
    assert any(t.get("id") == "task-pm" for t in state["task_queue"])


@pytest.mark.asyncio
async def test_save_state_async_passes_full_save_for_policy_audit(monkeypatch, tmp_path: Path):
    """Policy audit path must request full SQL save (not dirty subset)."""
    _pipeline_env(monkeypatch, tmp_path)
    monkeypatch.setattr(policy_audit, "apply_policy_audit", lambda _p, _t, _n: True)
    monkeypatch.setattr(feedback_guardrail, "apply_feedback_guardrail", lambda _p, _t, _n: False)

    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={"products": {"a": {"id": "a"}}, "task_queue": []}
    )
    save_mock = AsyncMock(return_value=True)
    worker._save_state_async = save_mock

    await worker._run_policy_audit_once("integration-test")
    save_mock.assert_awaited_once()
    _args, kwargs = save_mock.call_args
    assert kwargs.get("sql_full_save") is True
