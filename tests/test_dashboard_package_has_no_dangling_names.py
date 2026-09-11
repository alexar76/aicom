"""No module in the split admin-dashboard package may use a name nothing defines.

`GET /api/admin/director/decisions` answered 500 on production for as long as it existed:
`routes_director.py` called `Path(DECISIONS_FILE)` while the constant had stayed behind in
`routes_metrics.py` when the package was split. Both the read and the write helper used it.

Nothing caught it because every module in the package does `from .models import *` and
`from .helpers import *`, and pyflakes stops reporting undefined names the moment a star
import appears — it cannot know what the star brought in. So this test resolves the star
imports itself and then checks the names.

Scope is deliberately narrow: module-level CONSTANT-style names (ALL_CAPS) read inside
functions. Those are exactly what a module split leaves dangling, and they are the ones a
type checker with star imports cannot see.
"""

from __future__ import annotations

import ast
import builtins
import importlib
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "admin" / "dashboard"
MODULES = sorted(p for p in PKG.glob("*.py") if p.name != "__init__.py")


def _defined_and_imported(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names this module binds itself, and the modules it star-imports."""
    bound: set[str] = set()
    star_from: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    bound.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                bound.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    star_from.add(node.module or "")
                else:
                    bound.add(a.asname or a.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
    return bound, star_from


def _star_names(module_name: str) -> set[str]:
    """Resolve `from X import *` the way Python would, so the check is not blind to it."""
    mod = importlib.import_module(f"web.backend.api.admin.dashboard.{module_name}")
    declared = getattr(mod, "__all__", None)
    if declared is not None:
        return set(declared)
    return {n for n in vars(mod) if not n.startswith("_")}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_all_caps_name_is_undefined(path: Path):
    tree = ast.parse(path.read_text())
    bound, star_from = _defined_and_imported(tree)
    for star in star_from:
        bound |= _star_names(star.lstrip("."))

    known = bound | set(dir(builtins))
    used_constants = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id.isupper()
        and len(node.id) > 2
    }
    dangling = sorted(used_constants - known)
    assert not dangling, (
        f"{path.name} reads {dangling} but nothing in the module, its imports or its star "
        "imports defines them — every call through that code path raises NameError and "
        "answers 500 (this is how /director/decisions was broken)"
    )
