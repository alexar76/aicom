"""Failure reports and reopen-from-FAILED operator flow."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from core.pipeline_retry_limits import pm_spec_auto_requeue_max, task_max_retries
from web.backend.services.pipeline_failure_report import build_failure_report
from web.backend.services.pipeline_reopen import _reopen_json, reopen_failed_product


def test_task_max_retries_default_is_seven():
    assert task_max_retries() >= 7


def test_build_failure_report_spec_gate_human_text():
    product = {
        "state": "FAILED",
        "failure_reason": "Specification failed quality gate: 1) [structure] missing NFR",
    }
    tasks = [
        {
            "status": "failed",
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "error": product["failure_reason"],
            "completed_at": time.time(),
        }
    ]
    report = build_failure_report(product, tasks)
    assert report["headline"] == "Specification quality gate failed"
    assert "quality gates rejected" in report["cause_plain"].lower()
    assert report["suggested_recovery"]["agent_type"] == "pm"
    assert report["failed_agent"] == "pm"


def test_reopen_failed_product_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "1")
    db = tmp_path / "pipeline.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))

    from orchestrator.sqlite_manager import SQLiteManager

    sm = SQLiteManager(str(db))
    sm.connect()
    now = time.time()
    pid = "prod-fail-01"
    sm.upsert_product(
        {
            "id": pid,
            "idea": "Test idea",
            "state": "FAILED",
            "failure_reason": "Specification failed quality gate",
            "created_at": now,
            "updated_at": now,
            "metadata": {},
        }
    )
    sm.upsert_task(
        {
            "id": "task-old-fail",
            "product_id": pid,
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "status": "failed",
            "error": "Specification failed quality gate",
            "created_at": now,
            "retry_count": 0,
        }
    )
    sm.upsert_task(
        {
            "id": "task-stale-pending",
            "product_id": pid,
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "status": "pending",
            "created_at": now,
            "retry_count": 0,
        }
    )
    sm.close()

    res = reopen_failed_product(
        pid,
        "Please rewrite spec with full acceptance criteria for every story.",
    )
    assert res.get("ok") is True
    assert res.get("product_state") == "MARKET_RESEARCHED"
    assert res.get("task_id")

    sm2 = SQLiteManager(str(db))
    sm2.connect()
    product = sm2.get_product(pid)
    assert product["state"] == "MARKET_RESEARCHED"
    assert "failure_reason" not in product or not product.get("failure_reason")
    tasks = sm2.get_tasks_by_product(pid)
    pending_pm = [
        t
        for t in tasks
        if t.get("status") == "pending" and t.get("agent_type") == "pm"
    ]
    assert len(pending_pm) == 1
    cancelled = [t for t in tasks if t.get("status") == "cancelled"]
    assert len(cancelled) >= 1
    sm2.close()


def test_reopen_failed_product_json(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "0")
    pj = tmp_path / "pipeline.json"
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))

    now = time.time()
    pid = "prod-fail-json-01"
    pending_id = "task-stale-pending-json"
    data = {
        "products": {
            pid: {
                "id": pid,
                "idea": "JSON path idea",
                "state": "FAILED",
                "failure_reason": "Specification failed quality gate",
                "created_at": now,
                "updated_at": now,
            }
        },
        "task_queue": [
            {
                "id": "task-old-fail-json",
                "product_id": pid,
                "agent_type": "pm",
                "state": "SPEC_WRITTEN",
                "status": "failed",
                "error": "Specification failed quality gate",
                "created_at": now,
                "retry_count": 0,
            },
            {
                "id": pending_id,
                "product_id": pid,
                "agent_type": "pm",
                "state": "SPEC_WRITTEN",
                "status": "pending",
                "created_at": now,
                "retry_count": 0,
            },
        ],
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    res = reopen_failed_product(
        pid,
        "Rewrite the spec with measurable acceptance criteria.",
    )
    assert res.get("ok") is True
    assert res.get("product_state") == "MARKET_RESEARCHED"
    assert res.get("task_id")

    loaded = json.loads(pj.read_text(encoding="utf-8"))
    product = loaded["products"][pid]
    assert product["state"] == "MARKET_RESEARCHED"
    assert not product.get("failure_reason")
    assert product.get("failed_reopen_count") == 1

    tasks = [t for t in loaded["task_queue"] if t.get("product_id") == pid]
    pending_pm = [t for t in tasks if t.get("status") == "pending" and t.get("agent_type") == "pm"]
    assert len(pending_pm) == 1
    assert pending_pm[0]["id"] == res["task_id"]
    cancelled = [t for t in tasks if t.get("status") == "cancelled"]
    assert any(t.get("id") == pending_id for t in cancelled)


def test_reopen_json_rejects_non_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_SQLITE", "0")
    pj = tmp_path / "pipeline.json"
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pj))
    pid = "prod-active-json"
    data = {
        "products": {pid: {"id": pid, "state": "DEV_FIXING", "idea": "x"}},
        "task_queue": [],
    }
    pj.write_text(json.dumps(data), encoding="utf-8")

    res = _reopen_json(pid, "Operator notes long enough for reopen.", agent_type=None, target_state=None)
    assert res.get("ok") is False
    assert res.get("reason") == "product_not_failed"


def test_auto_requeue_pm_spec_gate_respects_budget():
    from orchestrator.worker_components import QualityManager

    qm = QualityManager(lambda a: 4)
    products = {
        "p1": {
            "state": "FAILED",
            "idea": "x",
            "pm_spec_requeue_count": pm_spec_auto_requeue_max(),
        }
    }
    task_queue: list = []
    task = {
        "agent_type": "pm",
        "product_id": "p1",
        "error": "Specification failed quality gate: structure",
        "status": "failed",
    }
    assert qm.auto_requeue_pm_spec_gate(task, products, task_queue) is False

    products["p1"]["state"] = "MARKET_RESEARCHED"
    products["p1"]["pm_spec_requeue_count"] = 0
    assert qm.auto_requeue_pm_spec_gate(task, products, task_queue) is True
    assert products["p1"]["state"] == "MARKET_RESEARCHED"
    assert len(task_queue) == 1

    products["p1"]["state"] = "DEV_FIXING"
    task_queue.clear()
    assert qm.auto_requeue_pm_spec_gate(task, products, task_queue) is False
    assert len(task_queue) == 0
