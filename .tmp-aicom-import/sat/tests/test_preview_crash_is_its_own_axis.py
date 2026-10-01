"""A page that throws before paint has no UI to grade.

Measured on Sentinel. Browser E2E is kept out of GUARD_SCORED_GATES (crawl noise). The demo-quality
axis we added then did this:

    76 B, E2E green  ->  86 A, pageerror x12   accepted (demo rose)
    86 A, still throwing -> 76 B, E2E green   reverted (demo fell)

The working tree was thrown away because empty/toast in source still scored A on a page that never
painted. Same shape as a dead backend: the count moved, the product did not. The *throw* is its own
axis. spec_alignment_llm and a11y-without-throw are the next round's work on a page that loaded.
"""

from __future__ import annotations

from pathlib import Path

from core.round_regression_guard import preview_crashed

ROOT = Path(__file__).resolve().parents[1]


def test_page_errors_field_reads_as_crashed():
    """Playwright also stores the throws in page_errors; issues can be a parallel list."""
    assert preview_crashed(
        {"browser_preview_e2e": {"passed": False, "skipped": False, "issues": [], "page_errors": ["Error"]}}
    ) is True


def test_nested_quality_gates_are_readable():
    assert preview_crashed(
        {
            "quality_gates": {
                "browser_preview_e2e": {
                    "passed": False,
                    "skipped": False,
                    "issues": ["pageerror: Error"],
                }
            }
        }
    ) is True


def test_a_painted_page_is_not_a_crash():
    assert preview_crashed(
        {
            "browser_preview_e2e": {
                "passed": False,
                "skipped": False,
                "issues": ["spec_alignment_llm_failed: no toast"],
            }
        }
    ) is False
    assert preview_crashed(
        {
            "browser_preview_e2e": {
                "passed": True,
                "skipped": False,
                "issues": [],
            }
        }
    ) is False


def test_a_network_console_error_is_not_an_uncaught_throw():
    """HTTP 500 in devtools is a different finding; treating it as a crash would revert UI work."""
    assert preview_crashed(
        {
            "browser_preview_e2e": {
                "passed": False,
                "skipped": False,
                "issues": [
                    "console_error: Failed to load resource: the server responded with a status of 500"
                ],
            }
        }
    ) is False


def test_a_skipped_or_missing_gate_has_no_opinion():
    assert preview_crashed({"browser_preview_e2e": {"skipped": True}}) is None
    assert preview_crashed({}) is None
    assert preview_crashed("not a dict") is None


def test_the_guard_reverts_a_round_that_started_throwing():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "crashed = preview_crashed(qa_result)" in guard
    assert "if crashed is True and was_crashed is False:" in guard
    assert "the browser never painted" in guard


def test_the_crash_check_runs_before_visual_breakthrough():
    """Otherwise 86 A with pageerror is accepted because the demo score rose."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert guard.index("if crashed is True and was_crashed is False:") < guard.index(
        "visual_breakthrough"
    )
    assert "and crashed is not True" in guard


def test_a_crash_fix_is_not_reverted_as_a_visual_drop():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "crash_cleared" in guard
    assert "and not crash_cleared" in guard
    assert "was_crashed is not False" in guard, (
        "a missing key must not visual-revert the first green tree after this axis lands"
    )


def test_the_state_is_recorded_and_survives_sqlite():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    writes = guard.count('product["last_qa_defect_score"] = score')
    crashes = guard.count('product["last_preview_crashed"] = crashed')
    assert crashes >= writes, f"{writes} baseline writes but only {crashes} record the crash bit"

    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_preview_crashed" in PRODUCT_EXTRA_KEYS
