"""Shared parsing helpers: Python import resolution, module-level bindings, near-match ranking,
test paths and a product's home module.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files


# Logged under the facade module's name, where these checks lived and where log filters point.
logger = logging.getLogger(__name__.rsplit(".", 2)[0] + ".duplicate_module_check")

_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.M)
_PY_ASSIGN_RE = re.compile(r"^(\w+)\s*[:=]", re.M)
_PY_CLASS_RE = re.compile(r"^\s*class\s+(\w+)", re.M)

MAX_FINDINGS = 10


def from_imports(source: str) -> list[tuple[str, list[str]]]:
    """Every ``from X import a, b`` in a module, as ``(module, [names])``.

    Parsed, not matched. The regex this replaces used ``[^\n(]+`` for the name list,
    so it stopped dead at a parenthesis and never crossed a newline — which made the
    single most common Python import style invisible:

        from app.schemas.operator import (
            DashboardResponse,   # never checked by anything
            SpendResponse,
        )

    A product shipped to production with `DashboardResponse` missing from that module
    while every gate reported one unrelated defect. Relative imports are returned with
    their leading dots so callers can ignore or resolve them as they choose.
    """
    import ast

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = ("." * (node.level or 0)) + (node.module or "")
        names = [(a.name, a.asname) for a in node.names]
        out.append((module, [n for n, _ in names]))
    return out


def from_imports_with_aliases(source: str) -> list[tuple[str, list[tuple[str, str | None]]]]:
    """As :func:`from_imports`, keeping ``as`` aliases — a re-export defines a name."""
    import ast

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = ("." * (node.level or 0)) + (node.module or "")
            out.append((module, [(a.name, a.asname) for a in node.names]))
    return out


def _collect_imported_modules(code_dir: Path) -> set[str]:
    """Dotted modules the tree actually loads, including ``from .routers import auth``.

    Orphan detection used to record only the package (``.routers`` / ``app.routers``)
    and never the imported submodule. ``from .routers import auth`` then looked like
    nothing referenced ``app.routers.auth``, so the gate ordered DELETE of the live
    FastAPI login router.
    """
    imported: set[str] = set()

    def _remember(module: str) -> None:
        if not module or module.startswith("."):
            return
        imported.add(module)
        parts = module.split(".")
        for i in range(1, len(parts)):
            imported.add(".".join(parts[:i]))

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        importer = _module_path(file, code_dir)
        for written, names in from_imports(text):
            module = resolve_import_target(written, importer)
            _remember(module)
            for name in names:
                if name and name != "*":
                    _remember(f"{module}.{name}" if module else name)
        for m in re.finditer(r"^\s*import\s+([\w.]+)", text, re.M):
            _remember(m.group(1))
    return imported


def _module_path(file: Path, code_dir: Path) -> str:
    rel = file.relative_to(code_dir)
    parts = list(rel.parts)
    # Strip the backend root so `backend/app/core/security.py` → `app.core.security`,
    # which is how the product's own imports name it.
    while parts and parts[0] in ("backend", "server", "api", "src"):
        parts = parts[1:]
    if not parts:
        return file.stem
    parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def resolve_import_target(module: str, importer_module: str) -> str:
    """Absolute dotted path for an import as written, seen from the importing module.

    ``from_imports`` reports an import the way the source spells it, dots included:
    ``.advisory``, ``..services.cache``. The table of what each module defines is keyed by
    absolute path (``app.models.advisory``), so every relative import missed the lookup and was
    skipped as "not first-party" — silently, by the same ``continue`` that correctly skips
    third-party packages.

    That blinded module health to the dominant import style in the code this factory writes. A
    tree that could not boot at all —

        backend/app/models/__init__.py:  from .advisory import Advisory, CachedMeshReading
        backend/app/routers/advisory.py: from ..services.cache import MeshCache

    with neither name defined anywhere in the product — returned **zero** findings, while the
    only gate that noticed was the demo journey, and only as a uvicorn boot log the round could
    not act on. Eighteen repair rounds never saw the two names that stopped the app from starting.
    """
    if not module.startswith("."):
        return module
    level = len(module) - len(module.lstrip("."))
    tail = module[level:]
    parts = importer_module.split(".")
    # A package's ``__init__`` is already at package level; a module sits one below it.
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    else:
        parts = parts[:-1]
    # One dot means "this package", so only the dots beyond the first walk upwards.
    for _ in range(level - 1):
        if not parts:
            break
        parts = parts[:-1]
    return ".".join([*parts, *([tail] if tail else [])])


def _normalised_matches(name: str, candidates: Any, limit: int = 2) -> list[str]:
    """Candidates that differ from ``name`` only in case or underscores.

    ``difflib`` is case-sensitive, so ``ATLAS_BASE_URL`` against ``atlas_base_url`` scores far below
    any usable cutoff — every character differs — and the detector reported the attribute with no
    suggestion at all. Watched live: a round wrote ``settings.ATLAS_BASE_URL`` for a field declared as
    ``atlas_base_url``, was rejected for it, and had nothing in the finding to tell it that the fix is
    one token. This is the single most common shape of the mistake and the cheapest to name.
    """
    def key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).lower())

    target = key(name)
    if not target:
        return []
    return [c for c in sorted(candidates or ()) if key(c) == target and c != name][:limit]


def _module_level_bindings(text: str) -> set[str]:
    """Names bound at module level, including inside a top-level ``if``/``try``/``for``/``with``.

    The regex this replaces required the name to start the line with no indentation, so a
    conditional module-level binding was invisible to it:

        if settings.database_url.startswith("sqlite"):
            engine = create_engine(...)     # indented, therefore "never defined"
        else:
            engine = create_engine(...)

    Measured live: `from app.db import Base, engine, SessionLocal` was reported as a missing symbol
    on a product whose own `SessionLocal = sessionmaker(bind=engine)` two lines below proves the
    binding exists. missing_symbol weighs 10 in the tree score, so a false one is enough to make a
    good round look like a regression and get it reverted. Conditional engines, clients and
    settings are an everyday pattern; accusing them is worse than missing a real defect.

    Bindings inside a function or class body are deliberately NOT collected — those are locals and
    attributes, not module exports. Falls back to the caller's regex when the file does not parse.
    """
    import ast as _ast

    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return set()

    names: set[str] = set()

    def collect(nodes) -> None:
        for node in nodes:
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                names.add(node.name)
                continue  # its body is local scope, not module scope
            if isinstance(node, _ast.Assign):
                for target in node.targets:
                    for sub in _ast.walk(target):
                        if isinstance(sub, _ast.Name):
                            names.add(sub.id)
            elif isinstance(node, (_ast.AnnAssign, _ast.AugAssign)):
                if isinstance(node.target, _ast.Name):
                    names.add(node.target.id)
            elif isinstance(node, (_ast.If, _ast.Try, _ast.For, _ast.AsyncFor, _ast.While)):
                collect(node.body)
                collect(getattr(node, "orelse", []) or [])
                collect(getattr(node, "finalbody", []) or [])
                for handler in getattr(node, "handlers", []) or []:
                    collect(handler.body)
            elif isinstance(node, (_ast.With, _ast.AsyncWith)):
                collect(node.body)

    collect(tree.body)
    return names


def _is_test_path(rel: str) -> bool:
    lowered = rel.lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_spec.py"))
        or "/tests/" in f"/{lowered}"
        or "/test/" in f"/{lowered}"
    )


# Two SQLAlchemy models declaring the same table is a boot-blocker that no import check sees:
# every module imports fine on its own, and the app dies only when both are registered against
# one MetaData —
#
#     sqlalchemy.exc.InvalidRequestError: Table 'invoke_audit_logs' is already defined for
#     this MetaData instance. Specify 'extend_existing=True' to redefine …
#
# Found on a product where a repair round rewrote ``models/advisory.py`` and inlined copies of
# models that already lived in ``models/audit.py``: three collisions at once
# (invoke_audit_logs, heartbeat_logs, allowance_states). The endpoint that had just been fixed
# then could not be reached at all, because nothing booted.
#
# ``extend_existing=True`` is a deliberate redefinition and is not reported.
def _canonical_home(table: str, decls: list[dict[str, Any]]) -> dict[str, Any]:
    """Which of the duplicate declarations to keep — decided here, once, and stated.

    "Keep ONE and delete the other" leaves the choice to the round, and a round makes it afresh
    every time. Watched live: ``allowance_state`` was declared in advisory.py and allowance.py, the
    round deleted one, and the next round — rewriting advisory.py to add an unrelated missing
    symbol — put it back, so the same critical defect appeared, cleared and reappeared across
    rounds without ever being resolved. Naming the survivor makes the instruction converge, and
    the rule has to be deterministic or it oscillates for a new reason.

    Preference order: the module whose filename matches the table (``allowance_state`` →
    ``allowance.py``), then alphabetically.

    "Fewest tables in the file" was in the middle of that list and had to come out. It reads well —
    a dedicated module is a better home than a grab-bag — but it is a function of things the round
    itself moves, so the instruction contradicted itself between rounds:

        17:46  keep backend/app/models/advisory.py, remove from audit.py
        18:09  keep backend/app/models/audit.py,    remove from advisory.py

    Nobody had touched ``allowance_state`` in between; other model classes had moved, the table
    counts crossed over (advisory 4, audit 3), and the verdict flipped. The round obeyed each
    instruction in turn and the duplicate survived five rounds with the baseline stuck at 10 —
    the exact oscillation naming a survivor was introduced to end, reintroduced by the tie-break.
    Alphabetical order cannot be moved by anything except renaming one of the two files.
    """
    stem_of = lambda d: Path(str(d["file"])).stem.lower()  # noqa: E731
    table_words = [w for w in re.split(r"[^a-z0-9]+", table.lower()) if w]

    def rank(d: dict[str, Any]) -> tuple[int, str]:
        stem = stem_of(d)
        singular = stem.rstrip("s")
        name_match = 0 if any(w.startswith(singular) or singular in w for w in table_words) else 1
        return (name_match, str(d["file"]))

    return sorted(decls, key=rank)[0]
