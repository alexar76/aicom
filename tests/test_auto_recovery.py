"""Tests for pipeline auto-recovery after QA/dev ping-pong."""

from __future__ import annotations

import time

import pytest

from orchestrator.auto_recovery import try_auto_recovery_after_qa_failure
from web.backend.services.product_pipeline_complete import apply_product_completed_locked


def test_auto_recovery_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "0")
    product = {"id": "p1", "state": "BUG_FOUND", "quality_repair_round": 5}
    task_queue: list = []
    assert not try_auto_recovery_after_qa_failure(product, task_queue, repair_round=5)


def test_auto_recovery_skips_before_min_round(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_MIN_REPAIR_ROUND", "5")
    product = {"id": "p1", "state": "BUG_FOUND"}
    assert not try_auto_recovery_after_qa_failure(product, [], repair_round=3)


def test_auto_recovery_skips_when_operator_locked(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    product = {"id": "p1", "state": "BUG_FOUND", "operator_locked": True}
    assert not try_auto_recovery_after_qa_failure(product, [], repair_round=10)


def test_auto_recovery_completes_on_verify_and_storefront(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_MIN_REPAIR_ROUND", "3")

    product = {"id": "p-recover", "state": "BUG_FOUND", "idea": "test"}
    task_queue = [
        {
            "id": "t-dev",
            "product_id": "p-recover",
            "agent_type": "developer",
            "status": "pending",
            "state": "DEV_FIXING",
        }
    ]

    monkeypatch.setattr(
        "orchestrator.auto_recovery.verify_product_automated",
        lambda pid, **kw: {"passed": True, "product_id": pid},
    )
    monkeypatch.setattr(
        "orchestrator.auto_recovery.refresh_product_storefront_telemetry",
        lambda pid, **kw: {"ok": True, "release_score": 86, "demo_score": 100},
    )

    assert try_auto_recovery_after_qa_failure(product, task_queue, repair_round=4, data_root="/tmp")
    assert product["state"] == "COMPLETED"
    assert product["operator_locked"] is True
    assert product["policy_audit_eligible"] is True
    assert task_queue[0]["status"] == "cancelled"
    complete = next(t for t in task_queue if t.get("agent_type") == "__complete__")
    assert complete["status"] == "completed"


def test_auto_recovery_fails_when_verify_fails(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    product = {"id": "p2", "state": "BUG_FOUND"}
    monkeypatch.setattr(
        "orchestrator.auto_recovery.verify_product_automated",
        lambda pid, **kw: {"passed": False, "reason": "pytest_failed"},
    )
    assert not try_auto_recovery_after_qa_failure(product, [], repair_round=5)


def test_auto_recovery_fails_when_storefront_ineligible(monkeypatch):
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_AUTO_RECOVERY_REQUIRE_STOREFRONT", "1")
    product = {"id": "p3", "state": "BUG_FOUND"}
    monkeypatch.setattr(
        "orchestrator.auto_recovery.verify_product_automated",
        lambda pid, **kw: {"passed": True},
    )
    monkeypatch.setattr(
        "orchestrator.auto_recovery.refresh_product_storefront_telemetry",
        lambda pid, **kw: {"ok": False, "marketplace": {"reasons": ["release_score_low"]}},
    )
    assert not try_auto_recovery_after_qa_failure(product, [], repair_round=5)
    assert product["state"] == "BUG_FOUND"


def test_apply_product_completed_locked_cancels_dev_and_marks_complete():
    now = time.time()
    product = {"id": "p-done", "state": "BUG_FOUND"}
    task_queue = [
        {"id": "d1", "product_id": "p-done", "agent_type": "developer", "status": "running"},
        {"id": "q1", "product_id": "p-done", "agent_type": "qa", "status": "pending"},
    ]
    apply_product_completed_locked(product, task_queue, now=now, reason="test")
    assert product["state"] == "COMPLETED"
    assert product["operator_locked"] is True
    assert all(t["status"] == "cancelled" for t in task_queue[:2])
    complete = next(t for t in task_queue if t.get("agent_type") == "__complete__")
    assert complete["status"] == "completed"
