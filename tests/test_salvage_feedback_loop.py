"""A silent revert is an instruction to repeat.

Sentinel (prod-bdb1634806de) spent twelve days here. QA told it to fix `capability_never_invoked`
in `backend/app/services/aimarket_participant.py`; the developer edited exactly that file, round
after round; each edit raised the static defect count because it restored a call to a client
method that does not exist yet; the salvage step gave the file back; and the round reported
"0 files", which `_round_produced_output` reads as a provider outage — so the repair budget was
never charged and the loop never reached the limit that escalates a product to a human.

Round 31 of 40, unchanged across a dozen attempts. Free, silent, and eternal.

Two things were missing, and this file guards both:
  * the developer was never told WHAT its reverted edit introduced, so it made the same
    one-sided edit again;
  * a round emptied by our own guards was accounted for as a round that never happened.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.dev import (
    _clear_salvage_notes,
    _load_salvage_notes,
    _record_salvage_notes,
    _salvage_notes_path,
)


def _round_produced_output(product, output):
    """`orchestrator/__init__.py` imports aiosqlite, which is absent from some of this repo's
    interpreters, and a rule about a dict of counters has no business needing a database driver.
    Stubbing the optional driver is preferable to loading by path (the module imports from its
    own package, so the path trick does not avoid the __init__) and far preferable to copying the
    twenty lines under test into the test, which would assert nothing about the shipped code."""
    import importlib
    import sys
    import types

    sys.modules.setdefault("aiosqlite", types.ModuleType("aiosqlite"))
    module = importlib.import_module("orchestrator.task_executor_agent")
    return module._round_produced_output(product, output)


class _Out:
    def __init__(self, data):
        self.data = data


# ── the developer's note to its own next round ───────────────────────────────────────────────


def test_the_note_names_the_file_and_what_the_edit_introduced(tmp_path):
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    _record_salvage_notes(
        code_root,
        "prod-x",
        {"backend/app/services/aimarket_participant.py": ["missing_attribute: atlas_client.invoke"]},
    )
    lines = _load_salvage_notes(tmp_path, "prod-x")
    assert len(lines) == 1
    # Both halves matter: which file, and why it came back. Either alone is unactionable.
    assert "aimarket_participant.py" in lines[0]
    assert "missing_attribute: atlas_client.invoke" in lines[0]


def test_the_note_lives_beside_the_qa_reports_not_in_the_product_tree(tmp_path):
    """Anything written into the code tree becomes an untracked file inside the very tree the
    defect score is measured over."""
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    path = _salvage_notes_path(code_root, "prod-x")
    assert path == tmp_path / "bugs" / "prod-x" / "salvage_notes.json"
    assert code_root not in path.parents


def test_an_edit_that_introduced_nothing_nameable_still_says_so(tmp_path):
    """"Given back for no defect this score can name" is itself information — it means the score,
    not the edit, is what rejected the round."""
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    _record_salvage_notes(code_root, "prod-x", {"app/thing.py": []})
    line = _load_salvage_notes(tmp_path, "prod-x")[0]
    assert "app/thing.py" in line
    assert "no defect this score can name" in line


def test_notes_accumulate_but_stay_bounded(tmp_path):
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    for i in range(20):
        _record_salvage_notes(code_root, "prod-x", {f"app/f{i}.py": [f"defect_{i}"]})
    raw = json.loads(_salvage_notes_path(code_root, "prod-x").read_text())
    assert 0 < len(raw) <= 6


def test_a_landed_round_clears_the_dead_ends(tmp_path):
    """They describe edits against a tree that no longer exists. Handing them on is the mistake
    the round guard made when it restored a rejected diagnosis beside a reverted tree."""
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    _record_salvage_notes(code_root, "prod-x", {"app/a.py": ["d"]})
    assert _load_salvage_notes(tmp_path, "prod-x")
    _clear_salvage_notes(tmp_path, "prod-x")
    assert _load_salvage_notes(tmp_path, "prod-x") == []


def test_no_notes_is_not_an_error(tmp_path):
    assert _load_salvage_notes(tmp_path, "never-seen") == []
    _clear_salvage_notes(tmp_path, "never-seen")  # must not raise


def test_a_corrupt_note_file_is_ignored_not_fatal(tmp_path):
    (tmp_path / "bugs" / "prod-x").mkdir(parents=True)
    (tmp_path / "bugs" / "prod-x" / "salvage_notes.json").write_text("{not json", encoding="utf-8")
    assert _load_salvage_notes(tmp_path, "prod-x") == []


# ── a round we emptied ourselves is a spent round ────────────────────────────────────────────


def test_a_round_whose_files_we_reclaimed_charges_the_budget():
    """The provider answered and the developer worked; we removed the result. Accounting that as
    "never attempted" is what made the loop free."""
    assert _round_produced_output({}, _Out({"file_count": 0, "reclaimed_by_guard": 1,
                                            "reclaimed_paths": ["a.py"]})) is True


def test_a_genuine_provider_outage_still_costs_nothing():
    """The original rule stands: a 402 or a timeout must not spend the repair budget. It once
    silently consumed twenty-five rounds."""
    assert _round_produced_output({}, _Out({"file_count": 0})) is False
    assert _round_produced_output({}, _Out({"file_count": 0, "reclaimed_by_guard": 0})) is False
    assert _round_produced_output({}, _Out({})) is False
    assert _round_produced_output({}, _Out(None)) is False


def test_a_productive_round_is_unaffected():
    assert _round_produced_output({}, _Out({"file_count": 3})) is True
    assert _round_produced_output({}, _Out({"files": [{"path": "a.py"}]})) is True


def test_a_landed_round_that_reclaimed_work_keeps_its_note(tmp_path):
    """The two mechanisms must not cancel each other.

    Measured live on Sentinel: salvage gave back `routers/advisory.py` (the ATLAS wiring), wrote
    the note naming `api_route_shadows_spa, missing_symbol` — and the clear-on-land branch deleted
    it two statements later, because the round's other two files still stood so it counted as
    landed. The note describing what was taken back is the entire point of the round; a round that
    reclaimed anything must keep it.

    This test encodes the RULE the caller implements (`landed and not salvaged`), because the
    caller is 300 lines inside a method that needs an LLM, a code tree and a sandbox to reach.
    """
    code_root = tmp_path / "code" / "prod-x"
    code_root.mkdir(parents=True)
    _record_salvage_notes(code_root, "prod-x", {"routers/advisory.py": ["api_route_shadows_spa"]})

    def clear_if_appropriate(landed: bool, salvaged: set) -> None:
        if landed and not salvaged:
            _clear_salvage_notes(tmp_path, "prod-x")

    # Landed, but work was reclaimed -> the note survives.
    clear_if_appropriate(True, {"routers/advisory.py"})
    assert _load_salvage_notes(tmp_path, "prod-x"), "the note was erased by the round that made it"

    # Landed clean -> stale dead ends go.
    clear_if_appropriate(True, set())
    assert _load_salvage_notes(tmp_path, "prod-x") == []


def test_the_caller_binds_salvaged_before_reading_it():
    """`salvaged` is assigned only inside the regression branch, so the clear-on-land check would
    raise NameError on a round that never regressed — a guard becoming a crash on the happy path."""
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text("utf-8")
    tree = ast.parse(src)
    binds = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "salvaged"
    ]
    reads = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.UnaryOp)
        and isinstance(n.op, ast.Not)
        and isinstance(n.operand, ast.Name)
        and n.operand.id == "salvaged"
    ]
    assert binds, "no unconditional `salvaged: set = set()` binding found"
    assert reads, "no `not salvaged` read found — did the clear-on-land rule change?"
    assert min(binds) < min(reads), "salvaged is read before it is unconditionally bound"
