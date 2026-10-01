"""The score was counting symptom lines, and one broken import writes a line in every gate.

Taken from a round that was rejected at 34 against a baseline of 26:

    Module health: missing_symbol            CachedMeshReading      3
    Demo journey: import_error               CachedMeshReading      3   <- same defect
    Demo journey: demo_journey_boot_failed   …'CachedMeshReading'   3   <- same defect
    Frontend build: Dashboard.tsx(2,10)                             3
    Frontend build: Dashboard.tsx(3,10)                             3   <- same import block
    Frontend build: Dashboard.tsx(4,10)                             3   <- same import block

Two thirds of the weight was one symbol and one file's imports, counted over and over. Scored by
root cause the same round comes to **19**, which is *below* the baseline — so a round that closed
every mesh-contract violation and half the missing symbols would have been kept instead of thrown
away. The bias has a direction: fixing two defects and breaking one import could come out
net-worse while being net-better, because the new breakage is observed by three gates and the two
fixes only leave one each.

The gate that names the file to fix keeps its vote. A downstream sighting of the same identifier
does not vote again. Anything with no such link — a missing module no static gate ever saw — is a
real second defect and still counts.
"""

from __future__ import annotations

from core.round_regression_guard import dedupe_root_causes, qa_defect_score

MISSING_SYMBOL = {
    "severity": "high",
    "title": "Module health: missing_symbol",
    "description": "app.models.advisory never defines CachedMeshReading",
}
JOURNEY_SAME = {
    "severity": "high",
    "title": (
        "Demo journey: import_error: ImportError: cannot import name 'CachedMeshReading' from "
        "'app.models.advisory'"
    ),
}
JOURNEY_BOOT_SAME = {
    "severity": "high",
    "title": (
        "Demo journey: demo_journey_boot_failed:uvicorn_failed_to_listen: ImportError: cannot "
        "import name 'CachedMeshReading'"
    ),
}
JOURNEY_OTHER = {
    "severity": "high",
    "title": "Demo journey: import_error: ModuleNotFoundError: No module named 'app.schemas.auth'",
}
BUILD_LINES = [
    {
        "severity": "high",
        "title": f"Frontend build: frontend_build_failed: src/components/Operator/Dashboard.tsx({n},10): error TS2307",
    }
    for n in (2, 3, 4)
]


def test_the_live_rejected_round_scores_below_the_baseline_it_lost_to():
    """The whole point: this round improved the product and was discarded."""
    bugs = [
        *BUILD_LINES,
        {
            "severity": "critical",
            "title": "Module health: duplicate_tablename",
            "description": "2 model classes declare __tablename__ = 'allowance_state'",
        },
        MISSING_SYMBOL,
        {
            "severity": "high",
            "title": "Module health: missing_symbol",
            "description": "app.models.advisory never defines WatchLocation",
        },
        {
            "severity": "high",
            "title": "Module health: missing_symbol",
            "description": "app.services.cache never defines MeshCache",
        },
        JOURNEY_BOOT_SAME,
        JOURNEY_SAME,
        JOURNEY_OTHER,
        {
            "severity": "high",
            "title": "Demo journey: import_error: ImportError: cannot import name 'MeshCache' from 'app.services.cache'",
        },
    ]
    assert qa_defect_score({"bugs_found": bugs}) == 19
    assert 19 < 26, "the baseline this round was rejected against"


def test_a_downstream_sighting_of_the_same_symbol_does_not_vote_twice():
    one = qa_defect_score({"bugs_found": [MISSING_SYMBOL]})
    three = qa_defect_score({"bugs_found": [MISSING_SYMBOL, JOURNEY_SAME, JOURNEY_BOOT_SAME]})
    assert one == three == 3


def test_a_defect_no_static_gate_saw_still_counts():
    """A missing module is a second real defect, not a duplicate of a missing symbol."""
    assert qa_defect_score({"bugs_found": [MISSING_SYMBOL, JOURNEY_OTHER]}) == 6


def test_compiler_lines_about_one_file_are_one_defect():
    assert qa_defect_score({"bugs_found": BUILD_LINES}) == 3


def test_two_broken_files_are_two_defects():
    other = {
        "severity": "high",
        "title": "Frontend build: frontend_build_failed: src/App.tsx(1,1): error TS2307",
    }
    assert qa_defect_score({"bugs_found": [*BUILD_LINES, other]}) == 6


def test_the_static_finding_is_the_one_that_survives():
    """It names the file and the symbol; the journey line names a traceback."""
    kept = dedupe_root_causes([JOURNEY_SAME, MISSING_SYMBOL, JOURNEY_BOOT_SAME])
    assert kept == [MISSING_SYMBOL], kept


def test_module_health_findings_never_suppress_each_other():
    """Three missing symbols are three defects even though they share a module."""
    bugs = [
        MISSING_SYMBOL,
        {
            "severity": "high",
            "title": "Module health: missing_symbol",
            "description": "app.models.advisory never defines WatchLocation",
        },
    ]
    assert qa_defect_score({"bugs_found": bugs}) == 6


def test_short_tokens_do_not_create_accidental_matches():
    """Quoted noise like 'id' or 'ok' must not silence an unrelated gate."""
    static = {
        "severity": "high",
        "title": "Module health: missing_symbol",
        "description": "app.models.x never defines ok",
    }
    unrelated = {"severity": "high", "title": "Demo journey: demo_journey_5xx:/api/'ok'"}
    assert qa_defect_score({"bugs_found": [static, unrelated]}) == 6


def test_a_finding_from_a_non_voting_gate_is_still_not_counted():
    """Dedup composes with the whitelist rather than replacing it."""
    noisy = {"severity": "high", "title": "Browser E2E: visual_svg_viewport_hog"}
    assert qa_defect_score({"bugs_found": [MISSING_SYMBOL, noisy]}) == 3


def test_an_empty_round_is_still_zero_and_a_non_dict_is_still_none():
    assert qa_defect_score({"bugs_found": []}) == 0
    assert qa_defect_score("nope") is None


# --- one duplicate breaks the whole model layer -----------------------------------------------

DUP_TABLE = {
    "severity": "critical",
    "title": "Module health: duplicate_tablename",
    "description": "2 model classes declare __tablename__ = 'allowance_state': AllowanceState in "
    "backend/app/models/audit.py:36; AllowanceState in backend/app/models/advisory.py:56.",
}
BOOT_SYMPTOM = {
    "severity": "high",
    "title": "Demo journey: import_error: InvalidRequestError: Table 'invoke_audit_logs' is "
    "already defined for this MetaData instance",
}


def test_the_boot_error_naming_a_different_table_is_the_same_defect():
    """SQLAlchemy's MetaData is global: one duplicate breaks the whole model import.

    Observed live at a score of 10: the detector reports `allowance_state` declared twice, while the
    boot error says `invoke_audit_logs` — the first import pass registered that table before failing
    on the duplicate, and the retry tripped over its own leftovers. The table named in the error is
    decided by import order, not by a second defect, so matching on the name could never collapse
    these two and the identifier rule alone was not enough.
    """
    assert qa_defect_score({"bugs_found": [DUP_TABLE, BOOT_SYMPTOM]}) == 4


def test_the_boot_error_still_counts_when_no_duplicate_is_reported():
    """With nothing static to attribute it to, it is the only evidence there is."""
    assert qa_defect_score({"bugs_found": [BOOT_SYMPTOM]}) == 3


def test_an_unrelated_journey_error_is_untouched_by_this_rule():
    other = {"severity": "high", "title": "Demo journey: demo_journey_5xx:/api/advisory"}
    assert qa_defect_score({"bugs_found": [DUP_TABLE, other]}) == 7


def test_the_symptom_still_reaches_the_developer():
    """Dedup governs the vote, never the work list."""
    kept = dedupe_root_causes([DUP_TABLE, BOOT_SYMPTOM])
    assert DUP_TABLE in kept
    assert len(kept) == 1, "the collapse must remove it from scoring only"


def test_an_opinion_with_no_gate_prefix_does_not_vote():
    """The plateau this broke, and the revert log that finally named it.

        Round guard: 9 new finding(s) this round did not have before —
        Generic exception handler hides all errors; Integration tests are flaky;
        Login test is too permissive; Missing required repository files…

    Three rounds in a row reverted 14 -> 18, 20, 22 on arrivals like these, while the static tree got
    BETTER (missing_attribute 3 -> 1). They come from the LLM reviewer, whose output differs between
    two runs over identical code, so they cannot answer "is this round better than the last" — and the
    coin was landing against every round that touched anything.

    The whitelist alone did not stop them: it drops findings from gates it does not trust, and these
    carry no gate prefix at all, so `if gate and gate not in GUARD_SCORED_GATES` let every one of them
    through.
    """
    from core.round_regression_guard import qa_defect_score

    opinion = {"severity": "high", "title": "Generic exception handler hides all errors"}
    gated = {"severity": "high", "title": "Module health: missing_attribute", "file": "a.py"}

    assert qa_defect_score({"bugs_found": [opinion]}) == 0
    assert qa_defect_score({"bugs_found": [opinion, gated]}) == qa_defect_score(
        {"bugs_found": [gated]}
    )


def test_findings_from_trusted_gates_still_vote():
    from core.round_regression_guard import qa_defect_score

    for title in (
        "Module health: missing_symbol",
        "Frontend build: index.tsx(3,1) error TS2304",
        "Demo journey: demo_journey_5xx:/api/x:500",
        "API contract: endpoint_missing",
    ):
        assert qa_defect_score({"bugs_found": [{"severity": "high", "title": title}]}) > 0, title


def test_an_untrusted_gate_still_does_not_vote():
    """browser e2e includes an LLM alignment judgement and was already excluded; keep it that way."""
    from core.round_regression_guard import qa_defect_score

    assert qa_defect_score(
        {"bugs_found": [{"severity": "high", "title": "Browser E2E: spec_alignment_llm_failed:…"}]}
    ) == 0
