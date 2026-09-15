"""A baseline measured under older rules is in different units, so it can only be replaced.

This cost the best round of the evening. A round brought missing symbols from 9 down to 2 — the
largest real improvement all day — and the guard threw it away:

    Round guard: reverted a repair round (7 -> 64, severity-weighted); restored the tree QA last
    measured. Rounds reverted so far: 18

The 64 was honest. The 7 was measured hours earlier, before `missing_symbol` was raised from `high` to
`critical` and before two dedup rules landed. Nothing about the code had got nine times worse; the
ruler had changed. And the incentive runs the wrong way: the more the detectors improve, the more work
gets destroyed, which is the opposite of why they exist.

The tree fingerprint already covers "same tree, different measurement". This is its other half: the
same measurement *machinery*, or re-anchor instead of judging. Bump `SCORING_RULES_VERSION` whenever
the whitelist, the weights, the dedup rules or a detector's reported severity change, and the first
measurement afterwards sets the baseline instead of losing to it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a_version_exists_and_is_an_integer():
    from core.round_regression_guard import SCORING_RULES_VERSION

    assert isinstance(SCORING_RULES_VERSION, int) and SCORING_RULES_VERSION >= 1


def test_the_guard_reanchors_when_the_rules_moved():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert 'stored_rules = product.get("last_qa_defect_score_rules")' in guard
    assert "stored_rules != SCORING_RULES_VERSION" in guard
    assert "re-anchored to" in guard, "a silent re-anchor hides why the number moved"


def test_it_runs_before_the_accept_or_revert_decision():
    """After the decision, a rules change would already have reverted the round it invalidated."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert guard.index("stored_rules != SCORING_RULES_VERSION") < guard.index(
        'if (verdict(previous, score) == "accept" or breakthrough) and not visual_regression:'
    )


def test_a_first_measurement_is_not_treated_as_a_rules_change():
    """With no baseline at all there is nothing to re-anchor; the normal path stores it."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert "if previous is not None and stored_rules != SCORING_RULES_VERSION:" in guard


def test_every_path_that_writes_the_baseline_stamps_the_rules():
    """A baseline without a version is indistinguishable from one measured under old rules, so it
    would re-anchor forever and the guard would never revert anything again."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    writes = guard.count('product["last_qa_defect_score"] = score')
    stamps = guard.count('product["last_qa_defect_score_rules"] = SCORING_RULES_VERSION')
    assert stamps >= writes, f"{writes} baseline writes but only {stamps} stamped"


def test_the_key_survives_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_qa_defect_score_rules" in PRODUCT_EXTRA_KEYS


def test_the_version_is_documented_next_to_what_changes_it():
    """A version nobody knows to bump is a version that lies."""
    import re

    src = (ROOT / "core" / "round_regression_guard.py").read_text(encoding="utf-8")
    # Flatten the comment: a phrase wrapped across two lines is still documented.
    head = re.sub(r"\s+", " ", src[: src.index("SCORING_RULES_VERSION")].replace("#", " "))
    for trigger in ("gate whitelist", "severity weights", "dedup rules", "reported severity"):
        assert trigger in head, f"nothing tells the next reader that {trigger!r} bumps the version"


def test_adding_a_term_to_the_score_bumps_the_version():
    """Forgetting this cost a round in which the app had actually booted.

        QA complete: 12 bugs, backend_e2e=True          ← the backend started
        Round guard: reverted a repair round (7 -> 12)  ← and the round was thrown away

    The 7 was measured before the class-body forward-reference term existed; the 12 includes it. The
    version is what tells the guard those are different units, and it was left at 4 while the score
    changed underneath it. Bumping it is the mechanism, not bookkeeping.

    Pinned as a floor rather than an exact value so it can keep rising, and paired with the term list so
    the next person adding a detector sees the two live together.
    """
    from pathlib import Path

    from core.round_regression_guard import SCORING_RULES_VERSION

    assert SCORING_RULES_VERSION >= 28

    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    terms = sum(
        1
        for name in (
            "find_missing_symbols",
            "find_missing_modules",
            "find_missing_instance_attributes",
            "find_class_body_forward_refs",
            "find_duplicated_router_prefix",
            "find_frontend_missing_exports",
            "find_mismatched_back_populates",
            "find_api_routes_shadowing_spa",
            "find_case_collisions",
            "find_dead_path_rewrites",
            "find_duplicate_tablenames",
            "find_hallucinated_imports",
            "find_orm_schema_never_created",
            "find_undeclared_dependencies",
            "find_capabilities_never_invoked",
            "find_sync_wrapper_over_async_handler",
        )
        if f"len({name}(" in score
    )
    assert terms == 16, f"the score has {terms} of the import-fatal terms; did a detector move?"


def test_a_rules_change_is_not_an_amnesty_for_new_breakage():
    """Re-anchoring must not adopt defects the accepted tree did not have.

    This cost a working product. The rules moved 16 -> 18 in the same round that a repair added
    `@rate_limit` without the `request` parameter slowapi needs, so `app.main` stopped importing and
    every route died. QA reported 52 defects and backend_e2e=False; the guard said "different units,
    not a regression", adopted the broken tree as the new baseline at 95, and there was nothing left
    to revert to.

    The NUMBER is in new units. The IDENTITIES are not: a name that resolved before and does not now
    is a regression under any ruler. So the units re-anchor while the defect set is still compared.
    """
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]

    rules_branch = guard[guard.index("stored_rules != SCORING_RULES_VERSION") :]
    rules_branch = rules_branch[: rules_branch.index("fingerprint = tree_fingerprint(")]
    assert "_tree_defect_identities" in rules_branch, "the rules branch compares nothing structural"
    assert "restore_snapshot(pid, code_root, host.data_root)" in rules_branch
    assert "adopting new breakage is not" in rules_branch

    # And the accepted tree's identities have to be recorded, or there is nothing to compare to.
    assert 'product["last_accepted_defect_identities"]' in guard

    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_accepted_defect_identities" in PRODUCT_EXTRA_KEYS


def test_a_rules_change_with_no_new_defects_still_re_anchors():
    """The original purpose survives: a sharper ruler on the same tree must not revert anything."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    rules_branch = guard[guard.index("stored_rules != SCORING_RULES_VERSION") :]
    rules_branch = rules_branch[: rules_branch.index("fingerprint = tree_fingerprint(")]
    assert "if regressed_ids:" in rules_branch, "the revert must be conditional on new identities"
    assert "re-anchored to %s rather than compared" in rules_branch
