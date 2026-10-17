"""Python names: duplicate roles, imported symbols nothing defines, missing modules, undefined
names, orphan modules with broken imports.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import (
    _collect_imported_modules,
    _is_test_path,
    _module_level_bindings,
    _module_path,
    _normalised_matches,
    _PY_ASSIGN_RE,
    _PY_CLASS_RE,
    _PY_DEF_RE,
    from_imports,
    from_imports_with_aliases,
    MAX_FINDINGS,
    resolve_import_target,
)


# Roles a generated product tends to implement more than once.
_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("demo seeding", re.compile(r"^(seed|seeds|demo|demo_seed|demo_data|seed_demo|demo_seeder)$")),
    ("security helpers", re.compile(r"^(security|auth_utils|hashing|password)$")),
    ("api client", re.compile(r"^(api|client|apiClient|http)$")),
    # Bare `auth` is a FastAPI router or a Pydantic schema, not a React hook.
    # Matching it glued routers/auth.py + schemas/auth.py + frontend/src/api/auth.ts
    # into one "keep ONE, delete the rest" finding. Sentinel deleted the live
    # login router; main.py still `from .routers import auth`.
    ("auth hook", re.compile(r"^(useAuth|authContext|AuthContext)$")),
)


def _role_layer(rel: str) -> str:
    """Router / schema / frontend client are three layers of one feature, not copies."""
    posix = rel.replace("\\", "/")
    if posix.endswith((".ts", ".tsx", ".js", ".jsx")) or "/frontend/" in posix:
        return "frontend"
    if "/schemas/" in posix:
        return "schema"
    if "/models/" in posix:
        return "model"
    if "/routers/" in posix or "/endpoints/" in posix:
        return "router"
    return "backend"


def find_duplicate_roles(code_dir: Path) -> list[dict[str, Any]]:
    """Files whose names say they implement the same role."""
    by_role: dict[str, list[str]] = defaultdict(list)
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".py", ".ts", ".tsx", ".js", ".jsx"):
            continue
        stem = file.stem
        for role, pattern in _ROLE_PATTERNS:
            if pattern.match(stem):
                by_role[role].append(file.relative_to(code_dir).as_posix())
                break
        else:
            # Page.tsx vs PageX.tsx pairs: Accounts / AccountsPage.
            if stem.endswith("Page") and len(stem) > 4:
                by_role[f"{stem[:-4]} screen"].append(file.relative_to(code_dir).as_posix())
            elif file.suffix in (".tsx", ".jsx"):
                by_role[f"{stem} screen"].append(file.relative_to(code_dir).as_posix())

    findings: list[dict[str, Any]] = []
    for role, files in sorted(by_role.items()):
        by_layer: dict[str, list[str]] = defaultdict(list)
        for rel in files:
            by_layer[_role_layer(rel)].append(rel)
        for layer_files in by_layer.values():
            uniq = sorted(set(layer_files))
            if len(uniq) < 2:
                continue
            findings.append({"role": role, "files": uniq})
    return findings


def _rank_near_matches(name: str, candidates: Any, limit: int = 2) -> list[str]:
    """Closest existing names, ranked for snake_case identifiers.

    difflib alone ranks by character overlap and gets these backwards: asked for
    ``get_password_hash`` it offered ``verify_password`` ahead of ``hash_password``,
    which is plainly the same function. Comparing word sets first fixes that —
    {hash, password} sits inside {get, password, hash}; {verify, password} does not.
    """
    import difflib

    wanted = set(name.lower().split("_"))
    scored: list[tuple[float, str]] = []
    for candidate in sorted(candidates):
        if candidate == name:
            continue
        words = set(candidate.lower().split("_"))
        overlap = len(wanted & words) / max(1, len(wanted | words))
        ratio = difflib.SequenceMatcher(None, name, candidate).ratio()
        if overlap == 0 and ratio < 0.6:
            continue
        scored.append((overlap * 2 + ratio, candidate))
    scored.sort(reverse=True)
    return [c for _, c in scored[:limit]]


def find_missing_symbols(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Symbols imported from a first-party module that the module never defines.

    ``limit`` caps the report for human consumption; callers that act on every
    finding (the developer's regression rollback) must raise it, or a round that
    drops twenty symbols only gets ten of them protected.
    """
    defined: dict[str, set[str]] = {}
    files: dict[str, Path] = {}
    dynamic: set[str] = set()
    for file in iter_product_files(code_dir, "*.py"):
        module = _module_path(file, code_dir)
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A module that can synthesise attributes is unanalysable statically;
        # claiming a symbol is missing there would be a false accusation.
        if "__getattr__" in text or any(
            "*" in names for _m, names in from_imports(text)
        ):
            dynamic.add(module)
        names = set(_PY_DEF_RE.findall(text))
        names |= set(_PY_CLASS_RE.findall(text))
        names |= set(_PY_ASSIGN_RE.findall(text))
        # Conditional module-level bindings — `engine` assigned inside an if/else — are invisible
        # to a regex anchored at column zero, and a false missing_symbol costs a whole round.
        names |= _module_level_bindings(text)
        # Re-exports count as definitions. Parsed, so parenthesised multi-line
        # imports are included — the regex could not see them at all.
        for _mod, pairs in from_imports_with_aliases(text):
            for imported_name, alias in pairs:
                bound = alias or imported_name
                if bound and bound != "*":
                    names.add(bound)
        defined[module] = names
        files[module] = file
        # `from app.models import Advisory` names the package, but the table keys the file as
        # `app.models.__init__`, so package-level absolute imports missed the lookup as well.
        if module.endswith(".__init__"):
            package = module[: -len(".__init__")]
            defined.setdefault(package, names)
            files.setdefault(package, file)
            if module in dynamic:
                dynamic.add(package)

    wanted: dict[tuple[str, str], list[str]] = defaultdict(list)
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        importer = file.relative_to(code_dir).as_posix()
        importer_module = _module_path(file, code_dir)
        for written, names in from_imports(text):
            module = resolve_import_target(written, importer_module)
            if module not in defined or module in dynamic:
                continue
            for name in names:
                if not name or name == "*":
                    continue
                if name in defined[module]:
                    continue
                # `from . import advisory` and `from app import models` import a MODULE, not a
                # symbol of one. Reporting those as missing would be a false accusation, and a
                # false critical is worse than a miss: this gate votes on whether a round's work
                # is kept.
                if f"{module}.{name}" in defined or f"{module}.{name}.__init__" in defined:
                    continue
                wanted[(module, name)].append(importer)

    import difflib

    findings: list[dict[str, Any]] = []
    for (module, name), importers in sorted(wanted.items(), key=lambda kv: -len(kv[1])):
        # The writer and the caller often disagree about the name rather than the
        # behaviour: security.py defined seed_demo_operator while main.py imported
        # get_or_create_demo_operator. Told only "define it", the agent writes a
        # second function and breaks something else on the way past. Naming the
        # near-match turns that into one rename.
        near_matches = _normalised_matches(name, defined.get(module, ())) or _rank_near_matches(
            name, defined.get(module, ())
        )
        # When the only code wanting this name is a test, the test is the thing that is wrong. A test
        # importing a name the module never had was written against an imagined API, and changing
        # production code to satisfy it is the tail wagging the dog. Watched live: the sole importer of
        # `evaluate_advisory` was test_rule_engine.py, the module defines `compute_advisory`, and four
        # rounds went into editing the production module — where the anchor they chose appears three
        # times — instead of the one-line import in the test.
        only_tests = bool(importers) and all(_is_test_path(str(i)) for i in importers)
        findings.append(
            {
                "module": module,
                "symbol": name,
                "file": files[module].relative_to(code_dir).as_posix(),
                "importers": sorted(set(importers))[:8],
                "did_you_mean": near_matches,
                "only_tests_want_it": only_tests,
                "fix_hint": (
                    (
                        f"Only tests import '{name}': "
                        + ", ".join(sorted(set(importers))[:3])
                        + ". Fix the import in the test"
                        + (f" to '{near_matches[0]}'" if near_matches else "")
                        + " rather than adding the name to production code — a test asking for a name "
                        "the module never had was written against an API that does not exist."
                    )
                    if only_tests
                    else ""
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_missing_modules(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """First-party modules a file imports that do not exist anywhere in the product.

    ``find_missing_symbols`` stays silent when the target module is unknown, and that restraint is
    correct for ``fastapi`` — we do not own it and cannot judge it. But it swallowed a whole class
    of boot blocker with the same ``continue``: ``from ..schemas.auth import LoginRequest`` in a
    product whose ``schemas`` package holds only advisory.py, analytics.py and operator.py. The app
    dies at import with ``ModuleNotFoundError: No module named 'app.schemas.auth'`` and no static
    gate had an opinion, so the only report was a uvicorn traceback in the demo-journey log.

    A **relative** import cannot be third-party — the dots point inside the product by
    construction — and an absolute import whose first segment is one of the product's own top-level
    packages cannot be either. Those two rules are what make this checkable without guessing.

    A package whose directory has no ``__init__.py`` still counts as present when any module below
    it exists, which is what keeps namespace-style layouts from being accused.
    """
    defined: set[str] = set()
    roots: set[str] = set()
    for file in iter_product_files(code_dir, "*.py"):
        module = _module_path(file, code_dir)
        defined.add(module)
        if module.endswith(".__init__"):
            defined.add(module[: -len(".__init__")])
        head = module.split(".")[0]
        if head:
            roots.add(head)

    def present(module: str) -> bool:
        if module in defined:
            return True
        # A package is present if anything lives under it, __init__.py or not.
        prefix = module + "."
        return any(d.startswith(prefix) for d in defined)

    wanted: dict[str, list[str]] = defaultdict(list)
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        importer_module = _module_path(file, code_dir)
        importer = file.relative_to(code_dir).as_posix()
        for node in ast.walk(tree):
            written = ""
            if isinstance(node, ast.ImportFrom):
                written = ("." * (node.level or 0)) + (node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name or ""
                    if name.split(".")[0] in roots and not present(name):
                        wanted[name].append(importer)
                continue
            if not written:
                continue
            is_first_party = written.startswith(".") or written.split(".")[0] in roots
            if not is_first_party:
                continue
            target = resolve_import_target(written, importer_module)
            if target and not present(target):
                wanted[target].append(importer)

    import difflib

    findings: list[dict[str, Any]] = []
    for module, importers in sorted(wanted.items(), key=lambda kv: -len(kv[1])):
        near = difflib.get_close_matches(module, sorted(defined), n=2, cutoff=0.75)
        findings.append(
            {
                "module": module,
                "code": "missing_module",
                "severity": "critical",
                "file": sorted(set(importers))[0],
                "importers": sorted(set(importers))[:8],
                "did_you_mean": near,
                "detail": (
                    f"{module} does not exist anywhere in the product but is imported by "
                    + ", ".join(sorted(set(importers))[:4])
                    + ". Python raises ModuleNotFoundError at import time, so the app never "
                    "starts and every endpoint is unreachable. Create the module or point the "
                    "import at the one that has the code."
                    + (f" Did you mean {', '.join(near)}?" if near else "")
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def undefined_names_in_source(source: str) -> list[tuple[str, int]]:
    """Names a single module uses but never binds, as ``(name, line)`` pairs.

    Shared by the tree scan and the developer's revert check, so "did this file
    already have that problem?" is answered by the same analysis that reports it
    rather than by matching substrings — the old text containing the name is
    exactly what a *binding* looks like.
    """
    import ast
    import builtins

    known = set(dir(builtins)) | {
        "__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__",
        "__builtins__", "__debug__", "__annotations__", "__path__", "__all__",
    }
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return []
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            bound.add(node.name)

    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        if node.id in bound or node.id in known or node.id in seen:
            continue
        seen.add(node.id)
        out.append((node.id, node.lineno))
    return out


def find_undefined_names(code_dir: Path, limit: int = 12) -> list[dict[str, Any]]:
    """Names a module uses but never binds — the missing-import class.

    ``app/models/scoring.py`` imported ``Column, String, Integer, DateTime,
    ForeignKey, Text`` and then wrote ``Column(Boolean, default=True)``. One
    missing name, and it survived roughly fifteen repair rounds: the app failed
    to boot, the gate reported "NameError: name 'Boolean' is not defined", and
    the agent kept editing everything except line 1.

    Scoping is deliberately flattened — every binding anywhere in the module
    counts, so a name bound in one function and used in another is never
    reported. That under-reports, which is the right direction for a gate that
    blocks a build. Modules with star-imports are skipped entirely.
    """
    import ast
    import builtins

    known_builtins = set(dir(builtins)) | {
        "__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__",
        "__builtins__", "__debug__", "__annotations__", "__path__", "__all__",
    }

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            source = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue  # syntax errors are the compiler's report, not ours

        bound: set[str] = set()
        star_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                star_import = True
                break
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound.update(node.names)
            elif isinstance(node, ast.MatchAs) and node.name:
                bound.add(node.name)
            elif isinstance(node, ast.MatchStar) and node.name:
                bound.add(node.name)
        if star_import:
            continue

        seen: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                continue
            name = node.id
            if name in bound or name in known_builtins or name in seen:
                continue
            seen.add(name)
            findings.append(
                {
                    "file": file.relative_to(code_dir).as_posix(),
                    "name": name,
                    "line": node.lineno,
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


# Files that are entrypoints by convention: nothing imports them, and that is fine.
_NEVER_ORPHAN = (
    "__init__.py",
    "main.py",
    "app.py",
    "conftest.py",
    "env.py",
    "setup.py",
    "wsgi.py",
    "asgi.py",
)


def find_orphan_modules_with_broken_imports(
    code_dir: Path,
    missing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Abandoned files that nothing imports *and* that break the package.

    A repair round supersedes ``app/seed.py`` with ``app/services/seed.py`` but never
    deletes the first. The orphan keeps importing names that no longer exist, and
    because ``app/models/__init__.py`` aggregates the package, that dangling import
    breaks every import of the app. Naming the file to delete is far more actionable
    than another ImportError.
    """
    if not missing:
        return []

    imported_modules = _collect_imported_modules(code_dir)

    broken_importers: dict[str, list[str]] = defaultdict(list)
    for item in missing:
        for importer in item.get("importers") or []:
            broken_importers[importer].append(f"{item['symbol']} from {item['module']}")

    # What counts as "the module that superseded this one". Same stem alone is too
    # loose — `models/bi.py`, `schemas/bi.py` and `api/bi.py` are three layers of one
    # feature, not three copies. Require either a parallel location (same stem *and*
    # same parent directory name, e.g. endpoints/datasets.py vs v1/endpoints/datasets.py)
    # or membership in a duplicate-role group (seed.py vs services/seed.py).
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for file in iter_product_files(code_dir, "*.py"):
        by_key[(file.parent.name, file.stem)].append(file.relative_to(code_dir).as_posix())

    role_siblings: dict[str, list[str]] = {}
    for group in find_duplicate_roles(code_dir):
        for rel in group["files"]:
            role_siblings[rel] = [f for f in group["files"] if f != rel]

    orphans: list[dict[str, Any]] = []
    for importer, broken in sorted(broken_importers.items()):
        path = code_dir / importer
        if not path.is_file() or path.name in _NEVER_ORPHAN:
            continue
        # Tests are collected by the runner, never imported — "nothing imports it"
        # is normal for them, and telling the agent to delete a test is wrong.
        if _is_test_path(importer):
            continue
        if _module_path(path, code_dir) in imported_modules:
            continue
        # Require a twin. An unimported file with a broken import might simply be
        # new code being built toward; "delete it" is only safe advice when the
        # module it duplicates still exists and is the one actually wired up.
        twins = [p for p in by_key.get((path.parent.name, path.stem), []) if p != importer]
        twins += [p for p in role_siblings.get(importer, []) if p not in twins]
        twins = [p for p in twins if _role_layer(p) == _role_layer(importer)]
        if not twins:
            continue
        orphans.append(
            {"file": importer, "broken_imports": broken[:6], "superseded_by": twins[:3]}
        )
    return orphans
