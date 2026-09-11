"""Two entries in one directory whose names differ only in case.

Found live as `components/UI/` next to `components/ui/`. TypeScript refuses the tree with TS1149 and
the build produces nothing — and the error prints ABSOLUTE paths nothing downstream can resolve, which
is how a one-directory rename survived a full informed round.

The twist that shaped these tests: the dev laptop's filesystem is itself case-insensitive, so the
collision literally cannot be created here — `UI/` and `ui/` are one directory on macOS. That is also
why the defect class matters: locally one spelling silently wins and everything works, then CI or the
deploy host (case-sensitive) refuses the tree. The behavioural test runs only where the fixture can
exist; the grouping and the wiring are tested everywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services.duplicate_module_check import find_case_collisions


def _fs_is_case_sensitive(tmp_path: Path) -> bool:
    (tmp_path / "probe_a").write_text("x", encoding="utf-8")
    return not (tmp_path / "PROBE_A").exists()


def test_the_live_shape_is_found_where_the_fs_allows_it(tmp_path):
    if not _fs_is_case_sensitive(tmp_path):
        pytest.skip("case-insensitive filesystem cannot host the fixture — verified live on prod instead")
    code = tmp_path / "code"
    (code / "frontend" / "src" / "components" / "UI").mkdir(parents=True)
    (code / "frontend" / "src" / "components" / "ui").mkdir(parents=True)
    (code / "frontend" / "src" / "components" / "ui" / "Button.tsx").write_text(
        "export const Button = 1\n", encoding="utf-8"
    )
    (code / "frontend" / "src" / "App.tsx").write_text(
        "import { Button } from './components/ui/Button'\n", encoding="utf-8"
    )
    found = find_case_collisions(code)
    assert len(found) == 1
    assert sorted(found[0]["spellings"]) == ["UI", "ui"]
    assert found[0]["keep"] == "ui", "the referenced spelling must win"
    assert "delete_files" in found[0]["detail"]


def test_a_clean_tree_is_silent(tmp_path):
    code = tmp_path / "code"
    (code / "frontend" / "src").mkdir(parents=True)
    (code / "frontend" / "src" / "App.tsx").write_text("export {}\n", encoding="utf-8")
    (code / "frontend" / "src" / "app.css").write_text("body {}\n", encoding="utf-8")
    assert find_case_collisions(code) == []


def test_same_name_in_different_directories_is_not_a_collision(tmp_path):
    code = tmp_path / "code"
    (code / "a").mkdir(parents=True)
    (code / "b").mkdir(parents=True)
    (code / "a" / "index.ts").write_text("export {}\n", encoding="utf-8")
    (code / "b" / "index.ts").write_text("export {}\n", encoding="utf-8")
    assert find_case_collisions(code) == []


def test_build_errors_lose_their_absolute_prefix():
    """TS1149 prints absolute paths, and nothing downstream can resolve those."""
    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "frontend_build_check.py"
    ).read_text(encoding="utf-8")
    strip_at = src.index('line.replace(str(product_code) + "/", "")')
    rel_at = src.index("errors = [_repo_relative(line, rel) for line in errors]")
    assert strip_at < rel_at, "absolute paths must be stripped before the relative rewrite"


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not case_twins" in passed_expr
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "5 * len(find_case_collisions(code_root, limit=200))" in score
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"case_collision"' in qa[: qa.index("# Deletions next")]


def test_the_finding_names_files_not_directories(tmp_path):
    """The first version pointed `file` at a directory, and the pipeline's own path resolver rejects
    directories — so the finding fell out of the repair scope, nothing was attached, and two informed
    rounds went to deps.py instead of the collision. delete_files also needs exact file paths;
    "delete UI/" is not an instruction it can execute."""
    if not _fs_is_case_sensitive(tmp_path):
        pytest.skip("case-insensitive filesystem cannot host the fixture")
    code = tmp_path / "code"
    (code / "c" / "UI").mkdir(parents=True)
    (code / "c" / "ui").mkdir(parents=True)
    (code / "c" / "UI" / "Skeleton.tsx").write_text("export const S = 1\n", encoding="utf-8")
    (code / "c" / "ui" / "Button.tsx").write_text("export const B = 1\n", encoding="utf-8")
    (code / "app.tsx").write_text("import { B } from './c/ui/Button'\n", encoding="utf-8")
    f = find_case_collisions(code)[0]
    assert f["file"].endswith(".tsx"), f["file"]
    assert f["drop_files"] == ["c/UI/Skeleton.tsx"]
    assert "c/UI/Skeleton.tsx" in f["detail"]


def test_the_file_field_names_the_file_to_delete(tmp_path):
    """The repair scope is built from `file`, and the work is on the drop side.

    Measured: `file` pointed at the keep side (ui/FeedbackStates.tsx, the first file in the kept
    directory), so every round was scoped to an innocent file — a round would delete UI/Toast.tsx,
    the actual instruction, and the out-of-scope revert would restore it. Round after round, while
    this one finding held both module_health and frontend_build red.
    """
    if not _fs_is_case_sensitive(tmp_path):
        pytest.skip("case-insensitive filesystem cannot host the fixture")
    code = tmp_path / "code"
    (code / "c" / "UI").mkdir(parents=True)
    (code / "c" / "ui").mkdir(parents=True)
    (code / "c" / "UI" / "Toast.tsx").write_text("export const T = 1\n", encoding="utf-8")
    (code / "c" / "ui" / "FeedbackStates.tsx").write_text("export const F = 1\n", encoding="utf-8")
    (code / "c" / "ui" / "Toast.tsx").write_text("export const T = 2\n", encoding="utf-8")
    (code / "app.tsx").write_text(
        "import { F } from './c/ui/FeedbackStates'\nimport { T } from './c/ui/Toast'\n",
        encoding="utf-8",
    )
    f = find_case_collisions(code)[0]
    assert f["keep"] == "ui"
    assert f["file"] == "c/UI/Toast.tsx", f["file"]


def test_the_case_twin_does_not_keep_the_victim_alive(tmp_path):
    """An import of ui/Toast is not an import of UI/Toast.tsx on the filesystem that matters.

    The still-imported guard matched any specifier ending in the stem, so the keep side's own
    importers were counted for the drop side — and in a case collision the keep twin exists by
    construction, which made the victim un-deletable: eleven informed rounds, a correct
    delete_files answer in each of the last three, all refused with "still imported by
    frontend/src/App.tsx", while App.tsx imported the keep side.
    """
    if not _fs_is_case_sensitive(tmp_path):
        pytest.skip("case-insensitive filesystem cannot host the fixture")
    from agents.dev import _module_is_still_imported

    code = tmp_path / "code"
    (code / "c" / "UI").mkdir(parents=True)
    (code / "c" / "ui").mkdir(parents=True)
    (code / "c" / "UI" / "Toast.tsx").write_text("export const T = 1\n", encoding="utf-8")
    (code / "c" / "ui" / "Toast.tsx").write_text("export const T = 2\n", encoding="utf-8")
    (code / "App.tsx").write_text("import { T } from './c/ui/Toast'\n", encoding="utf-8")

    # The keep side's importer must not pin the victim...
    assert _module_is_still_imported(code, code / "c" / "UI" / "Toast.tsx", ignore=set()) is None
    # ...while a real exact-case importer still refuses the deletion.
    assert (
        _module_is_still_imported(code, code / "c" / "ui" / "Toast.tsx", ignore=set())
        == "App.tsx"
    )


def test_a_bare_specifier_still_pins_the_module(tmp_path):
    """'./Toast' names no directory, so there is no way to tell which twin is meant — stay safe."""
    from agents.dev import _module_is_still_imported

    code = tmp_path / "code"
    (code / "c").mkdir(parents=True)
    (code / "c" / "Toast.tsx").write_text("export const T = 1\n", encoding="utf-8")
    (code / "c" / "App.tsx").write_text("import { T } from './Toast'\n", encoding="utf-8")
    assert (
        _module_is_still_imported(code, code / "c" / "Toast.tsx", ignore=set()) == "c/App.tsx"
    )


def test_an_empty_drop_side_is_not_a_finding(tmp_path):
    """The last twist of a very long fight, and the cheapest one to get wrong.

    UI/Toast.tsx was finally deleted after eleven informed rounds — frontend_build went green in
    the same verdict — and this detector kept module_health red on the empty UI/ directory, with
    `drop_files: []`. An instruction naming nothing can never be executed, so the remaining rounds
    would have run out against a directory no delete_files entry could address. TypeScript never
    sees an empty directory; housekeeping removes it.
    """
    if not _fs_is_case_sensitive(tmp_path):
        pytest.skip("case-insensitive filesystem cannot host the fixture")
    code = tmp_path / "code"
    (code / "c" / "UI").mkdir(parents=True)
    (code / "c" / "ui").mkdir(parents=True)
    (code / "c" / "ui" / "Toast.tsx").write_text("export const T = 1\n", encoding="utf-8")
    (code / "app.tsx").write_text("import { T } from './c/ui/Toast'\n", encoding="utf-8")
    assert find_case_collisions(code) == []


def test_the_round_prunes_the_directory_a_deletion_emptied(tmp_path):
    """Deleting the last file in a directory must not leave the directory behind."""
    from agents.dev import _prune_empty_dirs

    # Spelled Widgets/widgets-style rather than UI/ui so the case runs on every filesystem: the
    # behaviour under test is "the emptied directory goes", not the collision itself.
    code = tmp_path / "code"
    (code / "frontend" / "src" / "components" / "Emptied" / "nested").mkdir(parents=True)
    (code / "frontend" / "src" / "components" / "kept").mkdir(parents=True)
    (code / "frontend" / "src" / "components" / "kept" / "Toast.tsx").write_text("x\n", encoding="utf-8")
    removed = _prune_empty_dirs(
        code,
        log=lambda *a, **k: None,
        product_id="p",
        only_below=["frontend/src/components/Emptied/nested/Toast.tsx"],
    )
    assert "frontend/src/components/Emptied" in removed, removed
    assert "frontend/src/components/Emptied/nested" in removed, "a tree of empty dirs must all go"
    assert not (code / "frontend" / "src" / "components" / "Emptied").exists()
    assert (code / "frontend" / "src" / "components" / "kept" / "Toast.tsx").is_file()


def test_pruning_never_touches_dependencies_or_the_root(tmp_path):
    from agents.dev import _prune_empty_dirs

    code = tmp_path / "code"
    (code / "node_modules" / "pkg" / "empty").mkdir(parents=True)
    (code / "keep").mkdir(parents=True)
    (code / "keep" / "a.ts").write_text("x\n", encoding="utf-8")
    removed = _prune_empty_dirs(code, log=lambda *a, **k: None, product_id="p")
    assert not any(r.startswith("node_modules") for r in removed)
    assert code.is_dir() and (code / "keep" / "a.ts").is_file()


def test_the_prune_runs_after_every_rounds_writes():
    """Wired next to the deletions rather than only inside them: a rewrite can empty a directory
    too, by moving its last module elsewhere."""
    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "only_below=deleted_paths," in dev, "the prune must be scoped to this round's deletions"
    assert "_prune_empty_dirs(" in dev


def test_pruning_only_touches_the_directories_a_deletion_emptied(tmp_path):
    """A whole-tree sweep looked simpler and was wrong.

    Measured: it removed data/ and backend/data/ every round — directories the harness recreates,
    and on another product ones the app expects to exist. Housekeeping earns the right to remove a
    directory by having just emptied it.
    """
    from agents.dev import _prune_empty_dirs

    code = tmp_path / "code"
    (code / "backend" / "data").mkdir(parents=True)  # empty, but nobody deleted anything in it
    (code / "frontend" / "gone").mkdir(parents=True)
    removed = _prune_empty_dirs(
        code,
        log=lambda *a, **k: None,
        product_id="p",
        only_below=["frontend/gone/Toast.tsx"],
    )
    # frontend/ goes too — emptying its only child emptied it, and the walk continues upward
    # while each ancestor is empty. backend/data/ is untouched: nothing was deleted below it.
    assert removed == ["frontend/gone", "frontend"], removed
    assert (code / "backend" / "data").is_dir(), "an unrelated empty directory must survive"


def test_a_round_that_deleted_nothing_prunes_nothing(tmp_path):
    from agents.dev import _prune_empty_dirs

    code = tmp_path / "code"
    (code / "empty").mkdir(parents=True)
    assert _prune_empty_dirs(code, log=lambda *a, **k: None, product_id="p", only_below=[]) == []
    assert (code / "empty").is_dir()
