"""Product state sync from tasks and JSON merge guards."""

from __future__ import annotations

import time

from orchestrator.pipeline_state_sync import (
    infer_product_state_from_tasks,
    reconcile_product_state,
    sqlite_product_should_keep_over_json,
)


def test_infer_from_qa_tasks():
    tasks = [
        {"agent_type": "pm", "state": "SPEC_WRITTEN", "status": "completed"},
        {"agent_type": "qa", "state": "QA_TESTING", "status": "running"},
    ]
    assert infer_product_state_from_tasks(tasks) == "QA_TESTING"


def test_infer_complete_task():
    tasks = [{"agent_type": "__complete__", "state": "COMPLETED", "status": "completed"}]
    assert infer_product_state_from_tasks(tasks) == "COMPLETED"


def test_reconcile_raises_stale_idea():
    product = {"id": "p1", "state": "IDEA_RECEIVED", "updated_at": time.time()}
    tasks = [{"agent_type": "architect", "state": "ARCH_DESIGNED", "status": "running"}]
    assert reconcile_product_state(product, tasks) is True
    assert product["state"] == "ARCH_DESIGNED"


def test_sqlite_wins_over_stale_json():
    existing = {"state": "QA_TESTING", "updated_at": time.time()}
    incoming = {"state": "IDEA_RECEIVED", "updated_at": time.time() - 3600}
    assert sqlite_product_should_keep_over_json(existing, incoming) is True
