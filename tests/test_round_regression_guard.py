"""A repair round survives only if QA's own count says it helped.

Diagnosis, measured across eight consecutive QA rounds on one product: 114 distinct defects
appeared and **101 existed in exactly one round**. Exactly one persisted across seven or more
— and that one was a gate comparing the build to a specification that did not exist. Per
round the loop fixed ~14 findings and introduced ~15. The plateau at 12–16 was never a
stubborn core; ``fixed ≈ new`` held it in place.

A guard against this already existed in the developer and could not work: its score counted
unresolved imports, unbound names and unparseable files, while QA blocks on a frontend
TypeScript build, a booted app answering 5xx, a browser crawl and module health. A round could
resolve an import and break the TS build and still score as progress.

So the decision moves to the QA boundary, where the real measurement already happened. What
these tests pin is mostly the *edges*, because the happy path is one comparison and the edges
are where a guard like this does damage: it must never discard work it cannot measure, never
leave a product without a code directory, and never revert a round that merely traded a
critical for three lows.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from core.round_regression_guard import (
    guard_enabled,
    has_snapshot,
    qa_defect_score,
    restore_snapshot,
    revert_hint,
    save_snapshot,
    verdict,
)


def _tree(root: Path, marker: str) -> Path:
    code = root / "code" / "prod-x"
    (code / "backend" / "app").mkdir(parents=True, exist_ok=True)
    (code / "backend" / "app" / "main.py").write_text(f"# {marker}\n", encoding="utf-8")
    (code / "frontend").mkdir(parents=True, exist_ok=True)
    (code / "frontend" / "App.tsx").write_text(f"// {marker}\n", encoding="utf-8")
    return code


# --- the score -----------------------------------------------------------------------


def test_severity_is_weighted_not_counted():
    """One critical must outweigh two lows, or the guard reverts real progress.

    A round that turns a crash into a couple of lint findings is exactly the kind of round
    this loop needs to be able to land.
    """
    before = {"bugs_found": [{"severity": "critical"}]}
    after = {"bugs_found": [{"severity": "low"}, {"severity": "low"}]}
    assert qa_defect_score(after) < qa_defect_score(before)


def test_an_unknown_severity_is_not_free():
    """Otherwise a round could relabel its findings and look like an improvement."""
    assert qa_defect_score({"bugs_found": [{"severity": "banana"}]}) > 0
    assert qa_defect_score({"bugs_found": [{}]}) > 0


def test_an_unreadable_report_has_no_opinion():
    for bad in (None, {}, {"bugs_found": "not a list"}, "text", 7):
        assert qa_defect_score(bad) is None


def test_a_clean_report_scores_zero():
    assert qa_defect_score({"bugs_found": []}) == 0


# --- the verdict ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "previous,current,expected",
    [
        (10, 15, "revert"),
        (10, 10, "accept"),   # a trade of equal weight may still be progress
        (10, 4, "accept"),
        (0, 1, "revert"),
        (None, 12, "accept"), # first measured round has nothing to compare against
        ("x", 12, "accept"),
    ],
)
def test_verdict(previous, current, expected):
    assert verdict(previous, current) == expected


def test_equal_scores_are_accepted_deliberately():
    """Documenting the choice: reverting on equality discards genuine trades.

    The measured rounds swapped roughly as many findings as they fixed, so an equality
    revert would have thrown away nearly every round including the useful ones.
    """
    assert verdict(15, 15) == "accept"


def test_the_guard_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("AIFACTORY_ROUND_REGRESSION_GUARD", "0")
    assert guard_enabled() is False
    assert verdict(1, 99) == "accept", "a disabled guard must accept everything"


# --- snapshot and restore ------------------------------------------------------------


def test_restore_puts_back_the_measured_tree(tmp_path):
    code = _tree(tmp_path, "measured")
    assert save_snapshot("prod-x", code, tmp_path) is True
    assert has_snapshot("prod-x", tmp_path)

    # The round rewrites one file and deletes another — the shape of the observed churn.
    (code / "backend" / "app" / "main.py").write_text("# broken by the round\n", encoding="utf-8")
    (code / "frontend" / "App.tsx").unlink()

    assert restore_snapshot("prod-x", code, tmp_path) is True
    assert (code / "backend" / "app" / "main.py").read_text(encoding="utf-8") == "# measured\n"
    assert (code / "frontend" / "App.tsx").is_file(), "a deleted file must come back too"


def test_restore_removes_files_the_round_added(tmp_path):
    """A regressive round often adds a duplicate module; leaving it behind keeps the defect."""
    code = _tree(tmp_path, "measured")
    save_snapshot("prod-x", code, tmp_path)
    (code / "backend" / "app" / "auth_v2.py").write_text("# duplicate\n", encoding="utf-8")

    restore_snapshot("prod-x", code, tmp_path)
    assert not (code / "backend" / "app" / "auth_v2.py").exists()


def test_restore_without_a_snapshot_reports_failure(tmp_path):
    code = _tree(tmp_path, "only")
    assert restore_snapshot("prod-x", code, tmp_path) is False
    assert (code / "backend" / "app" / "main.py").is_file(), "the tree must be left intact"


def test_a_failed_restore_never_leaves_the_product_without_code(tmp_path, monkeypatch):
    """The worst outcome this guard could produce, so the property is pinned.

    The first design moved the live tree aside and swapped the extracted one in, which opened
    a window where a failing rename left a product with no code directory at all — far worse
    than a regressive round. The merge design closes that window structurally: the target is
    never moved, only written into. This test breaks the copy step to prove the tree survives
    a mid-restore failure rather than trusting the argument.
    """
    code = _tree(tmp_path, "measured")
    save_snapshot("prod-x", code, tmp_path)
    (code / "backend" / "app" / "main.py").write_text("# broken by the round\n", encoding="utf-8")

    import core.round_regression_guard as guard

    calls = {"n": 0}
    real_copy = guard.shutil.copy2

    def flaky_copy(src, dst, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_copy(src, dst, *a, **kw)

    monkeypatch.setattr(guard.shutil, "copy2", flaky_copy)
    assert guard.restore_snapshot("prod-x", code, tmp_path) is False
    monkeypatch.undo()

    assert code.is_dir(), "the product was left with no code directory"
    assert any(code.rglob("*.py")), "the tree was emptied by a failed restore"
    # And no staging directory left lying beside it, which a later round would walk into.
    assert not list(code.parent.glob("*.restoring"))


def test_snapshot_of_a_missing_tree_is_not_an_error(tmp_path):
    assert save_snapshot("prod-x", tmp_path / "code" / "nope", tmp_path) is False


def test_a_partial_snapshot_cannot_be_restored_over_good_code(tmp_path):
    """Snapshots are written to a temp file and swapped, so a truncated archive is never live."""
    code = _tree(tmp_path, "measured")
    save_snapshot("prod-x", code, tmp_path)
    archive = tmp_path / "backups" / "round-guard" / "prod-x.tar.gz"
    assert archive.is_file()
    with tarfile.open(archive, "r:gz") as tar:
        assert tar.getmembers(), "the archive holds the tree"
    leftovers = list((tmp_path / "backups" / "round-guard").glob("*.partial"))
    assert leftovers == [], f"temp archives left behind: {leftovers}"


def test_snapshot_overwrites_rather_than_accumulating(tmp_path):
    """One slot per product: keeping every round of an 85-file tree filled a disk to 98% once."""
    code = _tree(tmp_path, "first")
    save_snapshot("prod-x", code, tmp_path)
    (code / "backend" / "app" / "main.py").write_text("# second\n", encoding="utf-8")
    save_snapshot("prod-x", code, tmp_path)

    files = list((tmp_path / "backups" / "round-guard").iterdir())
    assert len(files) == 1, f"snapshots accumulated: {files}"

    (code / "backend" / "app" / "main.py").write_text("# third\n", encoding="utf-8")
    restore_snapshot("prod-x", code, tmp_path)
    assert (code / "backend" / "app" / "main.py").read_text(encoding="utf-8") == "# second\n"


# --- what the next round is told ------------------------------------------------------


def test_the_hint_says_the_tree_was_restored_and_not_to_repeat_the_edit():
    """Without this the next round re-applies the reverted change and the loop spins."""
    hint = revert_hint(10, 18, ["frontend build: TS1192 no default export"])
    assert "REVERTED" in hint
    assert "10 → 18" in hint
    assert "Do not re-apply" in hint
    assert "TS1192" in hint


def test_the_hint_survives_having_no_outstanding_list():
    assert "REVERTED" in revert_hint(3, 5, [])


# --- persistence ---------------------------------------------------------------------


def test_the_baseline_survives_a_sqlite_round_trip():
    """A score that does not persist degrades the guard to accepting everything.

    New top-level product fields are silently dropped by the SQLite backend unless they are
    in the allow-list, and a JSON-backend test would not catch it.
    """
    from orchestrator.product_extras import (
        PRODUCT_EXTRA_KEYS,
        extract_product_extras,
        extras_from_json,
        extras_to_json,
    )

    assert "last_qa_defect_score" in PRODUCT_EXTRA_KEYS
    assert "reverted_round_count" in PRODUCT_EXTRA_KEYS

    product = {"id": "prod-x", "last_qa_defect_score": 14, "reverted_round_count": 2}
    restored = extras_from_json(extras_to_json(extract_product_extras(product)))
    assert restored["last_qa_defect_score"] == 14
    assert restored["reverted_round_count"] == 2


def test_the_snapshot_is_taken_once_per_round_not_once_per_write_pass():
    """Structural: the snapshot must sit OUTSIDE the developer's retry loop.

    Inside it, the guard quietly disarms itself. The write-time self-check can send a round
    back for another pass, and the second pass would snapshot a tree that already carries the
    first pass's edits — so a later revert restores half of the round it is undoing, and the
    reference to the last QA-measured state is gone. Observed in production as two
    "snapshotted the measured tree" lines for a single developer task.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "agents" / "dev.py"
    text = src.read_text(encoding="utf-8")

    assert text.count("save_snapshot(") == 1, "more than one snapshot call site"
    loop_at = text.index("for attempt in range(max_attempts)")
    snap_at = text.index("save_snapshot(")
    assert snap_at < loop_at, (
        "the snapshot is inside the retry loop, so a second write pass overwrites the "
        "measured tree with a partially-edited one"
    )


def test_installed_dependencies_are_not_archived(tmp_path):
    """A 592 MB tree produced a 151 MB archive per round because node_modules was in it.

    Per round, per product, on a disk this project has already filled to 98% once — from a
    leak in my own gate. Installed output is reinstallable and is not the product.
    """
    code = _tree(tmp_path, "measured")
    heavy = code / "frontend" / "node_modules" / "react"
    heavy.mkdir(parents=True)
    (heavy / "index.js").write_text("x" * 50_000, encoding="utf-8")
    (code / "frontend" / "dist" / "assets").mkdir(parents=True)
    (code / "frontend" / "dist" / "assets" / "app.js").write_text("y" * 50_000, encoding="utf-8")
    (code / "backend" / "__pycache__").mkdir(parents=True)
    (code / "backend" / "__pycache__" / "m.pyc").write_bytes(b"z" * 50_000)

    assert save_snapshot("prod-x", code, tmp_path) is True
    archive = tmp_path / "backups" / "round-guard" / "prod-x.tar.gz"
    with tarfile.open(archive, "r:gz") as tar:
        names = [m.name for m in tar.getmembers()]
    assert not any("node_modules" in n for n in names), names
    assert not any("dist" in n for n in names), names
    assert not any("__pycache__" in n for n in names), names
    assert any(n.endswith("main.py") for n in names), "product source must still be archived"


def test_a_restore_leaves_installed_dependencies_alone(tmp_path):
    """Otherwise every revert pays for a fresh npm install, and QA's build becomes the
    slowest part of a round that produced nothing."""
    code = _tree(tmp_path, "measured")
    mods = code / "frontend" / "node_modules" / "react"
    mods.mkdir(parents=True)
    (mods / "index.js").write_text("installed\n", encoding="utf-8")
    save_snapshot("prod-x", code, tmp_path)

    (code / "backend" / "app" / "main.py").write_text("# broken\n", encoding="utf-8")
    (code / "backend" / "app" / "extra.py").write_text("# added by the round\n", encoding="utf-8")

    assert restore_snapshot("prod-x", code, tmp_path) is True
    assert (mods / "index.js").read_text(encoding="utf-8") == "installed\n", (
        "node_modules was deleted by the restore"
    )
    assert (code / "backend" / "app" / "main.py").read_text(encoding="utf-8") == "# measured\n"
    assert not (code / "backend" / "app" / "extra.py").exists(), "the round's addition survived"


def test_an_emptied_package_directory_is_pruned(tmp_path):
    """A leftover empty folder still reads as a module to the import checks."""
    code = _tree(tmp_path, "measured")
    save_snapshot("prod-x", code, tmp_path)
    pkg = code / "backend" / "app" / "invented"
    pkg.mkdir(parents=True)
    (pkg / "thing.py").write_text("# invented\n", encoding="utf-8")

    restore_snapshot("prod-x", code, tmp_path)
    assert not pkg.exists(), "an emptied directory the round created was left behind"


def test_the_qa_sandbox_venvs_are_not_archived(tmp_path):
    """QA builds preview environments INSIDE the product tree — 161 MB each, two of them.

    Excluding node_modules alone still produced an 85 MB archive; these were the rest. They
    are rebuilt on demand, so archiving them buys nothing and costs the disk.
    """
    code = _tree(tmp_path, "measured")
    venv = code / ".aicom_sandbox" / "journey-prod-x" / "preview-venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "big.so").write_bytes(b"q" * 80_000)

    save_snapshot("prod-x", code, tmp_path)
    with tarfile.open(tmp_path / "backups" / "round-guard" / "prod-x.tar.gz", "r:gz") as tar:
        names = [m.name for m in tar.getmembers()]
    assert not any(".aicom_sandbox" in n for n in names), names
    assert any(n.endswith("main.py") for n in names)


def test_a_restore_does_not_destroy_the_qa_sandbox(tmp_path):
    """Deleting it mid-run would break the very measurement the guard depends on."""
    code = _tree(tmp_path, "measured")
    venv = code / ".aicom_sandbox" / "e2e-prod-x"
    venv.mkdir(parents=True)
    (venv / "marker").write_text("live\n", encoding="utf-8")
    save_snapshot("prod-x", code, tmp_path)

    (code / "backend" / "app" / "main.py").write_text("# broken\n", encoding="utf-8")
    assert restore_snapshot("prod-x", code, tmp_path) is True
    assert (venv / "marker").read_text(encoding="utf-8") == "live\n"


def test_the_hint_does_not_present_discarded_findings_as_work():
    """The compounding bug: a revert restored the code and kept the wrong diagnosis.

    Observed as a monotone climb of 72 → 99 → 113 in severity weight while the tree was being
    byte-for-byte correctly reverted every round. The tree on disk had 15 defects; the next
    round was handed the rejected round's 39 and edited against a description of a tree that
    no longer existed, so each rejected round left a more wrong list than the last.
    """
    hint = revert_hint(41, 113, ["Backend realism: constant-only API responses"])
    assert "context only" in hint.lower()
    assert "DISCARDED" in hint
    assert "outstanding" not in hint.lower(), (
        "calling discarded findings 'outstanding' is what made the next round chase phantoms"
    )


def test_the_accepted_diagnosis_is_in_the_persistence_allowlist():
    """It must survive a cycle, or a revert restores code with someone else's findings."""
    from orchestrator.product_extras import (
        PRODUCT_EXTRA_KEYS,
        extract_product_extras,
        extras_from_json,
        extras_to_json,
    )

    assert "last_accepted_bug_context" in PRODUCT_EXTRA_KEYS
    ctx = {"source": "qa", "qa_findings": [{"severity": "high", "title": "x"}]}
    product = {"id": "prod-x", "last_accepted_bug_context": ctx}
    restored = extras_from_json(extras_to_json(extract_product_extras(product)))
    assert restored["last_accepted_bug_context"]["qa_findings"][0]["title"] == "x"


def test_the_guard_swaps_the_diagnosis_with_the_tree():
    """Structural: the revert branch must restore last_bug_context, not only the files."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    text = src.read_text(encoding="utf-8")
    guard_at = text.index("def _guard_round_regression(")
    # To the end of the function, not a fixed number of characters: a magic 4000 silently stopped
    # covering the revert branch as soon as the accept branch grew.
    body = text[guard_at : text.index("\ndef _refresh_static_findings(", guard_at)]
    assert 'product["last_accepted_bug_context"] = accepted_ctx' in body, "accept does not store it"
    assert 'product["last_bug_context"] = accepted_ctx' in body, "revert does not restore it"
    assert 'product.pop("last_bug_context", None)' in body, (
        "with no accepted diagnosis the rejected one must be dropped, not passed on"
    )


def test_findings_that_do_not_repeat_get_no_vote_on_the_revert():
    """The score exists to compare two rounds, so an unrepeatable term makes it a coin flip.

    Measured from one baseline tree of 41: scores of 67, 71, 84 and 106 for rounds that touched
    21, 1 and 21 files. A ONE-file round scored 71 while a twenty-one-file round scored 67 — the
    number tracked the LLM reviewer's sample rather than the round's effect, and twelve
    consecutive rounds were reverted on it.
    """
    deterministic_only = {"bugs_found": [{"severity": "critical", "title": "no boot"}]}
    with_llm_noise = {
        "bugs_found": [
            {"severity": "critical", "title": "no boot"},
            {"severity": "critical", "title": "hunch", "scored_by_guard": False},
            {"severity": "high", "title": "another hunch", "scored_by_guard": False},
        ]
    }
    assert qa_defect_score(with_llm_noise) == qa_defect_score(deterministic_only), (
        "an unrepeatable finding still moves the score, so the revert decision is partly random"
    )


def test_excluded_findings_still_reach_the_developer():
    """They are reported work, just not voters. Dropping them would lose real review value."""
    from pathlib import Path

    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    block = qa[qa.index('_llm_bug.setdefault("source", "llm_review")') - 700 :][:1400]
    assert "all_bugs.append(_llm_bug)" in block, "the LLM findings were dropped, not just unscored"
    assert 'setdefault("scored_by_guard", False)' in block


def test_an_absent_flag_still_counts():
    """Only an explicit False excludes; anything unmarked is deterministic and votes."""
    assert qa_defect_score({"bugs_found": [{"severity": "low"}]}) == 1
    assert qa_defect_score({"bugs_found": [{"severity": "low", "scored_by_guard": True}]}) == 1


def test_only_gates_shown_to_repeat_get_a_vote():
    """Established by measurement: the same tree measured twice, identical hash before and after.

    module_health 2, frontend_build 3, demo_journey 3 — weight 26 both runs. The guard's stored
    baseline for that same tree was 41, so fifteen points came from terms outside that set: a
    browser crawl whose visual findings depend on render timing, an LLM spec-alignment judgement,
    a maintainability review, a methodology gate. Thirteen rounds were reverted on a number that
    was a third unrepeatable, including a one-file round that scored 71 against a baseline of 41.
    """
    from core.round_regression_guard import GUARD_SCORED_GATES

    scored = {"bugs_found": [
        {"severity": "critical", "title": "Module health: duplicate_tablename"},
        {"severity": "high", "title": "Frontend build: TS1192 no default export"},
        {"severity": "high", "title": "Demo journey: demo_journey_5xx:/api/advisory"},
    ]}
    plus_noise = {"bugs_found": scored["bugs_found"] + [
        {"severity": "high", "title": "Demo/TZ gate: visual_app_missing_skeleton"},
        {"severity": "high", "title": "Browser E2E: a11y_missing_h1"},
        {"severity": "high", "title": "Methodology gate (analytics_bi): domain_api_endpoint_missing"},
    ]}
    assert qa_defect_score(plus_noise) == qa_defect_score(scored), (
        "a gate not shown to repeat still moves the score"
    )
    assert "module health" in GUARD_SCORED_GATES
    assert "demo/tz gate" not in GUARD_SCORED_GATES


def test_a_finding_with_no_gate_prefix_still_counts():
    """Absence of a prefix is not evidence of noise; only a known-unrepeatable gate is."""
    assert qa_defect_score({"bugs_found": [{"severity": "high", "title": "plain finding"}]}) == 3


def test_the_whitelist_is_a_whitelist():
    """A new gate must default to not deciding whether work is thrown away."""
    unknown = {"bugs_found": [{"severity": "critical", "title": "Brand new gate: something"}]}
    assert qa_defect_score(unknown) == 0, (
        "an unrecognised gate votes by default, so adding one silently changes the revert rule"
    )
