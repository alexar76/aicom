"""A money limit is a pause condition, not a verdict on the product.

The failure this closes, measured on production: the LLM cap tripped at $11.0105 against $11.00, the
product went to terminal FAILED, its QA task was cancelled, and the worker looped "Factory on hold"
every two seconds for 45 minutes — a log that looks alive and does nothing. Raising the cap resumed
nothing, because the idle-healer skips FAILED by design; a human had to notice the silence and
hand-edit the state back to DEV_FIXING.

Now the park is loud, the way back is recorded, and the worker resumes it the moment headroom exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator import task_queue_hygiene as tqh

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def guard(monkeypatch):
    state = {"cap": 14.0, "spent": {"prod-x": 11.01}}
    import core.pipeline_cost_guard as g

    monkeypatch.setattr(g, "effective_max_pipeline_cost_usd", lambda: state["cap"])
    monkeypatch.setattr(g, "pipeline_cost_guard_enabled", lambda: state["cap"] > 0)
    monkeypatch.setattr(g, "product_spend_usd", lambda pid, **kw: state["spent"].get(pid, 0.0))
    return state


def _parked() -> dict:
    return {
        "prod-x": {
            "state": "FAILED",
            "budget_parked": True,
            "state_before_budget_park": "DEV_FIXING",
            "failure_reason": "Pipeline LLM budget exceeded for prod-x: $11.0105 spent (cap $11.00)",
        }
    }


def test_headroom_resumes_the_product(guard):
    products = _parked()
    assert tqh.unpark_budget_exhausted(products) == ["prod-x"]
    p = products["prod-x"]
    assert p["state"] == "DEV_FIXING"
    assert p["budget_parked"] is False
    assert "failure_reason" not in p


def test_no_headroom_keeps_it_parked_and_shouts(guard, caplog):
    guard["cap"] = 11.0
    products = _parked()
    import logging

    with caplog.at_level(logging.WARNING, logger="pipeline-worker"):
        assert tqh.unpark_budget_exhausted(products) == []
    assert products["prod-x"]["state"] == "FAILED"
    assert any("PARKED ON BUDGET" in r.message for r in caplog.records), (
        "a park a human discovers by absence is the whole failure this exists to close"
    )


def test_the_shout_is_throttled_not_a_two_second_spam(guard):
    guard["cap"] = 11.0
    products = _parked()
    tqh.unpark_budget_exhausted(products)
    first = products["prod-x"].get("_budget_park_warned_at")
    tqh.unpark_budget_exhausted(products)
    assert products["prod-x"].get("_budget_park_warned_at") == first


def test_a_disabled_guard_resumes_too(guard):
    guard["cap"] = 0.0
    products = _parked()
    assert tqh.unpark_budget_exhausted(products) == ["prod-x"]


def test_a_legacy_park_without_the_flag_is_recognised(guard):
    """Products parked before this mechanism carry only the failure_reason text."""
    products = _parked()
    products["prod-x"].pop("budget_parked")
    assert tqh.unpark_budget_exhausted(products) == ["prod-x"]


def test_a_genuinely_failed_product_is_left_alone(guard):
    products = {"prod-y": {"state": "FAILED", "failure_reason": "unrecoverable schema corruption"}}
    assert tqh.unpark_budget_exhausted(products) == []
    assert products["prod-y"]["state"] == "FAILED"


def test_the_park_site_records_the_way_back():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    region = src[src.index("except PipelineCostBudgetExceeded as budget_exc:") :][:1600]
    assert '"state_before_budget_park"' in region
    assert '"budget_parked"' in region
    assert "PARKED ON BUDGET" in region, "the park itself must be loud, not only the aftermath"


def test_the_worker_runs_it_even_under_hold():
    src = (ROOT / "pipeline_worker.py").read_text(encoding="utf-8")
    at = src.index("unpark_budget_exhausted(products)")
    phase4c = src.index("# Phase 4c: Idle mid-pipeline products")
    assert at < phase4c
    region = src[max(0, at - 900) : at]
    assert "if not soft_hold" not in region.split("Phase 4b2")[-1], (
        "gated by the hold, it cannot fix the exact state the hold left the product in"
    )


def test_the_keys_survive_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "budget_parked" in PRODUCT_EXTRA_KEYS
    assert "state_before_budget_park" in PRODUCT_EXTRA_KEYS


def test_the_park_warning_throttle_does_not_live_on_the_product():
    """A throttle stored in a dropped field never throttles.

    The timestamp was written to product["_budget_park_warned_at"], a key absent from
    PRODUCT_EXTRA_KEYS — so SQLite dropped it on every save, the 600-second check always compared
    against 0.0, and the warning fired on every worker pass: roughly thirty lines a second for four
    hours, on a disk that had already filled up once the same night. The park itself worked; only
    its voice was broken, and a warning nobody can read is not a warning.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "orchestrator" / "task_queue_hygiene.py"
    ).read_text(encoding="utf-8")
    assert "_BUDGET_WARNED_AT: dict[str, float] = {}" in src
    body = src[src.index("def unpark_budget_exhausted(") :]
    assert "_BUDGET_WARNED_AT.get(pid)" in body
    assert 'product["_budget_park_warned_at"] = ' not in body, (
        "still writing the throttle to a field SQLite drops"
    )
    assert "> 600" in body, "the throttle window itself must survive"
