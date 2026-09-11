"""Per-product improvement hold — pauses auto-improvement enqueue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.backend.services.product_followup import (
    is_product_improvement_on_hold,
    normalize_pipeline_followup,
    set_product_improvement_on_hold,
)


def test_set_and_read_improvement_on_hold(tmp_path, monkeypatch):
    state = tmp_path / "state" / "product_followup"
    state.mkdir(parents=True)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_STATE_DIR", str(tmp_path / "state"))

    assert is_product_improvement_on_hold("prod-a") is False
    rec = set_product_improvement_on_hold("prod-a", True)
    assert rec["improvement_on_hold"] is True
    assert rec["improvement_on_hold_at"] is not None
    assert is_product_improvement_on_hold("prod-a") is True

    rec2 = set_product_improvement_on_hold("prod-a", False)
    assert rec2["improvement_on_hold"] is False
    assert is_product_improvement_on_hold("prod-a") is False

    p = state / "prod-a.json"
    assert p.is_file()
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw.get("improvement_on_hold") is False


def test_normalize_includes_improvement_hold_fields():
    n = normalize_pipeline_followup({"improvement_on_hold": True, "improvement_on_hold_at": 1.0})
    assert n["improvement_on_hold"] is True
    assert n["improvement_on_hold_at"] == 1.0


def test_enqueue_market_monitoring_skips_held_product(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AIFACTORY_MARKET_REVISION_INTERVAL_SEC", "1")

    set_product_improvement_on_hold("held-prod", True)

    from orchestrator.worker_components import TaskOrchestrator

    orch = TaskOrchestrator(get_priority=lambda _t: 0)
    products = {
        "held-prod": {"state": "COMPLETED", "idea": "x", "last_market_revision": 0},
        "free-prod": {"state": "COMPLETED", "idea": "y", "last_market_revision": 0},
    }
    task_queue: list = []
    now = 1_000_000.0
    assert orch.enqueue_market_monitoring(products, task_queue, now) is True
    pids = {t["product_id"] for t in task_queue}
    assert "free-prod" in pids
    assert "held-prod" not in pids
