"""A task inside its own budget is not stale.

The developer's execute timeout is 1500s; the stale-running threshold defaulted to 1200s. So a
healthy round that legitimately ran 20-25 minutes was declared stale and re-run — on a tree its
first pass had already rewritten. The agent would have timed out on its own five minutes later
and reported properly; the reset produced duplicate work and a half-written tree instead.

Latent for a long time, and repair batching made it the normal case rather than the rare one:
six sequential generation calls land squarely in the 15-22 minute band. Observed live —

    task-cdfe443ff developer running  "stale running reset after 1200s"

— on a round that had just produced all six batches successfully.
"""

from __future__ import annotations

import pytest

from orchestrator.task_executor_agent import _agent_execute_timeout_sec
from orchestrator.task_queue_hygiene import _stale_running_threshold_sec


@pytest.mark.parametrize("agent", ["developer", "qa", "pm", "architect", "security"])
def test_the_threshold_is_never_below_the_agents_own_timeout(agent):
    """Otherwise the watchdog fires before the thing it is watching can finish."""
    timeout = _agent_execute_timeout_sec(agent)
    threshold = _stale_running_threshold_sec(agent)
    assert threshold > timeout, (
        f"{agent}: stale threshold {threshold}s <= execute timeout {timeout}s, so a healthy "
        "task is reset mid-flight and re-run over its own half-written output"
    )


def test_the_developer_case_that_was_observed():
    """The specific numbers from production: 1500s timeout against a 1200s threshold."""
    assert _agent_execute_timeout_sec("developer") == 1500.0
    assert _stale_running_threshold_sec("developer") >= 1800.0


def test_there_is_margin_for_the_work_after_the_last_generation():
    """Writes, the static self-check and the rollbacks all happen after generation returns."""
    for agent in ("developer", "qa"):
        assert _stale_running_threshold_sec(agent) - _agent_execute_timeout_sec(agent) >= 300.0


def test_an_env_override_can_still_raise_it(monkeypatch):
    monkeypatch.setenv("AIFACTORY_STALE_RUNNING_SEC", "5400")
    assert _stale_running_threshold_sec("developer") >= 5400.0


def test_a_per_product_override_still_wins_upward():
    """Operators pin a longer timeout for a known-slow product; that must keep working."""
    high = _stale_running_threshold_sec(
        "developer", product={"stale_running_sec_override": 7200}
    )
    assert high >= 7200.0


def test_a_too_low_override_cannot_reintroduce_the_bug():
    """An override below the agent's timeout is the same trap by another route."""
    low = _stale_running_threshold_sec("developer", product={"stale_running_sec_override": 60})
    assert low > _agent_execute_timeout_sec("developer"), (
        "a per-product override was allowed to drop below the execute timeout"
    )
