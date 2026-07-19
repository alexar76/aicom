"""
Unit / light integration tests for ``pipeline_worker.PipelineWorker``.

Targets the main risk surface: state recovery, health server, policy audit hook,
and small pure helpers — without running the full agent loop or real LLM calls.
"""

from __future__ import annotations

import asyncio
import json
import socket
from unittest.mock import AsyncMock

import pytest

import web.backend.services.feedback_guardrail as feedback_guardrail
import web.backend.services.policy_audit as policy_audit
from core.delivery_profile import FULL_SOFTWARE, MARKETING_LANDING
from orchestrator.sqlite_manager import SQLiteManager
from orchestrator.worker_utils import (
    delivery_profile_from_product_dict,
    monitoring_refresh_decision,
)
from pipeline_worker import PipelineWorker


def test_monitoring_refresh_decision_false_when_not_requested():
    ok, payload = monitoring_refresh_decision({})
    assert ok is False
    assert payload == {}


def test_monitoring_refresh_decision_true_with_brief():
    ok, payload = monitoring_refresh_decision(
        {
            "request_implementation_refresh": True,
            "implementation_refresh_brief": "Fix checkout",
            "validation": {"x": 1},
        }
    )
    assert ok is True
    assert payload["passed"] is False
    assert "Fix checkout" in payload["demo_quality"]["issues"]
    assert payload["validation_snapshot"] == {"x": 1}


def test_monitoring_refresh_decision_default_issue_when_no_brief():
    ok, payload = monitoring_refresh_decision({"request_implementation_refresh": True})
    assert ok is True
    assert any("analyst monitoring" in s for s in payload["demo_quality"]["issues"])


def test_delivery_profile_explicit_top_level():
    assert delivery_profile_from_product_dict({"delivery_profile": "marketing_landing"}) == MARKETING_LANDING


def test_delivery_profile_from_metadata():
    assert (
        delivery_profile_from_product_dict({"metadata": {"delivery_profile": "full_software"}})
        == FULL_SOFTWARE
    )


def test_worker_get_priority_known_and_default():
    w = PipelineWorker()
    assert w._get_priority("analyst") == 1
    assert w._get_priority("devops") == 8
    assert w._get_priority("unknown_agent_xyz") == 5


def test_compute_content_hash(tmp_path, monkeypatch):
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    pj = state_dir / "pipeline.json"
    pj.write_text('{"hello": "world"}', encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    w = PipelineWorker()
    h = w._compute_content_hash()
    assert len(h) == 64
    assert h == __import__("hashlib").sha256(b'{"hello": "world"}').hexdigest()


def test_state_from_sqlite_snapshot_maps_products(monkeypatch, tmp_path):
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    db = state_dir / "pipeline.db"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(db))

    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {
            "id": "snap-prod",
            "idea": "Snap",
            "state": "idea_received",
            "created_at": 1.0,
            "updated_at": 1.0,
            "metadata": {},
        }
    )
    mgr.close()

    from core.pipeline_state_writer import read_pipeline_state_from_sql

    snap = read_pipeline_state_from_sql()
    assert snap is not None
    assert snap["products"]["snap-prod"]["id"] == "snap-prod"
    assert snap["task_queue"] == []
    assert snap["current_task_id"] is None


def test_load_state_with_recovery_rebuilds_from_sqlite(monkeypatch, tmp_path):
    root = tmp_path / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True)
    db = state_dir / "pipeline.db"
    pj = state_dir / "pipeline.json"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    monkeypatch.setenv("USE_SQLITE", "false")
    # JSON→SQLite recovery is opt-in (avoids silently overwriting a hand-edited
    # pipeline.json); enable it explicitly for this recovery test.
    monkeypatch.setenv("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", "1")

    mgr = SQLiteManager(str(db))
    mgr.connect()
    mgr.upsert_product(
        {
            "id": "rec-prod",
            "idea": "Recovery",
            "state": "completed",
            "created_at": 2.0,
            "updated_at": 2.0,
            "metadata": {},
        }
    )
    mgr.close()

    pj.write_text("{ not valid json", encoding="utf-8")

    w = PipelineWorker()
    state = w._persistence.load_json_with_recovery()
    assert state is not None
    assert "rec-prod" in state.get("products", {})
    repaired = json.loads(pj.read_text(encoding="utf-8"))
    assert "rec-prod" in repaired["products"]


@pytest.mark.asyncio
async def test_health_server_health_and_ready_endpoints(monkeypatch):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    monkeypatch.setenv("AIFACTORY_WORKER_HEALTH_PORT", str(port))
    monkeypatch.setenv("AIFACTORY_WORKER_HEALTH_HOST", "127.0.0.1")

    worker = PipelineWorker()
    await worker._start_health_server()
    assert worker._health_server is not None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        raw = await reader.read()
        assert b"200 OK" in raw
        assert b'"ok"' in raw
        writer.close()
        await writer.wait_closed()

        reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
        writer2.write(b"GET /ready HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer2.drain()
        raw2 = await reader2.read()
        assert b"200 OK" in raw2 or b"503" in raw2
        writer2.close()
        await writer2.wait_closed()
    finally:
        await worker._close_resources()


@pytest.mark.asyncio
async def test_run_policy_audit_early_exit_when_no_state(monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "true")
    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(return_value=None)
    await worker._run_policy_audit_once("test")
    worker._load_state_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_policy_audit_skips_save_when_no_changes(monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setattr(policy_audit, "apply_policy_audit", lambda _p, _t, _n: False)
    monkeypatch.setattr(feedback_guardrail, "apply_feedback_guardrail", lambda _p, _t, _n: False)

    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={"products": {"a": {"id": "a"}}, "task_queue": []}
    )
    save_mock = AsyncMock(return_value=True)
    worker._save_state_async = save_mock

    await worker._run_policy_audit_once("test")
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_run_policy_audit_saves_when_policy_changes(monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setattr(policy_audit, "apply_policy_audit", lambda _p, _t, _n: True)
    monkeypatch.setattr(feedback_guardrail, "apply_feedback_guardrail", lambda _p, _t, _n: False)

    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={"products": {"a": {"id": "a"}}, "task_queue": []}
    )
    save_mock = AsyncMock(return_value=True)
    worker._save_state_async = save_mock

    await worker._run_policy_audit_once("test")
    save_mock.assert_awaited_once()


def test_stop_unblocks_running_flag():
    w = PipelineWorker()
    w._running = True
    w.stop()
    assert w._running is False


@pytest.mark.asyncio
async def test_process_cycle_on_soft_hold_skips_without_save(monkeypatch):
    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: True)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: False)

    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={
            "products": {"p1": {"id": "p1", "state": "SPEC_DRAFTING"}},
            "task_queue": [{"id": "t1", "product_id": "p1", "status": "pending"}],
        }
    )
    save_mock = AsyncMock(return_value=True)
    worker._save_state_async = save_mock

    await worker._process_cycle()
    save_mock.assert_not_called()
    assert worker._has_active_pipeline_work is False


@pytest.mark.asyncio
async def test_process_cycle_on_soft_hold_resets_running_once(monkeypatch):
    monkeypatch.setattr("pipeline_worker.is_factory_on_hold", lambda **kw: True)
    monkeypatch.setattr("pipeline_worker.is_factory_hard_stopped", lambda: False)

    worker = PipelineWorker()
    worker._load_state_async = AsyncMock(
        return_value={
            "products": {"p1": {"id": "p1", "state": "DEV_IN_PROGRESS"}},
            "task_queue": [{"id": "t1", "product_id": "p1", "status": "running"}],
        }
    )
    save_mock = AsyncMock(return_value=True)
    worker._save_state_async = save_mock

    await worker._process_cycle()
    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    assert saved["task_queue"][0]["status"] == "pending"
    assert worker._has_active_pipeline_work is False
