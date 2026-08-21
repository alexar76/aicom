"""A scope limit that makes the tree worse is not a limit, it is a bug.

Watched live, twice in a row with identical numbers:

    Reverted 5 out-of-scope edit(s) (round scoped to models/audit.py, models/advisory.py,
    services/cache.py): backend/app/deps.py, backend/app/routers/analytics.py,
    backend/tests/e2e/test_widget_e2e.py, backend/tests/unit/test_rule_engine.py,
    frontend/src/components/Operator/Dashboard.tsx
    Repair round wrote 3 file(s), 0 identical to disk
    Rejected repair round: static defects would rise 16 → 24; tree restored

QA scoped the round to three files. The round wrote those three *and* the files that import the
symbols it had just moved. Reverting the importers left the new definitions in place with their
callers rolled back, so the tree got worse than before the round, the developer's own check
rejected it, and the next attempt reproduced the same thing exactly. Every attempt burned that way,
and nothing in the loop was a model decision — all three steps were rules.

So each candidate revert is measured before it is kept. A file whose revert makes the tree worse is
a necessary companion of the in-scope change; a file whose revert costs nothing is sprawl and goes.
Greedy, in sorted order, so one round always produces one answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.dev import _revert_out_of_scope_writes

QUIET = lambda *a, **k: None  # noqa: E731


def _tree(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def test_a_companion_edit_is_kept_when_reverting_it_would_break_the_tree(tmp_path):
    """The live case, reduced: a definition moves and its importer follows."""
    code = tmp_path / "code"
    # Before: cache.py defined ReadingCache, deps.py imported it.
    before_deps = "from .services.cache import ReadingCache\n\ncache = ReadingCache()\n"
    # The round renames it in the in-scope file and updates the out-of-scope importer.
    _tree(
        code,
        {
            "backend/app/services/cache.py": "class MeshCache:\n    pass\n",
            "backend/app/deps.py": "from .services.cache import MeshCache\n\ncache = MeshCache()\n",
            "backend/app/routers/analytics.py": "# unrelated churn\n",
        },
    )
    previous = {
        "backend/app/services/cache.py": "class ReadingCache:\n    pass\n",
        "backend/app/deps.py": before_deps,
        "backend/app/routers/analytics.py": "# original\n",
    }

    reverted = _revert_out_of_scope_writes(
        code,
        previous,
        ["backend/app/services/cache.py", "backend/app/deps.py", "backend/app/routers/analytics.py"],
        ["backend/app/services/cache.py"],
        log=QUIET,
        product_id="prod-x",
    )

    assert "backend/app/deps.py" not in reverted, (
        "the importer of the moved symbol was reverted, which is what produced 16 → 24"
    )
    assert "MeshCache" in (code / "backend/app/deps.py").read_text(encoding="utf-8")
    # The genuinely unrelated file is still sprawl and still goes.
    assert "backend/app/routers/analytics.py" in reverted
    assert (code / "backend/app/routers/analytics.py").read_text(encoding="utf-8") == "# original\n"


def test_plain_sprawl_is_still_reverted(tmp_path):
    """The behaviour this guard exists for must survive the fix.

    A round rewrites the whole tree whatever the prompt says; when only the backend needs repair,
    that is forty-odd chances to lose a working frontend.
    """
    code = tmp_path / "code"
    _tree(
        code,
        {
            "backend/app/main.py": "x = 2\n",
            "frontend/src/App.tsx": "export const App = () => null\n",
            "README.md": "new\n",
        },
    )
    previous = {
        "backend/app/main.py": "x = 1\n",
        "frontend/src/App.tsx": "export const App = () => <div/>\n",
        "README.md": "old\n",
    }
    reverted = _revert_out_of_scope_writes(
        code,
        previous,
        ["backend/app/main.py", "frontend/src/App.tsx", "README.md"],
        ["backend/"],
        log=QUIET,
        product_id="prod-x",
    )
    assert reverted == {"frontend/src/App.tsx", "README.md"}
    assert (code / "README.md").read_text(encoding="utf-8") == "old\n"


def test_a_brand_new_file_outside_the_scope_is_still_removed(tmp_path):
    code = tmp_path / "code"
    _tree(code, {"backend/app/main.py": "x = 1\n", "docs/extra.md": "new file\n"})
    reverted = _revert_out_of_scope_writes(
        code,
        {"backend/app/main.py": "x = 1\n"},
        ["backend/app/main.py", "docs/extra.md"],
        ["backend/"],
        log=QUIET,
        product_id="prod-x",
    )
    assert reverted == {"docs/extra.md"}
    assert not (code / "docs" / "extra.md").exists()


def test_a_new_companion_file_is_kept_when_it_is_load_bearing(tmp_path):
    """A round may need to CREATE the module the in-scope file now imports."""
    code = tmp_path / "code"
    _tree(
        code,
        {
            "backend/app/services/cache.py": "from .backend_store import Store\n\nc = Store()\n",
            "backend/app/services/backend_store.py": "class Store:\n    pass\n",
        },
    )
    reverted = _revert_out_of_scope_writes(
        code,
        {"backend/app/services/cache.py": "c = None\n"},
        ["backend/app/services/cache.py", "backend/app/services/backend_store.py"],
        ["backend/app/services/cache.py"],
        log=QUIET,
        product_id="prod-x",
    )
    assert "backend/app/services/backend_store.py" not in reverted, (
        "deleting the module the in-scope file imports leaves an unresolvable import"
    )
    assert (code / "backend/app/services/backend_store.py").exists()


def test_the_answer_is_the_same_every_time(tmp_path):
    """Greedy order must be deterministic or one round gives two answers."""

    def run() -> set[str]:
        code = tmp_path / f"code{run.counter}"
        run.counter += 1
        _tree(
            code,
            {
                "backend/app/services/cache.py": "class MeshCache:\n    pass\n",
                "backend/app/deps.py": "from .services.cache import MeshCache\n\nc = MeshCache()\n",
                "backend/app/z.py": "# churn\n",
                "backend/app/a.py": "# churn\n",
            },
        )
        return _revert_out_of_scope_writes(
            code,
            {
                "backend/app/services/cache.py": "class ReadingCache:\n    pass\n",
                "backend/app/deps.py": "from .services.cache import ReadingCache\n\nc = ReadingCache()\n",
                "backend/app/z.py": "# original\n",
                "backend/app/a.py": "# original\n",
            },
            ["backend/app/services/cache.py", "backend/app/deps.py", "backend/app/z.py", "backend/app/a.py"],
            ["backend/app/services/cache.py"],
            log=QUIET,
            product_id="prod-x",
        )

    run.counter = 0
    answers = {frozenset(run()) for _ in range(3)}
    assert len(answers) == 1, answers


def test_no_scope_means_no_reverts(tmp_path):
    """An unscoped round is bounded by the batch caps, not by this."""
    code = tmp_path / "code"
    _tree(code, {"backend/app/main.py": "x = 2\n"})
    assert _revert_out_of_scope_writes(
        code, {"backend/app/main.py": "x = 1\n"}, ["backend/app/main.py"], [],
        log=QUIET, product_id="prod-x",
    ) == set()


def test_the_reason_a_write_survived_is_logged(tmp_path):
    """Silence here reads as the scope limit being ignored."""
    lines: list[tuple[str, str]] = []
    code = tmp_path / "code"
    _tree(
        code,
        {
            "backend/app/services/cache.py": "class MeshCache:\n    pass\n",
            "backend/app/deps.py": "from .services.cache import MeshCache\n\nc = MeshCache()\n",
        },
    )
    _revert_out_of_scope_writes(
        code,
        {
            "backend/app/services/cache.py": "class ReadingCache:\n    pass\n",
            "backend/app/deps.py": "from .services.cache import ReadingCache\n\nc = ReadingCache()\n",
        },
        ["backend/app/services/cache.py", "backend/app/deps.py"],
        ["backend/app/services/cache.py"],
        log=lambda level, msg: lines.append((level, msg)),
        product_id="prod-x",
    )
    assert any("reverting them made the tree worse" in m for _l, m in lines), lines


# --- and the rejection has to say what moved ---------------------------------------------------


def test_the_breakdown_is_taken_before_the_rollback():
    """Structural, and it caught a real instance of the trap it guards.

    The first version logged the breakdown from inside the rejection branch, which runs *after* the
    rollback has already put the previous tree back. It reported `nothing individually — check the
    weights` about a round whose score had moved 30 → 34: a perfectly accurate measurement of its own
    undo. A diagnostic that measures after the revert can only ever say "nothing changed".
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    region = src[src.index("if patch_mode and before_score is not None:") :]
    region = region[: region.index("system_prompt = build_developer_system_prompt")] if "system_prompt = build_developer_system_prompt" in region else region[:6000]
    capture = region.index("after_parts = _tree_defect_breakdown(code_root)")
    rollback = region.index("for rel, content in previous_content.items():")
    assert capture < rollback, "the breakdown is measured after the tree was put back"
    assert "_breakdown_delta(before_parts, after_parts)" in region, (
        "the log re-measures instead of using the captured breakdown"
    )


def test_the_delta_names_only_what_moved():
    from agents.dev import _breakdown_delta

    text = _breakdown_delta(
        {"missing_attribute": 2, "duplicate_tablename": 1},
        {"missing_attribute": 4, "duplicate_tablename": 1, "undefined_name": 3},
    )
    assert "missing_attribute 2→4" in text
    assert "undefined_name 0→3" in text
    assert "duplicate_tablename" not in text, "an unchanged class was reported as movement"


def test_an_unexplained_rise_says_so_instead_of_staying_silent():
    """If every class is level and the total still moved, the weights are the place to look."""
    from agents.dev import _breakdown_delta

    assert "check the weights" in _breakdown_delta({"missing_attribute": 2}, {"missing_attribute": 2})


def test_the_rejection_names_the_defects_it_added():
    """A count says where to look; a name settles what happened.

    Three rounds in a row were rejected on `frontend_import 0→3` and `0→5`. That is enough to know
    the frontend is involved and not enough to know whether the round wrote a bad import or the
    detector is wrong about a good one — the same question that made counts worth logging, one level
    down.
    """
    from pathlib import Path

    from agents.dev import _identities_appeared

    text = _identities_appeared(
        {"frontend_import": set(), "missing_symbol": {"app.a.B"}},
        {
            "frontend_import": {"Dashboard.tsx -> ./AnalyticsWorkspace"},
            "missing_symbol": {"app.a.B"},
        },
    )
    assert text == "frontend_import: Dashboard.tsx -> ./AnalyticsWorkspace", text

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    region = src[src.index("if patch_mode and before_score is not None:") :][:6000]
    capture = region.index("after_ids = _tree_defect_identities(code_root)")
    rollback = region.index("for rel, content in previous_content.items():")
    assert capture < rollback, "the identities are collected after the tree was put back"


def test_pre_existing_defects_are_not_reported_as_added():
    """Otherwise every rejection reads as if the round caused everything."""
    from agents.dev import _identities_appeared

    same = {"frontend_import": {"a.tsx -> ./x"}}
    assert _identities_appeared(same, same) == ""


def test_a_long_list_is_truncated_and_says_so():
    from agents.dev import _identities_appeared

    text = _identities_appeared({}, {"missing_symbol": {f"app.m.S{i}" for i in range(9)}})
    assert "+3 more" in text, text


def test_a_dangling_import_alone_does_not_regenerate_the_round():
    """It starved the pipeline: QA had not run for 47 minutes.

    Eight consecutive four-minute attempts were spent on one dangling name, each a fresh chance to
    invent another, and the round never handed off — so none of the findings that would have named the
    real problem ever reached it. The check predates the ratchet it duplicates: the tree score already
    refuses a round that made things worse, the out-of-scope guard measures every write, and each batch
    is content-checked. What is left for the self-check is the case those miss, and a net-improving
    round with something still dangling is cheaper to hand off than to retry.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    region = src[src.index("broke = _self_check_written_files(") :][:2500]
    assert "if not broke or not _worse or attempt + 1 >= max_attempts:" in region
    assert "Handing off with" in region, "handing off with dangling imports is silent"
    # And the score it reads must exist however the round got here.
    assert "after_score: int | None = None" in src, (
        "patch_mode with no measurable baseline would raise NameError in that branch"
    )
