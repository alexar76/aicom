"""A product that does not start has no qualities to measure.

Measured. The round that finished closing the ATLAS contract violations also broke a constructor
call, and the two things arrived in the same verdict:

    demo_journey_boot_failed: TypeError: HeartbeatService.__init__() takes 1 positional argument
    backend_e2e: True -> False
    defects: 32 -> 27

The tree genuinely was cleaner, so the defect score improved, so the guard accepted a round that
left the application unable to start. Booting is not a matter of degree and cannot be traded against
a lower count of static findings — it needs its own axis, like journey depth.
"""

from __future__ import annotations

from pathlib import Path

from core.round_regression_guard import backend_boots

ROOT = Path(__file__).resolve().parents[1]


def test_a_passing_backend_gate_reads_as_booting():
    assert backend_boots({"backend_runtime_e2e": {"passed": True, "skipped": False}}) is True


def test_a_failing_backend_gate_reads_as_not_booting():
    assert backend_boots({"backend_runtime_e2e": {"passed": False, "skipped": False}}) is False


def test_a_skipped_or_missing_gate_has_no_opinion():
    """None must never revert anything: products without a backend are not broken."""
    assert backend_boots({"backend_runtime_e2e": {"skipped": True}}) is None
    assert backend_boots({}) is None
    assert backend_boots("not a dict") is None
    assert backend_boots({"backend_runtime_e2e": {"passed": None, "skipped": False}}) is None


def test_the_guard_reverts_a_round_that_stopped_the_boot():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "boots = backend_boots(qa_result)" in guard
    assert 'if boots is False and was_booting is True:' in guard
    assert "has no qualities to measure" in guard, "the log has to say why the count is irrelevant"


def test_the_boot_check_runs_before_the_score_decides():
    """After the accept branch it would only notice the breakage a round too late."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert guard.index("boots = backend_boots(qa_result)") < guard.index(
        'if (verdict(previous, score) == "accept" or breakthrough) and not visual_regression:'
    )


def test_a_product_that_never_booted_is_not_punished():
    """False -> False is not a regression; the round may be the one fixing it."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert "was_booting is True" in guard


def test_the_state_is_recorded_and_survives_sqlite():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    assert 'product["last_backend_booted"] = boots' in src

    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_backend_booted" in PRODUCT_EXTRA_KEYS
