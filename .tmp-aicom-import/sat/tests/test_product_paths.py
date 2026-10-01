"""One resolver, so a path named by any tool lands on a file that exists.

Findings arrive from tools that each have their own working directory. `tsc` prints
`src/api/advisory.ts` from inside `frontend/`; a traceback prints `app/services/cache.py` with the
`backend/` root stripped; a detector prints the repo-relative path. Everything downstream needs the one
form that resolves against the tree, and each consumer used to take whatever it was handed.

The cost, in a single round on a product that had one defect left:

    область ремонта: []                                   ← no such file, so no scope at all
    2 edit(s) did not apply: src/api/advisory.ts: no such file — use `files` to create it
                            src/components/Operator/Dashboard.tsx: no such file

No scope means nothing is attached; nothing attached means the round works from memory; the memory
reproduces the same unresolvable path. Three of the four failing gates sat behind that loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.product_paths import COMMON_ROOTS, resolve_all, resolve_product_path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    code = tmp_path / "code"
    for rel in (
        "frontend/src/api/advisory.ts",
        "frontend/src/components/Operator/Dashboard.tsx",
        "backend/app/services/cache.py",
        "backend/app/main.py",
        "node_modules/pkg/advisory.ts",
        ".aicom_sandbox/venv/lib/cache.py",
    ):
        path = code / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return code


def test_a_tsc_path_resolves(tree):
    assert resolve_product_path(tree, "src/api/advisory.ts") == "frontend/src/api/advisory.ts"


def test_a_traceback_path_resolves(tree):
    assert resolve_product_path(tree, "app/services/cache.py") == "backend/app/services/cache.py"


def test_a_line_column_suffix_is_stripped(tree):
    """Raw compiler text arrives as `src/a.ts(24,36)`."""
    assert resolve_product_path(tree, "src/api/advisory.ts(24,36)") == "frontend/src/api/advisory.ts"


def test_an_already_correct_path_is_returned_unchanged(tree):
    assert resolve_product_path(tree, "backend/app/main.py") == "backend/app/main.py"


def test_a_deep_suffix_resolves_without_a_known_root(tree):
    """Catches roots this list has never heard of."""
    assert (
        resolve_product_path(tree, "components/Operator/Dashboard.tsx")
        == "frontend/src/components/Operator/Dashboard.tsx"
    )


def test_installed_dependencies_are_not_candidates(tree):
    """node_modules also contains an advisory.ts; resolving to it would edit a dependency."""
    assert resolve_product_path(tree, "src/api/advisory.ts") == "frontend/src/api/advisory.ts"
    assert resolve_product_path(tree, "pkg/advisory.ts") is None


def test_the_sandbox_is_not_a_candidate(tree):
    assert resolve_product_path(tree, "lib/cache.py") is None


def test_an_ambiguous_name_is_refused_rather_than_guessed(tmp_path):
    """Two files ending the same way is an ambiguity, and picking one lands a fix in the wrong file."""
    code = tmp_path / "code"
    for rel in ("frontend/src/util.ts", "backend/src/util.ts"):
        path = code / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    assert resolve_product_path(code, "src/util.ts") is None


def test_nonsense_resolves_to_nothing(tree):
    for candidate in ("", "   ", "nope/missing.ts", "../../etc/passwd"):
        assert resolve_product_path(tree, candidate) is None


def test_resolve_all_separates_the_unresolvable(tree):
    resolved, unresolved = resolve_all(tree, ["src/api/advisory.ts", "nope/x.ts", "app/main.py"])
    assert resolved == ["frontend/src/api/advisory.ts", "backend/app/main.py"]
    assert unresolved == ["nope/x.ts"]


def test_the_common_roots_cover_the_layouts_the_factory_generates():
    for root in ("frontend", "backend", "app", "src", "server", "api"):
        assert root in COMMON_ROOTS


# --- the three consumers -------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def test_the_attachment_resolves_before_reading():
    src = (ROOT / "core" / "repair_batches.py").read_text(encoding="utf-8")
    assert "from core.product_paths import resolve_product_path" in src
    assert 'rel = resolve_product_path(root, str(raw)) or str(raw)' in src


def test_the_edit_applier_resolves_before_refusing():
    src = (ROOT / "agents" / "dev_edits.py").read_text(encoding="utf-8")
    region = src[src.index("no such file") - 900 : src.index("no such file") + 300]
    assert "resolve_product_path(code_root, rel)" in region
    assert "Edit path for" in src, "a silent path rewrite hides which file was actually edited"


def test_the_repair_scope_resolves_and_reports_what_it_cannot():
    src = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    region = src[src.index("if blocking_files:") : src.index("repair_scope = blocking_files[:6]")]
    assert "resolve_all(" in region
    assert "a pipeline defect, not the product's" in region, (
        "an unresolvable path must surface as our bug, not vanish into an empty scope"
    )


def test_an_attachment_still_happens_when_the_path_needed_fixing(tmp_path):
    """End to end: the shape that lost two edits now attaches."""
    from core.repair_batches import attach_file_contents

    code = tmp_path / "code"
    (code / "frontend" / "src" / "api").mkdir(parents=True)
    (code / "frontend" / "src" / "api" / "advisory.ts").write_text("export const x = 1\n", encoding="utf-8")
    got = attach_file_contents({"files": ["src/api/advisory.ts"]}, code)
    assert got == {"frontend/src/api/advisory.ts": "export const x = 1\n"}
