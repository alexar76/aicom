"""A journey that gets strictly deeper cannot be a regression, whatever it finds there.

Measured twice on one product, back to back. The round that finally made login return a token was
reverted 14 -> 32 for six 401s on endpoints behind the login; the next round, same fix, was
reverted 14 -> 35 because those 401s had become 500s. Both sets of findings were unreachable one
round earlier: auth_rejected and 5xx behind a door that would not open. Depth and defect count
move in opposite directions at a breakthrough, so depth has to be its own ratchet axis or the
guard destroys exactly the rounds the whole pipeline exists to produce.
"""

from __future__ import annotations

from pathlib import Path

from core.round_regression_guard import journey_depth

ROOT = Path(__file__).resolve().parents[1]


def _qa(attempts):
    return {"bugs_found": [], "demo_journey": {"login": {"attempts": attempts}}}


def test_depth_two_means_a_token():
    assert journey_depth(_qa([{"kind": "form", "status": 422, "token": False},
                              {"kind": "json_email", "status": 200, "token": True}])) == 2


def test_depth_one_is_a_2xx_without_a_token():
    assert journey_depth(_qa([{"kind": "json_email", "status": 200, "token": False}])) == 1


def test_depth_zero_is_a_failed_login():
    assert journey_depth(_qa([{"kind": "form", "status": 422, "token": False},
                              {"kind": "json_email", "status": 500, "token": False}])) == 0


def test_no_journey_means_no_opinion():
    """None must never accept or reject anything: products without a login have no depth axis."""
    assert journey_depth({"bugs_found": []}) is None
    assert journey_depth({"demo_journey": {"login": {"skipped": "no_login_endpoint"}}}) is None
    assert journey_depth("not a dict") is None


def test_the_guard_accepts_a_deeper_round_despite_the_score():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "journey_depth(qa_result)" in guard
    assert "depth > stored_depth" in guard
    assert "visual_breakthrough" in guard
    assert (
        'if (verdict(previous, score) == "accept" or breakthrough) and not visual_regression:'
        in guard
    )
    assert "breakthrough round" in guard, "a silent breakthrough accept hides why the score jumped"


def test_the_breakthrough_check_runs_before_the_revert():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert guard.index("depth > stored_depth") < guard.index("if not restore_snapshot(")


def test_a_baseline_without_a_recorded_depth_is_read_from_its_own_diagnosis():
    """The stored diagnosis saying demo_login_no_token IS a depth statement: shallower than 2.

    Without this, the first breakthrough after this code deploys would not be recognised — the
    depth was never recorded before the axis existed.
    """
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert '"demo_login_no_token" in _titles' in guard
    assert '"demo_login_failed" in _titles' in guard


def test_every_path_that_keeps_the_measured_tree_records_its_depth():
    """Re-anchors and unrevertable keeps adopt the measured tree; a stale depth on those paths
    would later let a same-depth round pass as a breakthrough."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    writes = guard.count('product["last_qa_defect_score"] = score')
    depths = guard.count('product["last_journey_depth"] = depth')
    assert depths >= writes, f"{writes} baseline writes but only {depths} record the depth"


def test_the_key_survives_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_journey_depth" in PRODUCT_EXTRA_KEYS
