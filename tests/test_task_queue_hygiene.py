"""Task queue hygiene: dedupe and regressive re-queue guards."""

from __future__ import annotations

import time

from orchestrator.task_queue_hygiene import (
    enforce_task_queue_hygiene,
    is_regressive_task,
    pm_spec_requeue_allowed,
    try_pm_spec_requeue,
)


def test_pm_spec_requeue_not_allowed_after_arch():
    assert pm_spec_requeue_allowed("MARKET_RESEARCHED") is True
    assert pm_spec_requeue_allowed("SPEC_WRITTEN") is True
    assert pm_spec_requeue_allowed("DEV_FIXING") is False
    assert pm_spec_requeue_allowed("DESIGN_CRITIQUED") is False


def test_is_regressive_pm_on_dev_fixing():
    assert is_regressive_task(
        "DEV_FIXING",
        {"agent_type": "pm", "state": "SPEC_WRITTEN"},
    )


def test_enforce_dedupes_multiple_pending():
    products = {"p1": {"id": "p1", "state": "DESIGN_CRITIQUED", "idea": "x"}}
    now = time.time()
    task_queue = [
        {
            "id": "t1",
            "product_id": "p1",
            "agent_type": "pm",
            "state": "MARKET_RESEARCHED",
            "status": "pending",
            "created_at": now - 100,
        },
        {
            "id": "t2",
            "product_id": "p1",
            "agent_type": "developer",
            "state": "CODE_COMMITTED",
            "status": "pending",
            "created_at": now,
        },
    ]
    assert enforce_task_queue_hygiene(products, task_queue, now) is True
    pending = [t for t in task_queue if t.get("status") == "pending"]
    assert len(pending) == 1
    assert pending[0]["agent_type"] == "developer"


def test_try_pm_spec_requeue_skips_advanced_product():
    products = {
        "p1": {
            "id": "p1",
            "state": "DEV_FIXING",
            "idea": "test",
            "pm_spec_requeue_count": 0,
        }
    }
    task_queue: list = []
    task = {
        "agent_type": "pm",
        "product_id": "p1",
        "error": "Specification failed quality gate after 3 attempts",
    }
    assert try_pm_spec_requeue(task, products, task_queue, lambda a: 4) is False
    assert len(task_queue) == 0
