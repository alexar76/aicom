"""Task queue hygiene: dedupe and regressive re-queue guards."""

from __future__ import annotations

import time

from orchestrator.task_queue_hygiene import (
    archive_superseded_failed_tasks,
    enforce_task_queue_hygiene,
    failed_task_may_terminalize_product,
    is_likely_false_failed_product,
    is_regressive_task,
    is_superseded_failed_task,
    pm_spec_requeue_allowed,
    recover_false_failed_products,
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


def test_superseded_pm_failed_on_dev_fixing():
    product = {"id": "p1", "state": "DEV_FIXING", "idea": "landing"}
    task = {
        "status": "failed",
        "agent_type": "pm",
        "state": "SPEC_WRITTEN",
        "error": "Specification failed quality gate after 3 attempts",
        "product_id": "p1",
    }
    assert is_superseded_failed_task(task, product) is True
    assert failed_task_may_terminalize_product(task, product) is False


def test_archive_superseded_failed_tasks_cancels_row():
    products = {"p1": {"id": "p1", "state": "DEV_FIXING", "idea": "x"}}
    task_queue = [
        {
            "id": "t-old",
            "product_id": "p1",
            "agent_type": "pm",
            "state": "SPEC_WRITTEN",
            "status": "failed",
            "error": "Specification failed quality gate",
        }
    ]
    assert archive_superseded_failed_tasks(products, task_queue, time.time()) is True
    assert task_queue[0]["status"] == "cancelled"


def test_false_failed_detected_when_already_terminal(monkeypatch):
    monkeypatch.setattr(
        "web.backend.api.products._product_has_code",
        lambda _pid: True,
    )
    product = {"id": "p1", "state": "FAILED", "idea": "x", "failure_reason": ""}
    task = {
        "id": "t1",
        "product_id": "p1",
        "agent_type": "pm",
        "state": "SPEC_WRITTEN",
        "status": "failed",
        "error": "Specification failed quality gate",
    }
    assert is_likely_false_failed_product(product, [task]) is True
    products = {"p1": product}
    assert recover_false_failed_products(products, [task], time.time()) is True
    assert products["p1"]["state"] == "BUG_FOUND"


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
