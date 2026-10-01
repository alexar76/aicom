"""Regression: stale failed PM rows must not terminalize advanced products on worker restart."""

from __future__ import annotations

import time

from orchestrator.task_queue_hygiene import (
    archive_superseded_failed_tasks,
    recover_false_failed_products,
)
from orchestrator.worker_components import TaskOrchestrator


def test_retry_failed_old_pm_leaves_dev_fixing_alive():
    """Simulates restart: ancient failed PM row + product already at DEV_FIXING."""
    orch = TaskOrchestrator(lambda _agent: 5)
    now = time.time()
    products = {
        "p1": {
            "id": "p1",
            "state": "DEV_FIXING",
            "idea": "Marketing landing — fitness studio",
        }
    }
    task_queue = [
        {
            "id": "t-old-pm",
            "product_id": "p1",
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "status": "failed",
            "retry_count": 99,
            "max_retries": 7,
            "error": "Specification failed quality gate after 3 attempts",
            "completed_at": now - 86400,
        }
    ]
    assert orch.archive_superseded_failed_tasks(products, task_queue, now) is True
    assert task_queue[0]["status"] == "cancelled"

    products["p1"]["state"] = "DEV_FIXING"
    task_queue[0]["status"] = "failed"
    changed = orch.retry_failed_tasks(products, task_queue, now)
    assert changed is True
    assert products["p1"]["state"] == "DEV_FIXING"
    assert task_queue[0]["status"] == "cancelled"


def test_recover_false_failed_after_wrong_terminalize(monkeypatch):
    orch = TaskOrchestrator(lambda _agent: 5)
    now = time.time()
    products = {
        "p1": {
            "id": "p1",
            "state": "FAILED",
            "idea": "Marketing landing",
            "failure_reason": "",
        }
    }
    task_queue: list = []

    monkeypatch.setattr(
        "web.backend.api.products._product_has_code",
        lambda _pid: True,
    )

    assert recover_false_failed_products(products, task_queue, now) is True
    assert products["p1"]["state"] == "BUG_FOUND"
    assert "failure_reason" not in products["p1"]
