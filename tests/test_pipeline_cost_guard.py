"""Per-product pipeline LLM spend cap."""

from __future__ import annotations

import json

import pytest

from core import pipeline_cost_guard as guard


@pytest.fixture(autouse=True)
def _reset_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    guard.reset_pipeline_cost_state_for_tests()
    yield
    guard.reset_pipeline_cost_state_for_tests()


def test_disabled_when_cap_zero(monkeypatch):
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "0")
    assert guard.pipeline_cost_guard_enabled() is False
    guard.assert_product_within_budget("prod-x")


def test_blocks_when_spend_exceeds_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "1.0")
    guard.record_product_llm_spend("prod-1", 1.5)
    with pytest.raises(guard.PipelineCostBudgetExceeded) as exc:
        guard.assert_product_within_budget("prod-1")
    assert exc.value.product_id == "prod-1"
    assert exc.value.cap_usd == 1.0


def test_ingest_from_jsonl_log(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "10")
    from core.paths import logs_dir

    log_dir = logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "product_id": "prod-jsonl",
        "estimated_cost_usd": 2.5,
    }
    (log_dir / "llm_calls.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    ok, spent, cap = guard.check_product_budget("prod-jsonl")
    assert ok is True
    assert spent == 2.5
    assert cap == 10.0
