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

def _product_extras():
    """Load `orchestrator/product_extras.py` without importing the `orchestrator` PACKAGE.

    The package's `__init__` pulls in `aiosqlite`, which is absent from some of this repo's
    interpreters — so `from orchestrator.product_extras import …` made three tests fail on a
    missing database driver. Every function these tests exercise operates on plain dicts and
    JSON strings and has no business needing one. Skipping them instead would have been worse:
    the allow-list is exactly the mechanism whose failure mode is SILENT (a key absent from it
    is dropped on save, and no JSON-backend test can see that), so it must be verified wherever
    the suite runs, not only where a driver happens to be installed.
    """
    import importlib.util
    import pathlib as _p

    path = _p.Path(__file__).resolve().parents[1] / "orchestrator" / "product_extras.py"
    spec = importlib.util.spec_from_file_location("_product_extras_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


# Every finding below carries a `Module health: …` title. That is not decoration: since
# 0d8caa50 only findings whose title names a gate in GUARD_SCORED_GATES are scored at all, so a
# bare `{"severity": "critical"}` weighs ZERO. These three tests were written before that
# change and kept passing severity-only dicts, which made them assert "0 < 0" and "0 > 0" — they
# went red without ever describing anything false about the code. The intent each was written
# for is still right, so it is preserved and expressed against the contract that exists.
SCORED = "Module health: "


def _finding(severity: str, name: str = "duplicate_tablename", **extra):
    """A finding shaped the way a scored gate emits one."""
    return {"severity": severity, "title": SCORED + name, **extra}


def test_severity_is_weighted_not_counted():
    """One critical must outweigh two lows, or the guard reverts real progress.

    A round that turns a crash into a couple of lint findings is exactly the kind of round
    this loop needs to be able to land.
    """
    before = {"bugs_found": [_finding("critical")]}
    after = {"bugs_found": [_finding("low", "a"), _finding("low", "b")]}
    assert qa_defect_score(after) < qa_defect_score(before)


def test_an_unknown_severity_is_not_free():
    """Otherwise a round could relabel its findings and look like an improvement."""
    assert qa_defect_score({"bugs_found": [_finding("banana")]}) > 0
    assert qa_defect_score({"bugs_found": [{"title": SCORED + "no severity at all"}]}) > 0


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
    _pe = _product_extras()
    PRODUCT_EXTRA_KEYS = _pe.PRODUCT_EXTRA_KEYS
    extract_product_extras = _pe.extract_product_extras
    extras_from_json = _pe.extras_from_json
    extras_to_json = _pe.extras_to_json

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
    _pe = _product_extras()
    PRODUCT_EXTRA_KEYS = _pe.PRODUCT_EXTRA_KEYS
    extract_product_extras = _pe.extract_product_extras
    extras_from_json = _pe.extras_from_json
    extras_to_json = _pe.extras_to_json

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
    """They are reported work, just not voters. Dropping them would lose real review value.

    Asserted over the AST rather than over a slice of the file. The original version read
    `qa[index_of_a_string - 700:][:1400]` and looked for two substrings inside that window; when
    the test-hygiene filter was added to the same loop it pushed `all_bugs.append(_llm_bug)` past
    the 1400-character boundary, and the test went red while the behaviour it guards was intact.
    A test anchored to byte offsets in a source file fails on edits near it rather than on the
    change it exists to catch, which is worse than no test: it trains the reader to ignore it.
    """
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text("utf-8"))

    loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_llm_bug"
    ]
    assert loops, "no loop over the LLM reviewer's findings — has the marker been renamed?"

    def calls(loop, func_repr: str) -> list[ast.Call]:
        return [
            n
            for n in ast.walk(loop)
            if isinstance(n, ast.Call) and ast.unparse(n.func) == func_repr
        ]

    for loop in loops:
        appends = calls(loop, "all_bugs.append")
        assert any(
            a.args and ast.unparse(a.args[0]) == "_llm_bug" for a in appends
        ), "the LLM findings were dropped, not just unscored"

        vetoes = [
            c
            for c in calls(loop, "_llm_bug.setdefault")
            if len(c.args) == 2
            and getattr(c.args[0], "value", None) == "scored_by_guard"
            and getattr(c.args[1], "value", None) is False
        ]
        assert vetoes, "the findings vote on the revert again — scored_by_guard=False was lost"


def test_an_absent_flag_does_not_by_itself_grant_a_vote():
    """`scored_by_guard` is a veto, not a franchise.

    The original docstring said "anything unmarked is deterministic and votes", which stopped
    being true at 0d8caa50: a finding must ALSO come from a whitelisted gate. Both conditions,
    tested separately so a future change to either one names itself.
    """
    # Whitelisted gate, flag absent -> votes.
    assert qa_defect_score({"bugs_found": [_finding("low")]}) == 1
    # Whitelisted gate, flag explicitly True -> votes (True is not a special case).
    assert qa_defect_score({"bugs_found": [_finding("low", scored_by_guard=True)]}) == 1
    # Whitelisted gate, flag explicitly False -> vetoed.
    assert qa_defect_score({"bugs_found": [_finding("low", scored_by_guard=False)]}) == 0
    # Flag absent but NO gate prefix -> still no vote. This is the half the old test denied.
    assert qa_defect_score({"bugs_found": [{"severity": "low"}]}) == 0


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


def test_a_finding_with_no_gate_prefix_does_not_vote():
    """This test used to assert the OPPOSITE, and both versions cannot be right.

    It was written as `test_a_finding_with_no_gate_prefix_still_counts`, asserting weight 3 and
    reasoning that "absence of a prefix is not evidence of noise". Measurement overruled that at
    0d8caa50: prefixless findings come from the LLM reviewer, whose output differs between two
    runs over identical code, and one baseline tree scored 67, 71, 84 and 106 across rounds
    touching 21, 1 and 21 files — a one-file round outscoring a twenty-one-file round. A term
    that does not repeat cannot answer "is this round better than the last", so it does not get
    a vote. It is still reported to the developer as work; see
    `test_excluded_findings_still_reach_the_developer`.

    Left as a renamed test rather than deleted, because the file contained two contradictory
    contracts and a reader deserves to know which one won and why.
    """
    assert qa_defect_score({"bugs_found": [{"severity": "high", "title": "plain finding"}]}) == 0


def test_the_whitelist_is_a_whitelist():
    """A new gate must default to not deciding whether work is thrown away."""
    unknown = {"bugs_found": [{"severity": "critical", "title": "Brand new gate: something"}]}
    assert qa_defect_score(unknown) == 0, (
        "an unrecognised gate votes by default, so adding one silently changes the revert rule"
    )


# ── Fixed-point detection ────────────────────────────────────────────────────────────────────
# Sentinel (prod-bdb1634806de) accumulated 38 reverted rounds, four of them inside one
# five-hour log with byte-identical numbers (9 -> 12 every time, at 06:19, 09:05, 09:21, 10:03).
# The guard was working exactly as designed and that was the problem: it restores the tree AND
# the diagnosis, so the next round begins from identical inputs and a deterministic agent
# reproduces the identical edit. Nothing in the loop could break the symmetry, and `revert_hint`
# said "do not re-apply that approach" without ever naming the approach.


def test_the_same_rejected_tree_is_counted():
    from core.round_regression_guard import record_rejected_tree

    product: dict = {}
    assert record_rejected_tree(product, "deadbeef") == 1
    assert record_rejected_tree(product, "deadbeef") == 2
    assert record_rejected_tree(product, "deadbeef") == 3
    # A different rejected tree is progress of a sort, and counted separately.
    assert record_rejected_tree(product, "cafebabe") == 1


def test_an_unmeasurable_tree_is_not_counted_as_a_repeat():
    """"We cannot tell" and "we have seen this three times" are different facts, and only one of
    them may pause a product."""
    from core.round_regression_guard import record_rejected_tree

    product: dict = {}
    assert record_rejected_tree(product, None) == 0
    assert record_rejected_tree(product, "") == 0
    assert product.get("rejected_tree_fingerprints") in (None, {})


def test_a_second_identical_attempt_does_not_stop_the_pipeline():
    """A transient — a flaky preview, a timed-out install — is a real reason to produce the same
    edit twice, so the threshold must not fire on two."""
    from core.round_regression_guard import STUCK_AFTER, is_stuck

    assert STUCK_AFTER >= 3
    assert not is_stuck(1)
    assert not is_stuck(2)
    assert is_stuck(3)
    assert is_stuck(9)


def test_the_ledger_stays_bounded():
    from core.round_regression_guard import MAX_LEDGER_ENTRIES, record_rejected_tree

    product: dict = {}
    for i in range(MAX_LEDGER_ENTRIES * 3):
        record_rejected_tree(product, f"fp-{i}")
    assert len(product["rejected_tree_fingerprints"]) <= MAX_LEDGER_ENTRIES


def test_the_ledger_keeps_the_most_repeated_entry_when_it_evicts():
    """Eviction must not throw away the one digest that is about to trip the breaker."""
    from core.round_regression_guard import MAX_LEDGER_ENTRIES, record_rejected_tree

    product: dict = {}
    for _ in range(5):
        record_rejected_tree(product, "the-loop")
    for i in range(MAX_LEDGER_ENTRIES * 2):
        record_rejected_tree(product, f"noise-{i}")
    assert product["rejected_tree_fingerprints"].get("the-loop") == 5


def test_the_hint_names_the_repetition_instead_of_hinting_at_it():
    from core.round_regression_guard import revert_hint

    once = revert_hint(9, 12, ["a defect"], repeat_count=1)
    assert "EXACT tree" not in once, "a first rejection is not yet a loop"

    again = revert_hint(9, 12, ["a defect"], repeat_count=4)
    assert "4 times" in again
    assert "9 → 12" in again
    assert "cannot succeed" in again
    # It must offer a way out that is not "try again", or it is the same dead end with a count.
    assert "say so in your output" in again


def test_the_stuck_reason_states_the_observation_and_the_consequence():
    from core.round_regression_guard import stuck_reason

    reason = stuck_reason("prod-bdb1634806de", 3, 9, 12)
    assert "prod-bdb1634806de" in reason
    assert "3 times" in reason
    assert "9 -> 12" in reason
    assert "fixed point" in reason
    # An operator reading this must learn what is being asked of them.
    assert "human" in reason.lower()


def test_the_ledger_keys_are_persisted():
    """Under the SQLite backend a product key absent from PRODUCT_EXTRA_KEYS is dropped on save.
    A dropped `rejected_tree_fingerprints` resets the counter every cycle, so the breaker could
    never reach its threshold — a guard that silently does nothing, which is precisely the
    failure it exists to end. The JSON backend does not drop unknown keys, so no other test in
    this file would catch it."""
    keys = _product_extras().PRODUCT_EXTRA_KEYS
    for key in (
        "rejected_tree_fingerprints",
        "pipeline_stuck_reason",
        "pipeline_stuck_at",
        "qa_non_improvement_streak",
    ):
        assert key in keys, key


def test_equal_scores_are_not_a_revert_but_four_equals_are_a_plateau():
    """Equal is accepted (a trade), but a streak of equals with QA still failing is churn."""
    from core.round_regression_guard import (
        PLATEAU_AFTER,
        is_plateau,
        record_quality_round,
        verdict,
    )

    assert verdict(21, 21) == "accept"
    assert PLATEAU_AFTER >= 4
    product: dict = {}
    assert not is_plateau(record_quality_round(product, improved=False))
    assert not is_plateau(record_quality_round(product, improved=False))
    assert not is_plateau(record_quality_round(product, improved=False))
    assert is_plateau(record_quality_round(product, improved=False))
    assert product["qa_non_improvement_streak"] == 4


def test_an_improving_round_resets_the_plateau_streak():
    from core.round_regression_guard import record_quality_round

    product = {"qa_non_improvement_streak": 3}
    assert record_quality_round(product, improved=True) == 0
    assert product["qa_non_improvement_streak"] == 0


def test_mark_stuck_stamps_a_repair_resume_kind_not_post_devops():
    """Approve must grant another repair cycle, not skip to sales."""
    from core.round_regression_guard import mark_stuck, plateau_reason

    product: dict = {"id": "prod-bdb1634806de"}
    mark_stuck(product, plateau_reason("prod-bdb1634806de", 4, 21))
    assert product["human_review_kind"] == "qa_repair_stuck"
    assert "plateau" in product["pipeline_stuck_reason"]
    assert product["human_review_reason"] == product["pipeline_stuck_reason"]
    assert product.get("pipeline_stuck_at")


def test_the_plateau_reason_names_the_score_and_the_stop():
    from core.round_regression_guard import plateau_reason

    reason = plateau_reason("prod-bdb1634806de", 4, 21)
    assert "prod-bdb1634806de" in reason
    assert "4 consecutive" in reason
    assert "21" in reason
    assert "human" in reason.lower()


def test_the_accept_path_counts_non_improvement_and_parks_when_stuck():
    """Without this the guard accepts equals forever and the QA-fail handler enqueues developer."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "orchestrator" / "task_executor_agent.py"
    text = src.read_text(encoding="utf-8")
    guard = text[text.index("def _guard_round_regression(") : text.index("def _hold_if_stuck(")]
    assert "_note_non_improvement(product, pid, previous, score, breakthrough=breakthrough)" in guard
    assert "_note_non_improvement(product, pid, previous, score, breakthrough=False)" in guard

    qa_fail = text[text.index("_guard_round_regression(products[pid], pid, qa_result, host)") :]
    qa_fail = qa_fail[: qa_fail.index("elif security_gate_failed and pid in products")]
    assert 'if products[pid].get("pipeline_stuck_reason")' in qa_fail
    assert '"HUMAN_REVIEW_PENDING"' in qa_fail
    assert "try_auto_recovery_after_qa_failure" in qa_fail
    # Auto-recovery must not run on a stuck product (it would COMPLETE a tree QA just failed).
    stuck_branch = qa_fail[: qa_fail.index("else:")]
    assert "try_auto_recovery_after_qa_failure" not in stuck_branch


def test_idle_heal_does_not_advance_a_stuck_repair_park():
    """Sentinel already had post_devops approved, so HUMAN_REVIEW_PENDING used to mean sales."""
    from pathlib import Path

    from orchestrator.worker_task_planner import _REPAIR_PARK_KINDS, NextTaskPlanner

    parked_kinds = {
        "qa_repair_exhausted",
        "security_repair_exhausted",
        "qa_repair_stuck",
        "live_mesh_payment_ops",
    }
    assert parked_kinds <= set(_REPAIR_PARK_KINDS)

    # The guarantee, not its address: a product parked for any of these must get NO next task.
    # The field is `human_review_kind` — the one the gate actually reads. Writing the kind into
    # `pipeline_stuck_reason` (a free-text string set alongside it) makes this test pass without
    # ever entering the branch it claims to cover.
    planner = NextTaskPlanner()
    for kind in sorted(parked_kinds):
        product = {
            "id": "prod-parked",
            "state": "HUMAN_REVIEW_PENDING",
            "human_review_kind": kind,
            "pipeline_stuck_reason": f"parked: {kind}",
        }
        assert planner.create_next_task(product) is None, kind

    # The second reader, asserted the same way: by behaviour. A park honoured by only one of
    # the two is not a park, and grepping for the literal broke the moment it was reformatted.
    from orchestrator.task_queue_hygiene import missing_forward_task

    for kind in sorted(parked_kinds):
        product = {"id": "prod-parked", "state": "HUMAN_REVIEW_PENDING",
                   "human_review_kind": kind}
        assert missing_forward_task(product, []) is None, kind


def test_the_repair_park_guard_is_not_vacuous(monkeypatch):
    """The control case: the SAME product, parked for a non-repair reason, does advance.

    Without this the test above passes whether or not the guard exists — every
    HUMAN_REVIEW_PENDING product returns None when the post-devops gate is unapproved, so a
    test that never sets an approved gate proves nothing about the park kinds.
    """
    import web.backend.services.product_followup as followup

    from orchestrator.worker_task_planner import NextTaskPlanner

    monkeypatch.setattr(followup, "post_devops_human_review_approved", lambda pid: True)
    planner = NextTaskPlanner()

    approved = {"id": "prod-ok", "state": "HUMAN_REVIEW_PENDING",
                "human_review_kind": "post_devops"}
    advanced = planner.create_next_task(approved)
    assert advanced is not None, "control case must advance, or the guard test proves nothing"
    assert advanced.get("agent_type") == "sales"

    parked = {"id": "prod-parked", "state": "HUMAN_REVIEW_PENDING",
              "human_review_kind": "qa_repair_exhausted"}
    assert planner.create_next_task(parked) is None
