"""A round that raises demo quality cannot be a regression; a round that lowers it cannot be progress.

Measured on Sentinel. A repair added mobile nav, empty/error/toast — demo 66 C → 86 A — and was
reverted 3 → 9 for two unused TypeScript locals (TS6133). The next round deleted those locals by
rewriting App.tsx to an 18-line router; demo fell back to 66 C and the guard *accepted* it because
the weighted total improved. Visuals never landed. Demo/TZ findings do not vote in the defect
score (render-timed crawl noise); the *integer* from the static demo_quality gate does, as its
own ratchet, or the loop oscillates forever.
"""

from __future__ import annotations

from pathlib import Path

from core.round_regression_guard import demo_quality_score

ROOT = Path(__file__).resolve().parents[1]


def test_it_reads_the_demo_quality_integer():
    assert demo_quality_score({"demo_quality": {"score": 86, "grade": "A"}}) == 86
    assert demo_quality_score({"demo_quality": {"score": 66, "grade": "C"}}) == 66


def test_no_opinion_when_the_gate_did_not_run():
    assert demo_quality_score({"bugs_found": []}) is None
    assert demo_quality_score({"demo_quality": {"skipped": True, "score": 0}}) is None
    assert demo_quality_score("not a dict") is None
    assert demo_quality_score({"demo_quality": {"grade": "A"}}) is None


def test_the_guard_accepts_a_higher_demo_score_despite_the_total():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "demo_quality_score(qa_result)" in guard
    assert "demo > stored_demo" in guard
    assert "visual_breakthrough" in guard
    assert "visual breakthrough" in guard, "a silent accept hides why unused-local tsc lost"


def test_the_guard_reverts_a_lower_demo_score_even_when_the_total_improved():
    """The TS-fix half of the oscillation: 9 → 3 by deleting the UI is not an improvement."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "demo < stored_demo" in guard
    assert "visual_regression" in guard
    assert "and not visual_regression" in guard
    assert "tsc got quieter after the UI was deleted" in guard


def test_the_visual_check_runs_before_the_revert():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert guard.index("demo > stored_demo") < guard.index("if not restore_snapshot(")
    assert guard.index("visual_regression") < guard.index("if not restore_snapshot(")


def test_a_baseline_without_a_recorded_score_is_read_from_the_c_grade_markers():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert "visual_no_responsive_nav_mobile" in guard
    assert "visual_app_missing_empty_state" in guard
    assert "stored_demo = 66" in guard


def test_every_path_that_keeps_the_measured_tree_records_its_demo_score():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    writes = guard.count('product["last_qa_defect_score"] = score')
    demos = guard.count('product["last_demo_quality_score"] = demo')
    assert demos >= writes, f"{writes} baseline writes but only {demos} record the demo score"


def test_the_key_survives_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_demo_quality_score" in PRODUCT_EXTRA_KEYS
