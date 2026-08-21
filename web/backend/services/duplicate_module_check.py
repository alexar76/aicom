"""
Detect the accretion pattern that keeps a repair loop from converging.

Watching a real rework: QA reported ``cannot import get_password_hash from
app.core.security``. The developer agent responded by writing a *new* seeding
module that also imported ``get_password_hash`` — without ever defining it. Next
round, another one. The tree ended up with five modules doing the same job

    app/seed.py                 imports hash_password
    app/services/seed.py        imports get_password_hash
    app/services/demo_data.py   imports get_password_hash
    app/services/demo_seed.py   imports get_password_hash
    app/services/demo.py        imports get_password_hash

and ``app/core/security.py`` defining neither. The same happened on the frontend
(``Accounts.tsx`` *and* ``AccountsPage.tsx``), where only one of each pair was
reachable from the router.

Patch mode never deletes, so every round the surface grows and the real defect
stays. This module names both halves of that failure:

  * ``duplicate_modules``  — several files serving one role
  * ``missing_symbol``     — a symbol imported across the codebase that nothing defines

The second is the one that actually breaks the build, and stating it as
"define X in Y" is far more actionable than an ImportError traceback.
"""

from __future__ import annotations

import ast
import builtins

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

logger = logging.getLogger(__name__)

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


_ROUTER_PREFIX_CTOR_RE = re.compile(
    r"(\w+)\s*=\s*APIRouter\s*\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']", re.S
)
_INCLUDE_WITH_PREFIX_RE = re.compile(
    r"include_router\s*\(\s*([\w.]+)[^)]*prefix\s*=\s*[\"']([^\"']+)[\"']", re.S
)
# The same call with the prefix passed as a name rather than a literal:
#   app.include_router(auth.router, prefix=settings.api_prefix)
# Live product, and it defeated both halves of this detector: the routers declared no prefix of
# their own, so the source shape never matched, and the route table could not resolve the value, so
# the effective paths looked clean. Meanwhile every route was really at /api/api/... — the demo
# journey POSTed /api/api/auth/login, advisory answered 500, and the whole frontend talked to paths
# that did not exist.
_INCLUDE_WITH_NAMED_PREFIX_RE = re.compile(
    r"include_router\s*\(\s*([\w.]+)[^)]*prefix\s*=\s*([A-Za-z_][\w.]*)", re.S
)
_ROUTE_PATH_RE = re.compile(
    r"@(\w+)\.(?:get|post|put|patch|delete|head|options)\s*\(\s*[\"']([^\"']+)[\"']"
)
_NAME_VALUE_RE = re.compile(r"^\s*(\w+)\s*(?::\s*str\s*)?=\s*[\"']([^\"']+)[\"']", re.M)


def _repeated_segment_run(path: str) -> str | None:
    """The doubled run in ``/api/auth/api/auth/login``, or ``None``.

    Compares whole segments, so ``/api/api-keys`` is not a repeat and ``/v1/users/v1/users`` is.
    """
    segs = [s for s in str(path or "").split("/") if s]
    for width in range(len(segs) // 2, 0, -1):
        for start in range(0, len(segs) - 2 * width + 1):
            first = segs[start : start + width]
            second = segs[start + width : start + 2 * width]
            if first and first == second:
                return "/" + "/".join(first)
    return None


def _router_include_prefixes(code_dir: Path) -> dict[str, str]:
    """``{module stem: prefix it is mounted under}`` for every include_router call.

    Needed by two detectors that read declared paths, and its absence made them contradict each
    other. `@router.get("/advisory")` in a module mounted with ``prefix=settings.api_prefix`` is
    served at ``/api/advisory`` — correct — but a detector reading only the decorator sees a route
    "outside /api" and demands it move, while the duplicated-prefix detector demands the opposite
    the moment it moves. Watched live: the round that correctly stripped /api from five routers
    immediately earned two shadow findings for doing so. Oscillation costs rounds and ends where it
    started.
    """
    values: dict[str, str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            blob = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, value in _NAME_VALUE_RE.findall(blob):
            if value.startswith("/"):
                values.setdefault(name, value)

    prefixes: dict[str, str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            blob = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for target, literal in _INCLUDE_WITH_PREFIX_RE.findall(blob):
            prefixes[target.split(".")[0]] = literal
        for target, name in _INCLUDE_WITH_NAMED_PREFIX_RE.findall(blob):
            resolved = values.get(name.split(".")[-1])
            if resolved:
                prefixes.setdefault(target.split(".")[0], resolved)
    return prefixes


def find_duplicated_router_prefix(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """A prefix applied twice, so every route in that router lives at a path nobody intends.

    Found on the live product in four of five routers::

        app/routers/auth.py:9   router = APIRouter(prefix="/api/auth", tags=["auth"])
        app/main.py:23          app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

    FastAPI adds both, so the real path is ``/api/auth/api/auth/login``. The consequences reached three
    separate gates and none of them named the cause:

    * the seeded demo login POSTed ``/api/auth/login``, which does not exist, and the catch-all route
      answered ``500`` — reported as a broken login handler for four rounds;
    * the same catch-all swallowed ``/``, so the browser crawl saw API JSON instead of the widget;
    * ``api_contract`` reported **agreement**, because the frontend had learned the doubled paths too —
      a gate returning the right answer to the wrong question, and the one component positioned to
      catch this first.

    Detected two ways, deliberately. The source shape says exactly which line to delete; the effective
    path catches the same fault arriving through nested routers, where no single line looks wrong.
    """
    try:
        from web.backend.services.api_contract_check import server_route_files
    except Exception:
        return []

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. The source shape: the same prefix declared on the router and on its inclusion.
    declared: dict[str, tuple[str, str]] = {}   # router var -> (prefix, file)
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for var, prefix in _ROUTER_PREFIX_CTOR_RE.findall(text):
            declared[f"{file.stem}.{var}"] = (prefix, rel)
            declared.setdefault(var, (prefix, rel))

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for target, include_prefix in _INCLUDE_WITH_PREFIX_RE.findall(text):
            key = ".".join(target.split(".")[-2:])
            hit = declared.get(key) or declared.get(target.split(".")[-1])
            if not hit:
                continue
            router_prefix, router_file = hit
            if router_prefix.rstrip("/") != include_prefix.rstrip("/"):
                continue
            if router_file in seen:
                continue
            seen.add(router_file)
            findings.append(
                {
                    "code": "duplicated_router_prefix",
                    "severity": "critical",
                    "file": router_file,
                    "prefix": router_prefix,
                    "included_in": rel,
                    "detail": (
                        f"{router_file} declares APIRouter(prefix=\"{router_prefix}\") and {rel} "
                        f"includes it with prefix=\"{include_prefix}\" as well. FastAPI applies both, so "
                        f"every route in this router is served at \"{router_prefix}{include_prefix}/…\" "
                        "and nothing reaches the path the app documents. "
                        f"REMOVE THE PREFIX FROM EXACTLY ONE PLACE so that the served paths become "
                        f"\"{router_prefix}/…\" — that is the path the specification, the frontend and "
                        "the demo journey all expect. Removing it from both leaves the routes at the "
                        "root, which silences this finding while breaking the API just as thoroughly: "
                        f"it already happened once on this product, and the login endpoint ended up at "
                        "\"/login\" instead of \"/api/auth/login\". Requests to the intended path fall "
                        "through to the catch-all route, which is why a correct login POST answers 500 "
                        "and why the root URL returns API JSON instead of the app."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings

    # 1b. The prefix arrives as a NAME, and the route paths already contain it. No single line looks
    # wrong here — the router has no prefix, the include has one, the decorators have full paths —
    # so only the combination is visible.
    named_values: dict[str, str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            blob = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, value in _NAME_VALUE_RE.findall(blob):
            if value.startswith("/"):
                named_values.setdefault(name, value)

    route_paths: dict[str, list[tuple[str, str]]] = {}   # module stem -> [(path, rel)]
    for file in iter_product_files(code_dir, "*.py"):
        try:
            blob = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for _var, path in _ROUTE_PATH_RE.findall(blob):
            route_paths.setdefault(file.stem, []).append((path, rel))

    for file in iter_product_files(code_dir, "*.py"):
        try:
            blob = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for target, prefix_name in _INCLUDE_WITH_NAMED_PREFIX_RE.findall(blob):
            attr = prefix_name.split(".")[-1]
            prefix = named_values.get(attr)
            if not prefix or prefix == "/":
                continue
            module = target.split(".")[0]
            for path, handler_rel in route_paths.get(module, []):
                if not path.startswith(prefix.rstrip("/") + "/"):
                    continue
                if handler_rel in seen:
                    continue
                seen.add(handler_rel)
                findings.append(
                    {
                        "code": "duplicated_router_prefix",
                        "severity": "critical",
                        "file": handler_rel,
                        "prefix": prefix,
                        "included_in": rel,
                        "detail": (
                            f"{rel} includes this router with prefix={prefix_name} (= \"{prefix}\") "
                            f"and the route in {handler_rel} is already declared as \"{path}\", so "
                            f"FastAPI serves it at \"{prefix.rstrip('/')}{path}\". Nothing reaches "
                            f"\"{path}\": the demo journey, the frontend and the specification all "
                            "use that path and get the catch-all instead. Fix it in ONE place — "
                            f"either drop the prefix from the include_router call in {rel}, or strip "
                            f"\"{prefix.rstrip('/')}\" from the decorators in {handler_rel} — never "
                            "both, because removing it twice moves every route to the root and "
                            "breaks the API just as thoroughly."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
                break

    # 2. The effective paths: catches the same fault through nested routers, where no line looks wrong.
    for path, handler_file in server_route_files(code_dir).items():
        run = _repeated_segment_run(path)
        if not run or handler_file in seen:
            continue
        seen.add(handler_file)
        findings.append(
            {
                "code": "duplicated_router_prefix",
                "severity": "critical",
                "file": handler_file,
                "prefix": run,
                "included_in": "",
                "detail": (
                    f"The served path \"{path}\" repeats \"{run}\", so this route is mounted under its "
                    "own prefix twice and nothing reaches the path the app documents. Apply the prefix "
                    "in ONE place only — where the router is constructed or where it is included, never "
                    f"both — so the served path becomes \"{path.replace(run + run, run, 1)}\". Do not "
                    "remove it from both places: that silences this finding and moves every route to "
                    "the root, which breaks the API just as thoroughly."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


_ROUTE_DECOR_WITH_METHOD_RE = re.compile(
    r"@(\w+)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']"
)
_SPA_EXEMPT = frozenset({"/", "/healthz", "/health", "/api", "/metrics/prometheus"})


_SCOPE_PATH_REWRITE_RE = re.compile(
    r"scope\[\s*[\"']path[\"']\s*\]\s*=\s*[\"']([^\"']+)[\"']"
)


def find_dead_path_rewrites(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """ASGI middleware that rewrites a request path to one no route serves.

    Found live as the saboteur behind a 405 that survived every other fix::

        class PathRewriteMiddleware:
            ...
            if path == "/api/auth/login":
                scope["path"] = "/login"        # ← /login no longer exists

    A compatibility shim from the era when login lived at ``/login``. The routes moved under
    ``/api/auth``; the shim stayed, and now it rewrites the CORRECT path onto a dead one, where the
    SPA catch-all (GET-only) answers 405 to the login POST. Every observable symptom pointed at the
    auth router — the journey's file attribution, the OpenAPI schema, the static route table all said
    the endpoint exists, because it does; requests just never reach it. Rounds edited ``auth.py``
    repeatedly and could not have fixed anything there.

    Two flavours, both critical: a rewrite whose TARGET no route serves (requests die), and a rewrite
    whose SOURCE is itself a served route (a live endpoint is being shadowed on purpose or by
    leftover). Rewrites between two live paths are left alone — that is a legitimate alias.
    """
    try:
        from web.backend.services.api_contract_check import extract_server_routes
    except Exception:
        return []
    served = set(extract_server_routes(code_dir))
    if not served:
        return []

    def _served(path: str) -> bool:
        clean = path.rstrip("/") or "/"
        if clean in served:
            return True
        return any(s.split("{")[0].rstrip("/") == clean for s in served if "{" in s)

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for m in _SCOPE_PATH_REWRITE_RE.finditer(text):
            target = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            window = text[max(0, m.start() - 300) : m.start()]
            src_m = re.findall(r"==\s*[\"']([^\"']+)[\"']", window)
            source = src_m[-1] if src_m else ""
            target_ok = _served(target)
            source_live = bool(source) and _served(source)
            if target_ok and not source_live:
                continue  # alias onto a live route from a dead path: legitimate
            reason = []
            if not target_ok:
                reason.append(
                    f"the target \"{target}\" is served by NO route, so every rewritten request "
                    "falls through to the SPA catch-all — GET-only — and methods like POST answer 405"
                )
            if source_live:
                reason.append(
                    f"the source \"{source}\" IS a live route, so this rewrite shadows a working "
                    "endpoint that every schema and table says exists"
                )
            findings.append(
                {
                    "code": "dead_path_rewrite",
                    "severity": "critical",
                    "file": rel,
                    "line": line,
                    "source": source,
                    "target": target,
                    "detail": (
                        f"{rel}:{line} rewrites the request path "
                        + (f"\"{source}\" " if source else "")
                        + f"to \"{target}\" in ASGI middleware, and "
                        + "; ".join(reason)
                        + ". DELETE the rewrite (usually the whole leftover middleware): the real "
                        "route already exists at the original path. Do not edit the router — it is "
                        "correct, and it has been edited in vain for exactly this reason."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


def find_case_collisions(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Two entries in one directory whose names differ only in case.

    Found live as ``components/UI/`` next to ``components/ui/``. TypeScript refuses the tree with
    ``TS1149: File name … differs from already included file name only in casing``, so the build
    produces nothing — and the error prints absolute paths that no downstream consumer could resolve,
    which is how it survived a full informed round. On a case-insensitive filesystem (macOS, the
    default dev laptop) one of the two silently wins and the product breaks only in CI or on deploy,
    which is strictly worse than breaking here.

    The finding counts import references to each spelling and says to keep the more-referenced one,
    because "merge these" without a direction is the kind of instruction this pipeline has already
    watched oscillate.
    """
    from collections import defaultdict as _dd

    groups: dict[tuple[str, str], set[str]] = _dd(set)
    for path in code_dir.rglob("*"):
        rel = path.relative_to(code_dir)
        if any(part in ("node_modules", ".git", ".aicom_sandbox", "dist", "build", ".next", "__pycache__", ".venv", "preview-venv") for part in rel.parts):
            continue
        groups[(rel.parent.as_posix(), rel.name.lower())].add(rel.name)

    findings: list[dict[str, Any]] = []
    for (parent, _low), names in sorted(groups.items()):
        if len(names) < 2:
            continue
        spellings = sorted(names)
        refs: dict[str, int] = {}
        for name in spellings:
            stem = name.rsplit(".", 1)[0]
            count = 0
            for file in iter_product_files(code_dir, "*"):
                if file.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".py"):
                    continue
                try:
                    count += file.read_text(encoding="utf-8", errors="replace").count(f"/{stem}")
                except OSError:
                    continue
            refs[name] = count
        keep = max(spellings, key=lambda n: refs.get(n, 0))
        drop = [n for n in spellings if n != keep]
        # Enumerate REAL FILES, not directories. The first version pointed `file` at the directory to
        # keep — and the pipeline's own path resolver rejects directories, so the finding fell out of
        # the repair scope, nothing was attached, and two informed rounds went to deps.py instead of
        # the collision. delete_files also needs exact file paths; "delete UI/" is not an instruction
        # it can execute.
        drop_files: list[str] = []
        for name in drop:
            candidate = code_dir / parent / name
            if candidate.is_dir():
                drop_files.extend(
                    sorted(
                        f.relative_to(code_dir).as_posix()
                        for f in candidate.rglob("*")
                        if f.is_file()
                    )[:12]
                )
            else:
                drop_files.append(f"{parent}/{name}".lstrip("/"))
        # A drop side holding no files at all is not a build failure and not an executable
        # finding. Measured: UI/Toast.tsx was finally deleted after eleven rounds, frontend_build
        # went green in the same verdict — and this detector kept module_health red on the empty
        # UI/ directory with `drop_files: []`, an instruction naming nothing. TypeScript never sees
        # an empty directory; the round-level prune removes it as housekeeping.
        if not drop_files:
            continue

        # `file` names the FIRST FILE TO DELETE, not the keep side. The repair scope is built from
        # this field, and pointing it at the keep side sent every round to an innocent file: scoped
        # to ui/FeedbackStates.tsx, a round would delete UI/Toast.tsx — the actual instruction —
        # and the out-of-scope revert would restore it, round after round. The keep side needs no
        # edits at all when the dropped spelling has zero references; the drop side always does.
        file_field = (
            drop_files[0]
            if drop_files
            else f"{parent}/{keep}".lstrip("/")
        )
        findings.append(
            {
                "code": "case_collision",
                "severity": "critical",
                "file": file_field,
                "parent": parent,
                "spellings": spellings,
                "keep": keep,
                "drop_files": drop_files,
                "detail": (
                    f"{parent or '.'} contains {' and '.join(spellings)} — the same name in different "
                    "casing. TypeScript refuses the tree with TS1149 and the build produces nothing; "
                    "on a case-insensitive filesystem one of the two silently wins. KEEP "
                    f"\"{keep}\" (referenced {refs.get(keep, 0)} time(s), more than "
                    + ", ".join(f"{d}: {refs.get(d, 0)}" for d in drop)
                    + "). Put these EXACT paths in delete_files after moving anything unique into "
                    f"\"{keep}\": "
                    + (", ".join(drop_files) if drop_files else ", ".join(drop))
                    + ". Then update any import that references the deleted spelling."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_api_routes_shadowing_spa(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """API routes mounted outside ``/api`` in a product that serves a SPA catch-all.

    The recurring bug of this product's whole night, in three costumes. A JSON route whose path is not
    under ``/api`` sits in FastAPI's route table ahead of the SPA catch-all, so a browser *navigating*
    to that path never reaches the app shell:

    * ``GET /login``  → the login page rendered as raw JSON;
    * ``GET /``       → API JSON where the widget belongs (before the catch-all landed);
    * ``GET /dashboards`` → **405**, because the bare route serves only POST — the path matches, the
      method does not, and FastAPI answers 405 instead of falling through to ``index.html``.

    The 405 costumes were the ones that misdirected rounds hardest: the browser console said
    "Failed to load resource: 405" with no path, and two rounds went guessing in ``App.tsx``.

    Flagged only when the product actually serves a SPA catch-all (``{full_path:path}`` or
    equivalent) — an API-only product may mount wherever it likes. When the same resource tail
    already exists under ``/api``, the finding says to DELETE the bare twin rather than move it,
    because the moved copy would collide with the one that already works.
    """
    # (file, prefix) per router var, then every decorated route with its method.
    routers: dict[tuple[str, str], str] = {}   # (module stem, var) -> prefix
    routes: list[tuple[str, str, str, str]] = []  # (full_path, METHOD, file, var)
    include_prefixes = _router_include_prefixes(code_dir)
    has_catchall = False
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = file.relative_to(code_dir).as_posix()
        for var, args in _ROUTER_PREFIX_CTOR_RE.findall(text):
            routers[(file.stem, var)] = args
        for var, method, path in _ROUTE_DECOR_WITH_METHOD_RE.findall(text):
            if "full_path" in path or ":path" in path:
                has_catchall = True
                continue
            # The mount prefix can come from EITHER the router constructor or the include_router
            # call — and missing the second made this detector fight the duplicated-prefix one:
            # `@router.get("/advisory")` in a module mounted with prefix=settings.api_prefix is
            # served at /api/advisory, but read on its own it looks like a route outside /api. The
            # round that correctly stripped /api from five routers earned two shadow findings for
            # doing so, and the next round would have put them back.
            prefix = routers.get((file.stem, var), "") or include_prefixes.get(file.stem, "")
            full = (prefix + path).rstrip("/") or "/"
            routes.append((full, method.upper(), rel, var))

    if not has_catchall:
        return []

    under_api: set[str] = set()
    for full, method, _rel, _var in routes:
        if full == "/api" or full.startswith("/api/"):
            # Tail without the mount, for twin detection: /api/analytics/dashboards -> dashboards…
            under_api.add(full)

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for full, method, rel, _var in routes:
        if full in _SPA_EXEMPT or full == "/api" or full.startswith("/api/"):
            continue
        key = (full, rel)
        if key in seen:
            continue
        seen.add(key)
        tail = full.lstrip("/")
        twins = [p for p in under_api if p.endswith("/" + tail.split("/")[0])] or [
            p for p in under_api if p.split("/")[-1] == tail.split("/")[0]
        ]
        findings.append(
            {
                "code": "api_route_shadows_spa",
                "severity": "critical",
                "file": rel,
                "path": full,
                "method": method,
                "detail": (
                    f"{rel} serves {method} \"{full}\" outside /api in a product with a SPA "
                    "catch-all. The route table matches this path before the catch-all, so a browser "
                    f"NAVIGATING to \"{full}\" gets "
                    + ("405 Method Not Allowed" if method != "GET" else "raw API JSON")
                    + " instead of the app shell — this is the mechanism behind the console's "
                    "unexplained 405s and behind pages rendering as JSON. "
                    + (
                        f"The same resource already lives under {twins[0]} — DELETE this bare twin "
                        "and point any caller at the /api route. "
                        if twins
                        else f"MOVE it under /api (e.g. \"/api{full}\") and update the frontend "
                        "callers in the same round — api_contract will hold the two sides together. "
                    )
                    + "Do not touch the catch-all; it is correct."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_mismatched_back_populates(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """A ``relationship(back_populates=…)`` whose other side does not exist.

    The SQLAlchemy twin of ``missing_attribute``, found the same way its siblings were — a live
    product dead at boot with every static counter at zero::

        sqlalchemy.exc.InvalidRequestError: Mapper 'Mapper[Advisory(advisories)]' has no property
        'invoke_logs'. If this property was indicated from other mappers …

    ``InvokeAuditLog`` pointed back at ``Advisory.invoke_logs`` while ``Advisory`` calls that field
    ``audit_logs``. The mapper configures lazily, so the first query kills the app; nothing importable
    is wrong, so every import-level detector stayed silent and the rounds went back to guessing —
    measured: two rounds editing ``deps.py`` while both halves of the defect sat in the models.

    Precision rules, since this reports critical: only classes this product defines, targets resolved
    by class name, and a target that cannot be found is missing_symbol territory rather than a
    mismatch. The finding names both files and both attribute names, because the fix is a one-token
    rename on whichever side is wrong.
    """
    # class name -> {"file": rel, "line": int, "rels": {attr: (target, back_populates)}}
    classes: dict[str, dict[str, Any]] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        rel_path = file.relative_to(code_dir).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs: dict[str, Any] = {}
            rels: dict[str, tuple[str, str | None, int]] = {}
            for stmt in node.body:
                targets = []
                value = None
                if isinstance(stmt, ast.Assign):
                    targets = [x.id for x in stmt.targets if isinstance(x, ast.Name)]
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    targets = [stmt.target.id]
                    value = stmt.value
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    attrs[stmt.name] = True
                    continue
                for name in targets:
                    attrs[name] = True
                if not targets or not isinstance(value, ast.Call):
                    continue
                func = value.func
                func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if func_name != "relationship":
                    continue
                target_cls = ""
                if value.args:
                    a0 = value.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        target_cls = a0.value
                    elif isinstance(a0, ast.Name):
                        target_cls = a0.id
                back = None
                for kw in value.keywords:
                    if kw.arg == "back_populates" and isinstance(kw.value, ast.Constant):
                        back = kw.value.value
                if target_cls:
                    rels[targets[0]] = (target_cls, back, stmt.lineno)
            if attrs or rels:
                classes[node.name] = {
                    "file": rel_path,
                    "line": node.lineno,
                    "attrs": attrs,
                    "rels": rels,
                }

    import difflib

    findings: list[dict[str, Any]] = []
    for cls_name, info in sorted(classes.items()):
        for attr, (target_cls, back, lineno) in sorted(info["rels"].items()):
            if not back:
                continue
            target = classes.get(target_cls)
            if target is None:
                continue  # unknown class: missing_symbol territory, not a mismatch
            if back in target["attrs"] or back in target["rels"]:
                continue
            # The reciprocal attr the target actually has, if any: a relationship pointing back here.
            candidates = [
                a for a, (tc, _b, _l) in target["rels"].items() if tc == cls_name
            ] or difflib.get_close_matches(back, sorted(target["attrs"]), n=2, cutoff=0.6)
            findings.append(
                {
                    "code": "mismatched_back_populates",
                    "severity": "critical",
                    "file": info["file"],
                    "line": lineno,
                    "class": cls_name,
                    "attr": attr,
                    "target": target_cls,
                    "expected": back,
                    "did_you_mean": candidates[:2],
                    "detail": (
                        f"{info['file']}:{lineno}: {cls_name}.{attr} = relationship("
                        f"\"{target_cls}\", back_populates=\"{back}\") — but {target_cls} in "
                        f"{target['file']} has no attribute '{back}'. SQLAlchemy raises "
                        f"InvalidRequestError (\"Mapper has no property '{back}'\") when the mapper "
                        "first configures, so the app dies on its first query. "
                        + (
                            f"{target_cls} calls its side {' / '.join(repr(c) for c in candidates[:2])} — "
                            f"make the pair agree with a ONE-TOKEN rename on whichever side is wrong. "
                            if candidates
                            else f"Add the matching relationship to {target_cls} or fix the name. "
                        )
                        + "Do not delete the relationship: whatever queries it breaks next."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


def find_class_body_forward_refs(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Class-body statements that read a name the body has not bound yet.

    Python executes a class body top to bottom, so this raises ``NameError`` the moment the module is
    imported::

        class AtlasClient:
            invoke = invoke_capability          # <- line 8: nothing has bound this yet
            async def invoke(self, capability, payload):
                return await self.invoke_capability(capability, payload)

    The round wrote both halves of a fix and left the failed first half in place. The second is correct;
    the first stops the app from importing at all.

    Nothing saw it. ``undefined_names_in_source`` returned ``[]`` and the tree scored **0**, because a
    scope-wide name collector finds ``invoke_capability`` in the class namespace and never asks whether
    it was bound *before* the line that reads it. That blindness deadlocked the product: with the score
    at zero, any fix to the file measured as no improvement while any incidental change measured as
    risk, so the round guard gave the fix back every single time — three rounds running, on the one
    defect standing between the product and booting.

    Only class-body execution counts. A name read inside a method resolves when the method is called,
    which is a different question and not this one; a decorator or a default argument, however, is
    evaluated with the body and does count.
    """
    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue

        # MODULE scope only. Walking the whole tree pulled method names into it, so
        # `invoke = invoke_capability` inside a class looked bound by the very method defined below it
        # — which is exactly the case this detector exists for, and it went silent on it.
        module_bound: set[str] = set(dir(builtins))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    module_bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_bound.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.With, ast.Try)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        module_bound.add(sub.id)
                    elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        module_bound.add(sub.name)
            elif isinstance(node, (ast.If, ast.While)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        module_bound.add(sub.id)

        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            bound: set[str] = set(module_bound)
            # A generic class parameter or an enclosing name is fine; only ordering is in question.
            for stmt in cls.body:
                # Read the statement first, then record what it binds — that ordering IS the check.
                # Names a lambda parameter or a comprehension target binds are local to it. Without
                # this, `Column(default=lambda x: ...)` in a model body read as five critical findings
                # about a name called `x`.
                local: set[str] = set()
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Lambda):
                        args = sub.args
                        for arg in (
                            list(args.posonlyargs or [])
                            + list(args.args or [])
                            + list(args.kwonlyargs or [])
                            + [a for a in (args.vararg, args.kwarg) if a is not None]
                        ):
                            local.add(arg.arg)
                    elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        for gen in sub.generators:
                            for name in ast.walk(gen.target):
                                if isinstance(name, ast.Name):
                                    local.add(name.id)
                    elif isinstance(sub, ast.ExceptHandler) and sub.name:
                        local.add(sub.name)

                reads: list[ast.Name] = []
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not stmt:
                        continue
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        if sub.id not in local:
                            reads.append(sub)
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Its body runs later; only decorators and defaults run now.
                    reads = [
                        n
                        for dec in stmt.decorator_list
                        for n in ast.walk(dec)
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    ] + [
                        n
                        for default in (stmt.args.defaults or []) + [
                            d for d in (stmt.args.kw_defaults or []) if d is not None
                        ]
                        for n in ast.walk(default)
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    ]
                for name in reads:
                    if name.id in bound:
                        continue
                    findings.append(
                        {
                            "code": "class_body_forward_ref",
                            "severity": "critical",
                            "file": file.relative_to(code_dir).as_posix(),
                            "line": name.lineno,
                            "class": cls.name,
                            "name": name.id,
                            "detail": (
                                f"{file.relative_to(code_dir).as_posix()}:{name.lineno} reads "
                                f"'{name.id}' in the body of class {cls.name} before anything binds it. "
                                "A class body executes top to bottom at import, so Python raises "
                                f"NameError: name '{name.id}' is not defined and the app never starts. "
                                "If this line was meant to alias a method defined lower down, delete it "
                                "— a method defined later cannot be referenced here; the wrapper method "
                                "below already does the job."
                            ),
                        }
                    )
                    if len(findings) >= limit:
                        return findings
                # Now record the bindings this statement makes.
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    bound.add(stmt.name)
                else:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            bound.add(sub.id)
                        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                            bound.add(sub.target.id)
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


# Names pydantic/BaseModel and ordinary objects carry without declaring them in a class body.
# Reading one of these is never the defect this detector is looking for.
# Third-party bases whose attributes are still declared in the subclass body, so a subclass of one
# remains analysable. Pydantic is the whole reason this list exists: its fields ARE the class body,
# and treating `BaseSettings` as an opaque base made the detector silent on exactly the case it was
# written for — `class Settings(BaseSettings)` with 19 declared fields and `settings.cors_origins`
# read in main.py. Anything not listed here makes its subclass unanalysable, because an unknown base
# may well provide the attribute and a false critical costs more than a miss.
_ANALYSABLE_FOREIGN_BASES = frozenset({"BaseSettings", "BaseModel", "object"})

_INHERITED_ATTRS = frozenset(
    {
        "model_config", "model_fields", "model_fields_set", "model_computed_fields",
        "model_dump", "model_dump_json", "model_copy", "model_validate",
        "model_validate_json", "model_json_schema", "model_extra", "model_post_init",
        "dict", "json", "copy", "schema", "schema_json", "parse_obj", "parse_raw",
        "construct", "validate", "fields", "Config", "metadata", "registry", "query",
    }
)


def find_missing_instance_attributes(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Attributes read off a module-level singleton that its class never declares.

    The shape is ubiquitous in generated FastAPI code and fatal at import time::

        app/config.py:  class Settings(BaseSettings):  # 21 fields, none of them cors_origins
                        settings = Settings()
        app/main.py:19: allow_origins=settings.cors_origins

    ``AttributeError: 'Settings' object has no attribute 'cors_origins'`` before the first route is
    registered, so the app never starts and every endpoint is unreachable. Nothing static had an
    opinion: the module imports cleanly, every name resolves, the class exists. It surfaced only as
    a uvicorn traceback in the demo-journey log — the same blind spot as missing symbols and missing
    modules, one level further in, at the instance rather than the module.

    Kept narrow on purpose, because this reports ``critical`` and criticals decide whether a round's
    work is kept:

    * only module-level ``name = ClassName()`` singletons whose class is defined in this product;
    * classes that synthesise attributes (``__getattr__``) or accept extras (pydantic
      ``extra = "allow"``) are skipped — there the read may well succeed;
    * attributes assigned onto the singleton anywhere in the tree count as declared;
    * dunders and the inherited pydantic/ORM API are never reported.
    """
    # Keyed by the module that creates it, not by name alone: two modules can each bind `settings`
    # to different objects, and conflating them accused `settings.anything` on an `object()` in an
    # unrelated file. A false critical costs more than a miss on a gate that discards work.
    singletons: dict[tuple[str, str], str] = {}   # (module, binding name) -> class name
    classes: dict[str, dict[str, Any]] = {}  # class name -> {names, bases, dynamic, file}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        module_here = _module_path(file, code_dir)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names: set[str] = set()
                dynamic = False
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        names.add(stmt.target.id)
                    elif isinstance(stmt, ast.Assign):
                        names.update(x.id for x in stmt.targets if isinstance(x, ast.Name))
                    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(stmt.name)
                        if stmt.name in ("__getattr__", "__getattribute__"):
                            dynamic = True
                    elif isinstance(stmt, ast.ClassDef):
                        names.add(stmt.name)
                        # `class Config: extra = "allow"` lets undeclared fields through.
                        for inner in stmt.body:
                            if isinstance(inner, ast.Assign) and isinstance(
                                inner.value, ast.Constant
                            ):
                                if inner.value.value == "allow":
                                    dynamic = True
                    if isinstance(stmt, ast.Assign):
                        for sub in ast.walk(stmt):
                            if isinstance(sub, ast.keyword) and sub.arg == "extra":
                                if isinstance(sub.value, ast.Constant) and sub.value.value == "allow":
                                    dynamic = True
                classes[node.name] = {
                    "names": names,
                    # Which members are coroutines: calling one without await yields
                    # "TypeError: 'coroutine' object is not subscriptable", a shape that cost this
                    # product several rounds while the finding said nothing about it.
                    "async_names": {
                        stmt.name
                        for stmt in node.body
                        if isinstance(stmt, ast.AsyncFunctionDef)
                    },
                    "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
                    "dynamic": dynamic,
                    "file": rel,
                    "line": node.lineno,
                }
        # Module-level singletons AND locals built from a product class. The local case was missed
        # and it cost a boot: `heartbeat = HeartbeatService(db)` inside a lifespan function, followed
        # by `heartbeat.scheduler.shutdown()` on a class that has start(), stop(), _thread and
        # _stop_event — and no scheduler. AttributeError inside lifespan takes the whole app down,
        # exactly like the module-level case this detector was written for; the only difference is
        # the indentation of the line that builds the object.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                call = node.value
                if (
                    isinstance(target, ast.Name)
                    and isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                ):
                    key = (module_here, target.id)
                    prior = singletons.get(key)
                    if prior is not None and prior != call.func.id:
                        # The same name bound to two different classes in one module: two locals in
                        # separate functions, most likely. Which class a read belongs to is no longer
                        # knowable from this analysis, and a wrong critical costs a round's work.
                        singletons[key] = ""
                    elif prior != "":
                        singletons[key] = call.func.id

    def _offer(class_name: str, wanted: str) -> str:
        """"It does not declare X" is a diagnosis; "it declares these three" is an instruction.

        Without this the rounds oscillated: `atlas.get_advisory(...)` does not exist, so one round
        added a method, the next deleted the call, a third put the placeholder back — while
        AtlasClient had get_situation_brief, get_fire_weather and get_nearest_read sitting right
        there, every one of them async. Naming them, nearest spelling first, turns three rounds of
        guessing into one edit.
        """
        import difflib

        info = classes.get(class_name) or {}
        names = {
            n for n in (info.get("names") or set())
            if isinstance(n, str) and not n.startswith("_")
        }
        if not names:
            return ""
        close = difflib.get_close_matches(wanted, sorted(names), n=3, cutoff=0.4)
        listed = close or sorted(names)[:6]
        asyncs = info.get("async_names") or set()
        note = ""
        if any(n in asyncs for n in listed):
            note = (
                " (async — call with await; calling one without await gives "
                "\"TypeError: 'coroutine' object is not subscriptable\" instead)"
            )
        return (
            f"{class_name} DOES declare: {', '.join(listed)}{note}. "
            f"If one of those is the method you meant, call it instead. "
        )

    def declared(class_name: str, seen: set[str] | None = None) -> set[str] | None:
        if not class_name:
            return None
        """Every name the class and its product-defined bases declare, or None if unanalysable."""
        seen = seen or set()
        if class_name in seen:
            return set()
        info = classes.get(class_name)
        if info is None:
            # A class we do not own — FastAPI, TestClient, CryptContext — is unanalysable, and
            # treating "not found" as "declares nothing" accused every one of them: app.get,
            # client.post, pwd_context.hash. Fourteen false criticals from one wrong default, on a
            # gate that decides whether a round's work is thrown away.
            #
            # Pydantic is the exception, and not a grudging one: its fields are the class body, so a
            # BaseSettings subclass is exactly as readable as one with no base at all.
            return set() if class_name in _ANALYSABLE_FOREIGN_BASES else None
        if info["dynamic"]:
            return None
        seen.add(class_name)
        out = set(info["names"])
        for base in info["bases"]:
            more = declared(base, seen)
            if more is None:
                return None
            out |= more
        return out

    # An attribute assigned onto the singleton anywhere counts as declared.
    assigned: dict[str, set[str]] = defaultdict(set)
    reads: dict[tuple[str, str], list[str]] = defaultdict(list)
    attr_class: dict[tuple[str, str], str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        importer_module = _module_path(file, code_dir)
        # In scope here means: created in this module, or imported FROM the module that creates it.
        in_scope: dict[str, str] = {
            name: cls for (mod, name), cls in singletons.items() if mod == importer_module
        }
        for written_mod, pairs in from_imports_with_aliases(text):
            target_module = resolve_import_target(written_mod, importer_module)
            for name, alias in pairs:
                cls = singletons.get((target_module, name)) or singletons.get(
                    (f"{target_module}.__init__", name)
                )
                if cls:
                    in_scope[alias or name] = cls
        if not in_scope:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            base = node.value.id
            if base not in in_scope:
                continue
            if isinstance(node.ctx, ast.Load) and in_scope[base] not in classes:
                continue
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                assigned[base].add(node.attr)
                continue
            if node.attr.startswith("__") or node.attr in _INHERITED_ATTRS:
                continue
            reads[(base, node.attr)].append(f"{rel}:{node.lineno}")
            attr_class[(base, node.attr)] = in_scope[base]

    import difflib

    findings: list[dict[str, Any]] = []
    for (base, attr), where in sorted(reads.items(), key=lambda kv: -len(kv[1])):
        class_name = attr_class[(base, attr)]
        if class_name not in classes:
            # Only a class this product defines can be judged. `x = object()` or any library
            # constructor is not ours to have an opinion about.
            continue
        known = declared(class_name)
        if known is None or attr in known or attr in assigned.get(base, ()):
            continue
        info = classes.get(class_name) or {}
        # Case and underscore differences first — `ATLAS_BASE_URL` against `atlas_base_url` is the
        # commonest shape of this mistake and difflib cannot see it at all.
        near = _normalised_matches(attr, known)
        # Then prefix relations: `invoke` against `invoke_capability` also scores below any sane
        # difflib cutoff, and yet it is the answer — the round wrote a short alias for a method
        # that exists under a longer name.
        near += [
            k for k in sorted(known)
            if (k.startswith(attr) or attr.startswith(k)) and k not in near
        ][:2]
        near += [
            k
            for k in difflib.get_close_matches(attr, sorted(known), n=2, cutoff=0.7)
            if k not in near
        ]
        near = near[:2]
        findings.append(
            {
                "code": "missing_attribute",
                "severity": "critical",
                "singleton": base,
                "attribute": attr,
                "file": info.get("file", ""),
                "line": info.get("line"),
                "readers": sorted(set(where))[:6],
                "did_you_mean": near,
                "detail": (
                    f"{class_name} never declares '{attr}', read as {base}.{attr} at "
                    + ", ".join(sorted(set(where))[:4])
                    + f". Python raises AttributeError: '{class_name}' object has no attribute "
                    f"'{attr}' the first time that line runs — at import for module-level code — so "
                    f"the app does not start. {_offer(class_name, attr)}"
                    "Do NOT delete the call site to silence this — the call is what the product "
                    f"does. Otherwise declare it on {class_name} in "
                    f"{info.get('file', 'its module')}."
                    + (f" Did you mean {', '.join(near)}?" if near else "")
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def _callable_kwargs(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[set[str], bool]:
    """Keyword names a product method accepts, and whether it has ``**kwargs``."""
    args = fn.args
    names = {a.arg for a in args.posonlyargs + args.args if a.arg not in {"self", "cls"}}
    names |= {a.arg for a in args.kwonlyargs}
    return names, args.kwarg is not None


def find_unexpected_keyword_arguments(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Call site passes a keyword the method does not declare.

    The live Sentinel deploy answered 200 with UNKNOWN because::

        await atlas.get_situation_brief(west=west, east=east, south=south, north=north)

    while AtlasClient.get_situation_brief(self, lat, lon) — TypeError, swallowed by
    ``except Exception``. missing_attribute is silent: the method exists. The mesh
    contract is silent: the envelope is built inside the client, never at the call.
    """
    methods: dict[str, dict[str, tuple[set[str], bool, str, int]]] = {}
    classes_file: dict[str, str] = {}
    singletons: dict[tuple[str, str], str] = {}

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        module_here = _module_path(file, code_dir)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            slot: dict[str, tuple[set[str], bool, str, int]] = {}
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    accepted, has_kw = _callable_kwargs(stmt)
                    slot[stmt.name] = (accepted, has_kw, rel, stmt.lineno)
            methods[node.name] = slot
            classes_file[node.name] = rel
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                call = node.value
                if (
                    isinstance(target, ast.Name)
                    and isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in methods
                ):
                    singletons[(module_here, target.id)] = call.func.id

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        importer_module = _module_path(file, code_dir)
        in_scope: dict[str, str] = {
            name: cls for (mod, name), cls in singletons.items() if mod == importer_module
        }
        for written_mod, pairs in from_imports_with_aliases(text):
            target_module = resolve_import_target(written_mod, importer_module)
            for name, alias in pairs:
                cls = singletons.get((target_module, name)) or singletons.get(
                    (f"{target_module}.__init__", name)
                )
                if cls:
                    in_scope[alias or name] = cls
                # `from ..services.atlas_client import AtlasClient` then `atlas = AtlasClient()`
                if (alias or name) in methods:
                    in_scope[alias or name] = alias or name
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
            ):
                func = node.value.func
                cls_name = None
                if isinstance(func, ast.Name) and func.id in methods:
                    cls_name = func.id
                elif isinstance(func, ast.Attribute) and func.attr in methods:
                    cls_name = func.attr
                if cls_name:
                    in_scope[node.targets[0].id] = cls_name
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            obj = node.func.value.id
            method = node.func.attr
            class_name = in_scope.get(obj)
            if not class_name or class_name not in methods:
                continue
            sig = methods[class_name].get(method)
            if not sig:
                continue
            accepted, has_kw, class_file, _def_line = sig
            if has_kw:
                continue
            for kw in node.keywords:
                if not kw.arg or kw.arg in accepted:
                    continue
                key = (rel, method, kw.arg, class_name)
                if key in seen:
                    continue
                seen.add(key)
                offered = ", ".join(sorted(accepted)) or "(none besides self)"
                findings.append(
                    {
                        "code": "unexpected_keyword_argument",
                        "severity": "critical",
                        "file": rel,
                        "line": node.lineno,
                        "class_file": class_file,
                        "class": class_name,
                        "method": method,
                        "keyword": kw.arg,
                        "detail": (
                            f"{class_name}.{method}() does not accept keyword '{kw.arg}', "
                            f"called as {obj}.{method}({kw.arg}=...) at {rel}:{node.lineno}. "
                            f"The method is defined in {class_file} with parameters: {offered}. "
                            f"Python raises TypeError: {class_name}.{method}() got an unexpected "
                            f"keyword argument '{kw.arg}' the first time that line runs. A "
                            "`except Exception` that returns {\"level\": \"UNKNOWN\"} hides it as "
                            "a 200 forever — that is the defect that shipped on Vercel. Change "
                            f"the call in {rel} to match the signature, or change the signature in "
                            f"{class_file}. Do NOT swallow TypeError into UNKNOWN."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
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


def _is_test_path(rel: str) -> bool:
    lowered = rel.lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_spec.py"))
        or "/tests/" in f"/{lowered}"
        or "/test/" in f"/{lowered}"
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


def run_duplicate_module_check(
    product_id: str,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Pipeline entrypoint. Missing symbols fail the gate; duplicates warn."""
    from core.paths import code_dir as resolve_code_dir
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root)
    code_dir = resolve_code_dir(product_id, data_root=root)
    if not code_dir.is_dir():
        return {"passed": True, "skipped": True, "reason": "no_code_dir", "issues": []}

    try:
        missing = find_missing_symbols(code_dir)
        duplicates = find_duplicate_roles(code_dir)
        orphans = find_orphan_modules_with_broken_imports(code_dir, missing)
        undefined = find_undefined_names(code_dir)
        unregistered = find_unregistered_models(code_dir)
        hallucinated = find_hallucinated_imports(code_dir)
        undeclared = find_undeclared_frontend_deps(code_dir)
        broken_injection = find_route_handlers_with_broken_injection(code_dir)
        dup_tables = find_duplicate_tablenames(code_dir)
        mesh_contract = find_mesh_contract_violations(code_dir)
        absent_modules = find_missing_modules(code_dir)
        absent_attributes = find_missing_instance_attributes(code_dir)
        unexpected_kwargs = find_unexpected_keyword_arguments(code_dir)
        forward_refs = find_class_body_forward_refs(code_dir)
        double_prefix = find_duplicated_router_prefix(code_dir)
        ts_exports = find_frontend_missing_exports(code_dir)
        bad_pairs = find_mismatched_back_populates(code_dir)
        spa_shadows = find_api_routes_shadowing_spa(code_dir)
        case_twins = find_case_collisions(code_dir)
        dead_rewrites = find_dead_path_rewrites(code_dir)
        schema_never = find_orm_schema_never_created(code_dir)
        undeclared_deps = find_undeclared_dependencies(code_dir)
        unstyled = find_unstyled_classes(code_dir)
        hollow = find_capabilities_never_invoked(code_dir)
        sync_wrappers = find_sync_wrapper_over_async_handler(code_dir)
    except Exception as exc:
        logger.warning("duplicate_module_check failed for %s: %s", product_id, exc)
        return {"passed": True, "skipped": True, "reason": f"error:{exc}", "issues": []}

    # A symbol wanted only by files that are being deleted is not a symbol to write.
    # Reporting both turned 5 deletions into 30 "define X" instructions, and the agent
    # dutifully started implementing schemas for endpoints that no longer belong.
    orphan_files = {o["file"] for o in orphans}
    if orphan_files:
        missing = [
            m
            for m in missing
            if not set(m.get("importers") or []).issubset(orphan_files)
        ]

    issues: list[dict[str, Any]] = []
    for item in dead_rewrites:
        issues.append(
            {
                "code": "dead_path_rewrite",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in sync_wrappers:
        issues.append(
            {
                "code": "sync_wrapper_over_async_handler",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in hollow:
        issues.append(
            {
                "code": "capability_never_invoked",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in unstyled:
        issues.append(
            {
                "code": item.get("code"),
                "severity": item.get("severity", "high"),
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in undeclared_deps:
        issues.append(
            {
                "code": "undeclared_dependency",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in schema_never:
        issues.append(
            {
                "code": "orm_schema_never_created",
                "severity": "critical",
                "file": item.get("file"),
                "detail": item.get("detail"),
            }
        )
    for item in case_twins:
        issues.append(
            {
                "code": "case_collision",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in spa_shadows:
        issues.append(
            {
                "code": "api_route_shadows_spa",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in bad_pairs:
        issues.append(
            {
                "code": "mismatched_back_populates",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in ts_exports:
        issues.append(
            {
                "code": "frontend_missing_export",
                "severity": "high",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in double_prefix:
        issues.append(
            {
                "code": "duplicated_router_prefix",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in forward_refs:
        issues.append(
            {
                "code": "class_body_forward_ref",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    # First: the app cannot even be imported, so nothing else can be observed about it.
    for item in absent_modules:
        issues.append(
            {
                "code": "missing_module",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
            }
        )
    for item in absent_attributes:
        issues.append(
            {
                "code": "missing_attribute",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in unexpected_kwargs:
        issues.append(
            {
                "code": "unexpected_keyword_argument",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in mesh_contract:
        issues.append(
            {
                "code": "mesh_contract_violation",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in dup_tables:
        issues.append(
            {
                "code": "duplicate_tablename",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in broken_injection:
        issues.append(
            {
                "code": "route_handler_broken_injection",
                "severity": "critical",
                "detail": item["detail"],
                "file": item["file"],
                "line": item.get("line"),
            }
        )
    for item in undeclared:
        issues.append(
            {
                "code": "undeclared_dependency",
                "severity": "high",
                "detail": (
                    f"{item['file']} imports '{item['package']}' but {item['manifest']} does "
                    f"not declare it. Add it to dependencies — the build fails with "
                    f"\"Cannot find module '{item['package']}'\" after install, so nothing "
                    "before the build catches this."
                ),
                "file": item["file"],
            }
        )
    for item in hallucinated:
        issues.append(
            {
                "code": "hallucinated_import",
                "severity": "high",
                "detail": (
                    f"{item['file']} imports '{item['symbol']}' from {item['module']}, which "
                    f"does not export it. That name does not exist in the installed library — "
                    "check the real API rather than adjusting the import path; this fails at "
                    "import time and takes the whole app down."
                ),
                "file": item["file"],
            }
        )
    for item in unregistered:
        issues.append(
            {
                "code": "models_not_registered",
                "severity": "high",
                "detail": (
                    f"{item['file']} calls Base.metadata.create_all() but imports no model "
                    f"module, so SQLAlchemy only creates tables for models something else "
                    f"happened to import. Import the models package there (e.g. "
                    f"`from app import models`) so {', '.join(item['models'][:6])} are all "
                    "registered — otherwise they fail at runtime with 'no such table'."
                ),
                "file": item["file"],
            }
        )
    for item in undefined:
        issues.append(
            {
                "code": "undefined_name",
                "severity": "high",
                "detail": (
                    f"{item['file']}:{item['line']} uses '{item['name']}' but the module never "
                    f"imports or defines it. Add it to the import at the top of that file — "
                    f"this is one line, and it stops the whole app from importing."
                ),
                "file": item["file"],
            }
        )
    for item in orphans:
        issues.append(
            {
                "code": "orphan_module_breaks_build",
                "severity": "high",
                "detail": (
                    f"DELETE {item['file']} — nothing imports it, "
                    f"{', '.join(item.get('superseded_by') or [])} superseded it, and its "
                    f"dangling imports ({', '.join(item['broken_imports'])}) break the package "
                    "for everything that does. Removing the file is the fix, not adding the "
                    "symbols it wants."
                ),
                "file": item["file"],
            }
        )
    for item in missing:
        issues.append(
            {
                "code": "missing_symbol",
                # Critical, like every other defect that stops the import. As "high" it was worth 3
                # to the round guard against 4 for a duplicate table, though both mean the app never
                # starts — and it is the one that arrives nine at a time.
                "severity": "critical",
                "detail": (
                    (item.get("fix_hint") + " ") if item.get("fix_hint") else ""
                )
                + (
                    f"{item['file']} does not define '{item['symbol']}', but "
                    f"{len(item['importers'])} module(s) import it "
                    f"({', '.join(item['importers'][:4])}). "
                    + (
                        f"It does define {' / '.join(repr(c) for c in item['did_you_mean'])}. "
                        f"If {item['did_you_mean'][0]!r} is the same function, the stable fix is "
                        f"one line in that module — `{item['symbol']} = {item['did_you_mean'][0]}` "
                        "— which satisfies both names. Renaming instead breaks whatever still "
                        "calls the old one, and this has already flip-flopped between the two. "
                        "Do not write a second implementation. "
                        if item.get("did_you_mean")
                        else ""
                    )
                    + "Define it there — do NOT add another module that imports it."
                ),
                "file": item["file"],
                "symbol": item["symbol"],
            }
        )
    for item in duplicates:
        issues.append(
            {
                "code": "duplicate_modules",
                "severity": "medium",
                "detail": (
                    f"{len(item['files'])} files implement '{item['role']}': "
                    f"{', '.join(item['files'])}. Keep ONE and delete the rest — "
                    "unreachable duplicates hide the file that is actually wired up."
                ),
                "file": item["files"][0],
            }
        )

    return {
        # Duplicates alone are a smell; a symbol nothing defines is a broken build.
        # A route handler FastAPI cannot call blocks too. It was reported as critical and
        # the gate still passed, which makes it one line in a list the round may or may
        # not act on — and this class costs a 500 on every request to the endpoint, so a
        # product whose only feature is one endpoint is simply dead while the gate is
        # green. Blocking is what turns the finding into the round's work.
        # The two newest detectors were reported as critical and left out of this expression, so the
        # gate went green with a defect that stops the app importing. Caught on the live product at the
        # moment everything else closed: module_health PASSED with one missing_attribute —
        # `rule_engine.compute_advisory`, read by routers/advisory.py:62, gone because a round renamed
        # it. A critical that does not fail its own gate is one line in a list the round may or may not
        # act on, which is the same lesson the route-handler class taught two comments above.
        "passed": not missing and not undefined and not unregistered and not hallucinated
        and not undeclared and not broken_injection and not dup_tables
        and not mesh_contract and not absent_modules and not absent_attributes
        and not forward_refs and not double_prefix and not ts_exports
        and not bad_pairs and not spa_shadows and not case_twins
        and not schema_never
        and not undeclared_deps
        and not unstyled
        and not hollow
        and not sync_wrappers
        and not dead_rewrites
        and not unexpected_kwargs,
        "skipped": False,
        "issues": issues,
        "missing_symbols": missing,
        "undefined_names": undefined,
        "duplicate_roles": duplicates,
        "orphan_modules": orphans,
    }


_TS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\s[^\n;]*?from\s*['"](\.[^'"]+)['"]""",
)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".css", ".svg")


def find_unresolved_frontend_imports(code_dir: Path, limit: int = 12) -> list[dict[str, Any]]:
    """Relative imports in TS/JS that point at no file on disk.

    The round guard was Python-only, so a repair could fix one backend symbol and
    delete or rename half the frontend without the score moving. Type-level
    mismatches still need tsc, but a module that simply is not there is cheap to
    catch and is the failure that breaks a build hardest.
    """
    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in _TS_IMPORT_RE.findall(text):
            target = (file.parent / spec).resolve()
            if any(
                target.with_suffix(sfx).is_file() for sfx in _TS_SUFFIXES
            ) or target.is_file():
                continue
            if any((target / f"index{sfx}").is_file() for sfx in _TS_SUFFIXES):
                continue
            findings.append(
                {
                    "file": file.relative_to(code_dir).as_posix(),
                    "import": spec,
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


_CREATE_ALL_RE = re.compile(r"\bmetadata\s*\.\s*create_all\s*\(")
_TABLENAME_RE = re.compile(r"^\s*__tablename__\s*=", re.M)


_TS_EXPORT_DECL_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?"
    r"(?:function\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_TS_EXPORT_BRACE_RE = re.compile(
    r"^\s*export\s+(?:type\s+)?\{([^}]*)\}(?:\s*from\s*[\"']([^\"']+)[\"'])?", re.M
)
_TS_EXPORT_DEFAULT_RE = re.compile(r"^\s*export\s+default\b", re.M)
_TS_EXPORT_STAR_RE = re.compile(r"^\s*export\s*\*\s*from", re.M)
_TS_IMPORT_STMT_RE = re.compile(
    r"^\s*import\s+(type\s+)?([^;'\"]+?)\s+from\s*[\"']([^\"']+)[\"']", re.M
)
_TS_CODE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")


def _ts_resolve(file: Path, spec: str) -> Path | None:
    """The product file a relative TS import points at, or ``None``."""
    if not spec.startswith("."):
        return None  # third-party or aliased: not ours to judge
    base = (file.parent / spec).resolve()
    for cand in [base.with_suffix(sfx) for sfx in _TS_CODE_SUFFIXES] + [base] + [
        base / f"index{sfx}" for sfx in _TS_CODE_SUFFIXES
    ]:
        if cand.is_file():
            return cand
    return None


def _ts_exports_of(text: str) -> tuple[set[str], bool, bool]:
    """``(named exports, has_default, dynamic)`` for one TS module."""
    names = set(_TS_EXPORT_DECL_RE.findall(text))
    for inner, _from in _TS_EXPORT_BRACE_RE.findall(text):
        for piece in inner.split(","):
            piece = piece.strip()
            if not piece:
                continue
            # `A as B` exports B; a bare `A` exports A.
            parts = piece.split()
            names.add(parts[-1] if len(parts) == 3 and parts[1] == "as" else parts[0])
    has_default = bool(_TS_EXPORT_DEFAULT_RE.search(text))
    # `export *` makes the surface unenumerable; so does an export keyword our patterns missed.
    dynamic = bool(_TS_EXPORT_STAR_RE.search(text)) or (
        "export" in text and not names and not has_default
    )
    return names, has_default, dynamic


def find_frontend_missing_exports(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Named imports between the product's own TS files that the target never exports.

    The TypeScript twin of ``find_missing_symbols``, built for the same reason its Python sibling
    was: the last defect on a live product was a cross-file refactor — the frontend API layer plus
    five consumers — and every attempt was dismembered because the static score could not see
    TypeScript at all. The salvage log shows the coin flip in plain text: ``the rest of the round
    stands (0 vs 0 before)``. Reverting the API layer alone left five importers referencing exports
    that no longer existed, tsc failed with TS2305 five times, and the guard reverted the round —
    three rounds running, with the score reading zero throughout.

    Only relative imports between product files are judged. Third-party and aliased imports are
    skipped, a target that cannot be resolved is ``find_unresolved_frontend_imports``' business, a
    module with ``export *`` (or export syntax these patterns cannot parse) is treated as
    unenumerable and skipped — this feeds a score that discards work, so a false positive costs more
    than a miss.
    """
    modules: dict[Path, tuple[set[str], bool, bool]] = {}
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx"):
            continue
        try:
            modules[file.resolve()] = _ts_exports_of(
                file.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            continue

    import difflib

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*"):
        if file.suffix.lower() not in (".ts", ".tsx"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        importer = file.relative_to(code_dir).as_posix()
        for _type_kw, clause, spec in _TS_IMPORT_STMT_RE.findall(text):
            target = _ts_resolve(file, spec)
            if target is None or target.resolve() not in modules:
                continue
            exports, has_default, dynamic = modules[target.resolve()]
            if dynamic:
                continue
            rel_target = target.resolve().relative_to(code_dir.resolve()).as_posix()

            wanted: list[str] = []
            default_wanted = False
            body = clause.strip()
            brace = re.search(r"\{([^}]*)\}", body)
            if brace:
                for piece in brace.group(1).split(","):
                    piece = piece.strip()
                    if not piece:
                        continue
                    parts = piece.replace("type ", "").split()
                    wanted.append(parts[0])
                head = body[: brace.start()].strip().rstrip(",").strip()
                if head and not head.startswith("*"):
                    default_wanted = True
            elif body.startswith("*"):
                continue  # namespace import: member use is not statically checkable here
            elif body:
                default_wanted = True

            for name in wanted:
                if name in exports:
                    continue
                near = _normalised_matches(name, exports) or difflib.get_close_matches(
                    name, sorted(exports), n=2, cutoff=0.7
                )
                findings.append(
                    {
                        "code": "frontend_missing_export",
                        "severity": "high",
                        "file": rel_target,
                        "importer": importer,
                        "name": name,
                        "did_you_mean": near,
                        "detail": (
                            f"{importer} imports {{ {name} }} from '{spec}', but {rel_target} "
                            f"never exports '{name}'. tsc fails with TS2305 and `npm run build` "
                            "produces nothing to deploy."
                            + (f" It does export {', '.join(near)} — if that is the same thing, "
                               f"fix the IMPORT in {importer}; renaming the export instead breaks "
                               "every other importer." if near else "")
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
            if default_wanted and not has_default and not exports:
                findings.append(
                    {
                        "code": "frontend_missing_export",
                        "severity": "high",
                        "file": rel_target,
                        "importer": importer,
                        "name": "default",
                        "did_you_mean": [],
                        "detail": (
                            f"{importer} default-imports from '{spec}', but {rel_target} has no "
                            "default export. tsc fails and the build produces nothing to deploy."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


def find_unregistered_models(code_dir: Path) -> list[dict[str, Any]]:
    """Models that ``create_all()`` will silently skip.

    SQLAlchemy creates tables only for models that have been *imported* by the
    time ``Base.metadata.create_all()`` runs. A product whose main module calls
    create_all without importing its models package gets whichever tables happen
    to be pulled in transitively — and the rest fail at runtime with
    ``no such table``, long after every static check has passed.

    Seen on a live product: login worked because Operator was imported somewhere,
    while /api/operator/spend 500'd on ``no such table: budget_spends``.
    """
    model_modules: list[str] = []
    for file in iter_product_files(code_dir, "*.py"):
        if file.parent.name not in ("models", "model"):
            continue
        if file.name == "__init__.py":
            continue
        try:
            if _TABLENAME_RE.search(file.read_text(encoding="utf-8", errors="replace")):
                model_modules.append(file.stem)
        except OSError:
            continue
    if not model_modules:
        return []

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _CREATE_ALL_RE.search(text):
            continue
        # Importing the package (or a star/aggregate import of it) registers every
        # model its __init__ pulls in; that is the idiomatic fix.
        imports_package = bool(
            # from app.models import X   /  from ..models import X
            re.search(r"^\s*from\s+[\w.]*models\s+import\b", text, re.M)
            # import app.models
            or re.search(r"^\s*import\s+[\w.]*models\b", text, re.M)
            # from app.models.budget_spend import BudgetSpend
            or re.search(r"^\s*from\s+[\w.]*models\.[\w.]+\s+import\b", text, re.M)
            # from app import models  — the package arrives as a name, not a path
            or re.search(r"^\s*from\s+[\w.]+\s+import\s+[^\n]*\bmodels\b", text, re.M)
        )
        if imports_package:
            continue
        findings.append(
            {
                "file": file.relative_to(code_dir).as_posix(),
                "models": sorted(model_modules)[:10],
            }
        )
    return findings


# Frameworks the factory itself has installed, so a generated import from them can be
# verified without booting the product. Hallucinated framework APIs are a classic
# generation failure: `from fastapi.responses import JavaScriptResponse` looks entirely
# plausible, does not exist, and takes the whole app down at import time.
_VERIFIABLE_PACKAGES = (
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "httpx",
    "jose",
    "passlib",
)


_TAILWIND_UTILITY_RE = re.compile(
    r"^(?:sm:|md:|lg:|xl:|2xl:|hover:|focus:|active:|disabled:|dark:|group-hover:)*"
    r"(?:flex|grid|block|inline|hidden|container|"
    r"(?:p|m|px|py|pt|pb|pl|pr|mx|my|mt|mb|ml|mr|gap|space|w|h|min-w|min-h|max-w|max-h|top|bottom|left|right|inset|z)-[\w./\[\]-]+|"
    r"(?:bg|text|border|ring|shadow|from|to|via|fill|stroke|divide|outline|accent)-[\w./\[\]-]+|"
    r"(?:rounded|font|leading|tracking|items|justify|self|content|place|order|col|row|overflow|opacity|cursor|transition|duration|ease|animate|object|whitespace|break|truncate|select|pointer-events|sr-only|antialiased|uppercase|lowercase|capitalize|italic|underline|absolute|relative|fixed|sticky|static)(?:-[\w./\[\]-]+)?)$"
)

_CLASSNAME_ATTR_RE = re.compile(r"""(class(?:Name)?=)(['"])([^'"]*)\2""")


def product_has_tailwind(code_dir: Path) -> bool:
    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("node_modules", "dist", "build", ".next", ".aicom_sandbox") for part in Path(rel).parts):
            continue
        if file.name in ("package.json",) or file.name.startswith("tailwind.config"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if "tailwind" in blob.lower():
                return True
            continue
        if file.suffix in (".css", ".scss", ".sass", ".less"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "@tailwind" in blob or "@apply" in blob:
                return True
    return False


def _stylesheet_path(code_dir: Path) -> Path | None:
    for candidate in (
        "frontend/src/styles/index.css",
        "frontend/src/index.css",
        "src/styles/index.css",
        "src/index.css",
    ):
        path = code_dir / candidate
        if path.is_file():
            return path
    return None


def _safe_product_file(code_dir: Path, rel: str) -> Path | None:
    if not rel or any(p in Path(rel).parts for p in ("node_modules", "dist", ".aicom_sandbox")):
        return None
    try:
        path = (code_dir / rel).resolve()
        path.relative_to(code_dir.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def strip_orphan_tailwind_classnames(code_dir: Path, relative_paths: list[str]) -> list[str]:
    """Drop Tailwind utilities from this round's markup when the product has no Tailwind.

    Live: a demo_quality round wrote the widget plus one ``text-muted``. The rollback
    score treated that as +5, salvage could not keep any landing file, and three
    attempts restored the tree. QA then asked for the same UI again.
    """
    if product_has_tailwind(code_dir):
        return []
    changed: list[str] = []
    for rel in relative_paths:
        path = _safe_product_file(code_dir, rel)
        if path is None or path.suffix.lower() not in {".tsx", ".jsx", ".html"}:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue

        def _repl(match: re.Match[str]) -> str:
            prefix, quote, value = match.group(1), match.group(2), match.group(3)
            kept = [tok for tok in value.split() if not _TAILWIND_UTILITY_RE.match(tok)]
            return f"{prefix}{quote}{' '.join(kept)}{quote}"

        updated = _CLASSNAME_ATTR_RE.sub(_repl, original)
        if updated == original:
            continue
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError:
            continue
        changed.append(rel)
    return changed


def ensure_markup_classes_have_rules(code_dir: Path, relative_paths: list[str]) -> list[str]:
    """Append CSS selectors for semantic classes this round used without a rule.

    Eight new class names without rules is ``unstyled_classes``: another +5 on the
    rollback score, same total restore as the stray Tailwind token.
    """
    stylesheet = _stylesheet_path(code_dir)
    if stylesheet is None:
        return []
    try:
        css_blob = stylesheet.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    defined = {m.group(1) for m in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", css_blob)}
    missing: list[str] = []
    seen: set[str] = set()
    for rel in relative_paths:
        path = _safe_product_file(code_dir, rel)
        if path is None or path.suffix.lower() not in {".tsx", ".jsx", ".html"}:
            continue
        try:
            blob = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _CLASSNAME_ATTR_RE.finditer(blob):
            for cls in match.group(3).split():
                cls = cls.strip()
                if (
                    cls
                    and cls not in defined
                    and cls not in seen
                    and not _TAILWIND_UTILITY_RE.match(cls)
                    and not cls.startswith(("js-", "data-"))
                ):
                    seen.add(cls)
                    missing.append(cls)
    if not missing:
        return []
    block = "\n".join(f".{name} {{}}" for name in missing)
    try:
        stylesheet.write_text(css_blob.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
    except OSError:
        return []
    return missing


def find_unstyled_classes(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Markup whose class names have no styling behind them.

    Reported by a human looking at the deployed product and asking "where is the design?" — every
    gate was green. The build compiled, the browser rendered, the demo-quality gate counted sections
    and CTAs. None of them asked whether the classes in the markup mean anything.

    Two distinct failures, both fatal to the look and invisible to a type checker:

    * **Tailwind utilities with no Tailwind.** The live product used `bg-slate-800`, `flex`,
      `gap-2`, `focus:ring-2` throughout — and had no tailwindcss dependency and no config, so those
      class names styled nothing at all. The page rendered as unstyled HTML with a few colours from
      the handful of real rules that did exist.
    * **Semantic classes nobody wrote rules for.** 64 distinct classes used in JSX, 21 defined in
      the stylesheet.

    A type checker cannot see this: class names are strings. The browser cannot fail on it: unstyled
    markup renders fine. It has to be compared, which is what this does.
    """
    used: dict[str, list[str]] = {}
    defined: set[str] = set()
    has_tailwind = False

    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("node_modules", "dist", "build", ".next", ".aicom_sandbox") for part in Path(rel).parts):
            continue
        if file.name in ("package.json",) or file.name.startswith("tailwind.config"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if "tailwind" in blob.lower():
                has_tailwind = True
            continue
        if file.suffix in (".css", ".scss", ".sass", ".less"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "@tailwind" in blob or "@apply" in blob:
                has_tailwind = True
            for match in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", blob):
                defined.add(match.group(1))
        elif file.suffix in (".tsx", ".jsx"):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in re.finditer(r"class(?:Name)?=[\"']([^\"'{}]+)[\"']", blob):
                for cls in match.group(1).split():
                    cls = cls.strip()
                    if cls:
                        used.setdefault(cls, []).append(rel)

    if not used:
        return []

    findings: list[dict[str, Any]] = []
    style_target = ""
    for candidate in ("frontend/src/styles/index.css", "frontend/src/index.css", "src/styles/index.css", "src/index.css"):
        if (code_dir / candidate).is_file():
            style_target = candidate
            break

    tailwind_used = sorted(c for c in used if _TAILWIND_UTILITY_RE.match(c) and c not in defined)
    if tailwind_used and not has_tailwind:
        files_hit = sorted({f for c in tailwind_used for f in used[c]})
        findings.append(
            {
                "code": "tailwind_utilities_without_tailwind",
                "severity": "critical",
                "file": files_hit[0] if files_hit else (style_target or "package.json"),
                "classes": tailwind_used[:12],
                "detail": (
                    f"{len(tailwind_used)} Tailwind utility classes are used in the markup "
                    f"({', '.join(tailwind_used[:8])}) and this product has NO tailwindcss "
                    "dependency, no tailwind config and no @tailwind directives — so every one of "
                    "them styles nothing. The page renders as unstyled HTML no matter how correct "
                    "the components are, which is exactly what a person sees and a type checker "
                    "cannot. Pick ONE: either add tailwindcss (dependency + config + @tailwind "
                    f"directives in {style_target or 'the global stylesheet'}), or replace these "
                    "utility classes with the product's own semantic classes and write their rules."
                ),
            }
        )

    semantic_unstyled = sorted(
        c for c in used
        if c not in defined and not _TAILWIND_UTILITY_RE.match(c) and not c.startswith(("js-", "data-"))
    )
    # A couple of stragglers is noise; a third of the markup is a missing stylesheet.
    if len(semantic_unstyled) >= 8 and style_target:
        files_hit = sorted({f for c in semantic_unstyled for f in used[c]})
        findings.append(
            {
                "code": "unstyled_classes",
                "severity": "high",
                "file": style_target,
                "classes": semantic_unstyled[:12],
                "detail": (
                    f"{len(semantic_unstyled)} class names appear in the markup with no rule "
                    f"anywhere in the product's stylesheets ({', '.join(semantic_unstyled[:8])}). "
                    f"The components render, and they render unstyled. Add rules for them to "
                    f"{style_target} (or remove the class names if the elements are meant to "
                    f"inherit). Used in: {', '.join(files_hit[:3])}."
                ),
            }
        )
    return findings[:limit]


def find_undeclared_dependencies(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Third-party imports the product never declares as dependencies.

    Found the only way this class of defect ever gets found: in production. The factory published a
    full-stack product to Vercel, the page served 200, and every API route answered
    FUNCTION_INVOCATION_FAILED. The function log said:

        File "/var/task/api/app/utils/security.py", line 7, in <module>
            import jwt
        ModuleNotFoundError: No module named 'jwt'

    ``requirements.txt`` declared ``python-jose[cryptography]`` — a different package that provides
    ``jose``, not ``jwt``. Nothing caught it, because the sandbox venv happened to have PyJWT
    installed: every gate ran against an environment more generous than production, which is the
    definition of a test that cannot fail for the reason that matters.

    Import name and package name are frequently different (``jwt`` → PyJWT, ``PIL`` → Pillow,
    ``cv2`` → opencv-python), so the mapping is explicit; unknown packages fall back to the usual
    normalisation, and anything ambiguous is left alone rather than guessed at.
    """
    import sys as _sys

    # Import name -> the distribution that provides it, where the two differ.
    known_aliases = {
        "jwt": "pyjwt",
        "jose": "python-jose",
        "PIL": "pillow",
        "cv2": "opencv-python",
        "yaml": "pyyaml",
        "sklearn": "scikit-learn",
        "dotenv": "python-dotenv",
        "bs4": "beautifulsoup4",
        "dateutil": "python-dateutil",
        "multipart": "python-multipart",
        "jwt_extended": "flask-jwt-extended",
        "psycopg2": "psycopg2-binary",
        "redis": "redis",
        "magic": "python-magic",
        "serial": "pyserial",
        "usb": "pyusb",
        "OpenSSL": "pyopenssl",
        "Crypto": "pycryptodome",
        "google": "google-cloud-storage",
        "attr": "attrs",
        "zoneinfo": "",  # stdlib on 3.9+
    }

    declared: set[str] = set()
    declaration_files: list[str] = []

    def _norm(name: str) -> str:
        return re.split(r"[<>=!\[;]", str(name).strip(), maxsplit=1)[0].strip().lower().replace("_", "-")

    def _declare(spec: str) -> None:
        """Record the distribution AND its extras. ``passlib[bcrypt]`` provides ``bcrypt`` too, and
        demanding a separate requirements line for it would be noise the product cannot act on."""
        declared.add(_norm(spec))
        extras = re.search(r"\[([^\]]+)\]", str(spec))
        if extras:
            for extra in extras.group(1).split(","):
                cleaned = extra.strip().lower().replace("_", "-")
                if cleaned:
                    declared.add(cleaned)

    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if file.name.startswith("requirements") and file.suffix == ".txt":
            declaration_files.append(rel)
            try:
                for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-")):
                        _declare(line)
            except OSError:
                continue
        elif file.name in ("pyproject.toml", "setup.cfg", "Pipfile"):
            declaration_files.append(rel)
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in re.finditer(r"[\"']([A-Za-z0-9][A-Za-z0-9._-]+)\s*(?:[<>=!~\[][^\"']*)?[\"']", blob):
                _declare(match.group(1))

    if not declaration_files:
        return []  # nothing declares anything: a different defect, not this one

    # Everything importable from within the product itself.
    local_roots: set[str] = set()
    for entry in code_dir.rglob("*"):
        rel_parts = entry.relative_to(code_dir).parts
        if any(
            p in ("node_modules", "dist", "build", ".next", "__pycache__", ".venv",
                  "preview-venv", ".git", ".aicom_sandbox")
            or p.startswith(".")
            for p in rel_parts
        ):
            continue
        if entry.is_dir():
            local_roots.add(entry.name)
        elif entry.suffix == ".py":
            local_roots.add(entry.stem)

    stdlib = set(getattr(_sys, "stdlib_module_names", set())) | {
        "__future__", "typing_extensions", "setuptools", "pkg_resources",
    }

    offenders: dict[str, list[str]] = {}
    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        # Test-only imports are a dev concern, and a product that ships without pytest is fine.
        if "/tests/" in f"/{rel}" or file.name.startswith("test_"):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        roots: set[str] = set()
        for match in re.finditer(r"^\s*import\s+([A-Za-z_][\w.]*)", text, re.M):
            roots.add(match.group(1).split(".")[0])
        for match in re.finditer(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import", text, re.M):
            roots.add(match.group(1).split(".")[0])
        for root in roots:
            if root in stdlib or root in local_roots:
                continue
            dist = known_aliases.get(root, root.lower().replace("_", "-"))
            if not dist or dist in declared:
                continue
            # A declared extra such as passlib[bcrypt] provides `bcrypt` too; be conservative and
            # accept any declaration whose name contains the import root.
            if any(root.lower() in d for d in declared):
                continue
            offenders.setdefault(root, []).append(rel)

    findings: list[dict[str, Any]] = []
    target = declaration_files[0]
    for root, files in sorted(offenders.items()):
        dist = known_aliases.get(root, root.lower().replace("_", "-"))
        findings.append(
            {
                "code": "undeclared_dependency",
                "severity": "critical",
                "file": target,
                "import_root": root,
                "package": dist,
                "importers": sorted(files)[:4],
                "detail": (
                    f"`import {root}` in {', '.join(sorted(files)[:3])} is not covered by any "
                    f"declared dependency in {target}. It works in the sandbox only because that "
                    "environment happens to have the package installed; in a clean install — a "
                    "Docker build, a Vercel function, any deploy — the import raises "
                    f"ModuleNotFoundError and every route in the app returns a 500 before running "
                    f"a line of its own code. Add `{dist}` to {target}. Note that the import name "
                    "and the package name differ here"
                    if known_aliases.get(root)
                    else f"Add `{dist}` to {target}."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_hallucinated_imports(code_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Names imported from a known framework that the framework does not export."""
    import importlib

    findings: list[dict[str, Any]] = []
    module_cache: dict[str, Any] = {}

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for module, imported_names in from_imports(text):
            root = module.split(".")[0]
            if root not in _VERIFIABLE_PACKAGES:
                continue
            if module not in module_cache:
                try:
                    module_cache[module] = importlib.import_module(module)
                except Exception:
                    module_cache[module] = None  # not installed here; not our verdict
            mod = module_cache[module]
            if mod is None:
                continue
            for name in imported_names:
                if not name or name == "*":
                    continue
                if hasattr(mod, name):
                    continue
                findings.append(
                    {
                        "file": file.relative_to(code_dir).as_posix(),
                        "module": module,
                        "symbol": name,
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


_TS_PKG_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\s[^\n;]*?from\s*['"]([^'".][^'"]*)['"]""",
)
# Bare specifiers that resolve without a dependency entry.
_TS_BUILTIN_PREFIXES = ("node:", "@/", "~/", "virtual:")


def find_undeclared_frontend_deps(code_dir: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Packages the frontend imports but package.json never declares.

    `import axios from 'axios'` with no axios in dependencies compiles in an editor
    and dies as `TS2307: Cannot find module 'axios'` in the build — after install,
    so nothing earlier catches it.
    """
    import json as _json

    findings: list[dict[str, Any]] = []
    for pkg_file in iter_product_files(code_dir, "package.json"):
        try:
            manifest = _json.loads(pkg_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        declared = set()
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            block = manifest.get(field)
            if isinstance(block, dict):
                declared.update(block)
        root = pkg_file.parent
        seen: set[str] = set()
        for source in iter_product_files(root, "*"):
            if source.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                continue
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for spec in _TS_PKG_IMPORT_RE.findall(text):
                if spec.startswith(_TS_BUILTIN_PREFIXES):
                    continue
                # '@scope/name/sub' -> '@scope/name';  'axios/lib' -> 'axios'
                parts = spec.split("/")
                pkg = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
                if not pkg or pkg in declared or pkg in seen:
                    continue
                seen.add(pkg)
                findings.append(
                    {
                        "file": source.relative_to(code_dir).as_posix(),
                        "package": pkg,
                        "manifest": pkg_file.relative_to(code_dir).as_posix(),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


# A custom decorator between the route decorator and the handler is a FastAPI footgun that
# costs a 500 on EVERY call, and it is invisible to every other check here: the tree imports
# cleanly, the symbols all resolve, the frontend builds. Only calling the endpoint reveals it.
#
# The shape, taken from a product that carried it through roughly ninety repair rounds:
#
#     @router.get("", response_model=AdvisoryResponse)
#     @rate_limited(max_calls=..., period=60)              # ← the trap
#     async def get_advisory(lat=Query(...), lon=Query(...), db=Depends(get_db)):
#
#     def rate_limited(...):
#         def decorator(func):
#             @wraps(func)
#             async def wrapper(request: Request, *args, **kwargs):   # ← demands `request`
#                 return await func(request, *args, **kwargs)         # ← and forwards it
#
# ``@wraps`` sets ``__wrapped__``, so FastAPI's ``inspect.signature`` follows it to the
# handler and sees no ``request`` — it never supplies one. It then calls the wrapper without
# it, and the wrapper requires it positionally:
#
#     TypeError: get_advisory() missing 1 required positional argument: 'request'
#
# (the name is the handler's because ``@wraps`` copied ``__name__``, which sends anyone
# debugging it to the wrong function). And had FastAPI supplied it, ``func(request, ...)``
# would have passed the request straight into ``lat``.
_ROUTE_DECORATOR_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}
)


def _is_route_decorator(node: ast.expr) -> bool:
    """``@router.get(...)`` / ``@app.post(...)`` and friends."""
    call = node.func if isinstance(node, ast.Call) else node
    return isinstance(call, ast.Attribute) and call.attr in _ROUTE_DECORATOR_METHODS


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _wrapper_required_params(code_dir: Path, decorator: str) -> list[str]:
    """Required positional parameters the decorator's wrapper adds, if we can find it.

    Resolving the decorator makes the difference between a useful finding and a nag: plenty of
    decorators are harmless, and only one that *demands a parameter the handler does not
    declare* actually breaks injection.
    """
    if not decorator:
        return []
    for path in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != decorator:
                continue
            # decorator -> inner decorator(func) -> wrapper(...): take the innermost function
            inner = [
                child
                for child in ast.walk(node)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child is not node
            ]
            if not inner:
                continue
            wrapper = inner[-1]
            required = [
                a.arg
                for a in wrapper.args.args
                if a.arg not in ("self", "cls")
            ]
            # Parameters with defaults are optional and cannot break the call.
            defaults = len(wrapper.args.defaults or [])
            if defaults:
                required = required[: len(required) - defaults]

            # A decorator FACTORY takes the function itself — `def rate_limit(times, seconds)` ->
            # `def decorator(func)` -> `limiter.limit(...)(func)`. `func` is the handler, not a
            # parameter the handler must declare, and reporting it produced an instruction no round
            # could usefully follow: "get_advisory is decorated with @rate_limit, whose wrapper
            # requires func". Measured while the real defect was something else entirely.
            required = [r for r in required if r not in ("func", "fn", "f", "handler", "endpoint")]

            # slowapi reads the request out of the handler's own signature, so a limited endpoint
            # must declare `request`. Without it the app raises at import time:
            #   Exception: No "request" or "websocket" argument on function "get_advisory"
            # which is boot-fatal and was the actual cause of a dead backend on a shipped product.
            body_src = ast.dump(node)
            if "limiter" in body_src and "limit" in body_src:
                if "request" not in required:
                    required.append("request")
            return required
    return []


def find_route_handlers_with_broken_injection(
    code_dir: Path, limit: int = MAX_FINDINGS
) -> list[dict[str, Any]]:
    """Route handlers whose extra decorator demands a parameter FastAPI will not supply."""
    findings: list[dict[str, Any]] = []
    for path in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = list(node.decorator_list or [])
            if not any(_is_route_decorator(d) for d in decorators):
                continue
            extra = [d for d in decorators if not _is_route_decorator(d)]
            if not extra:
                continue
            handler_params = {a.arg for a in node.args.args} | {
                a.arg for a in (node.args.kwonlyargs or [])
            }
            for dec in extra:
                name = _decorator_name(dec)
                needed = _wrapper_required_params(code_dir, name)
                missing = [p for p in needed if p not in handler_params]
                if not missing:
                    continue
                findings.append(
                    {
                        "file": str(path.relative_to(code_dir)),
                        "line": node.lineno,
                        "handler": node.name,
                        "decorator": name,
                        "detail": (
                            (
                                f"{node.name} is decorated with @{name}, which applies a slowapi "
                                "rate limiter. slowapi reads the request out of the handler's own "
                                f"signature, so {node.name} must declare `request: Request` (import "
                                "Request from fastapi) — without it the application raises at "
                                'import time: No "request" or "websocket" argument on function '
                                f'"{node.name}", the module never loads, and every route in the app '
                                "is dead, not just this one. Add the parameter; do not remove the "
                                "decorator."
                            )
                            if "request" in missing
                            else
                            f"{node.name} is decorated with @{name}, whose wrapper requires "
                            f"{', '.join(missing)} — but {node.name} does not declare "
                            f"{'them' if len(missing) > 1 else 'it'}, so FastAPI (which reads "
                            f"the wrapped signature through __wrapped__) never supplies "
                            f"{'them' if len(missing) > 1 else 'it'} and every call raises "
                            f"TypeError: {node.name}() missing {len(missing)} required "
                            f"positional argument(s). Fix by declaring "
                            f"{', '.join(f'{p}: Request' if p == 'request' else p for p in missing)} "
                            f"on {node.name} and passing it through, or by making the wrapper "
                            f"take *args/**kwargs only and read what it needs from those."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


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


_CAPABILITY_ID_RE = re.compile(r"\b([a-z][\w]*(?:\.[a-z][\w]*)+@v\d+)\b")


def find_sync_wrapper_over_async_handler(
    code_dir: Path, limit: int = MAX_FINDINGS
) -> list[dict[str, Any]]:
    """A decorator whose wrapper is ``def`` applied to a handler that is ``async def``.

    The last runtime defect of a long repair, and invisible to every other check. The product's own
    rate-limit decorator built a synchronous wrapper::

        def rate_limit(times, seconds):
            def decorator(func):
                def wrapper(*args, **kwargs):     # sync
                    ...
                    return func(*args, **kwargs)  # returns a coroutine, unawaited
                return wrapper

    applied to ``async def get_advisory(...)``. FastAPI inspects the wrapper, sees a plain function,
    calls it, and gets a coroutine object as the response::

        ResponseValidationError: {'type': 'model_attributes_type', 'loc': ('response',),
          'input': <coroutine object get_advisory ...>}
        RuntimeWarning: coroutine 'get_advisory' was never awaited

    Every request to that route answers 500, the traceback names the response model rather than the
    decorator, and the route handler is correct — which is why three rounds looked at advisory.py and
    at the schema instead of at deps.py.
    """
    findings: list[dict[str, Any]] = []
    sync_factories: dict[str, str] = {}   # decorator name -> file it is defined in

    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inner = [
                child
                for child in ast.walk(node)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not node
            ]
            if not inner:
                continue
            wrapper = inner[-1]
            if isinstance(wrapper, ast.AsyncFunctionDef):
                continue  # an async wrapper awaits properly; nothing to say
            # Does the wrapper hand back the result of calling the wrapped function?
            returns_call = any(
                isinstance(stmt, ast.Return)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                for stmt in ast.walk(wrapper)
            )
            if returns_call:
                sync_factories.setdefault(node.name, rel)

    if not sync_factories:
        return []

    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for dec in node.decorator_list or []:
                name = ""
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Name):
                    name = target.id
                elif isinstance(target, ast.Attribute):
                    name = target.attr
                if name not in sync_factories:
                    continue
                findings.append(
                    {
                        "code": "sync_wrapper_over_async_handler",
                        "severity": "critical",
                        "file": sync_factories[name],
                        "handler": node.name,
                        "handler_file": rel,
                        "decorator": name,
                        "detail": (
                            f"@{name} (defined in {sync_factories[name]}) wraps the async handler "
                            f"{node.name} in {rel}:{node.lineno} with a SYNCHRONOUS wrapper that "
                            "returns func(...) without awaiting it. FastAPI inspects the wrapper, "
                            "sees a plain function, calls it, and receives a coroutine object as the "
                            "response — every request to this route answers 500 with "
                            "ResponseValidationError: 'Input should be a valid dictionary or object' "
                            f"and a RuntimeWarning that coroutine '{node.name}' was never awaited. "
                            "The handler itself is correct; do not edit it, and do not change the "
                            f"response model. Fix the wrapper in {sync_factories[name]}: make it "
                            "`async def wrapper(*args, **kwargs)` and `return await "
                            "func(*args, **kwargs)` (use functools.wraps so FastAPI still sees the "
                            "handler's signature), or handle both cases with "
                            "inspect.iscoroutinefunction(func)."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings


def find_capabilities_never_invoked(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """A capability the product is built around, reachable from no request path.

    The failure this catches is not a bug — it is a round taking the cheapest route out of a hard
    finding. Watched live. The advisory endpoint called ``atlas.get_advisory(...)``, a method
    AtlasClient never declared, so every request 500'd. Two rounds later the endpoint looked like
    this::

        return construct_unknown_advisory("ATLAS sensor mesh integration pending", lat, lon)

    The AttributeError was gone, the 500 was gone, module health was happier — and the product no
    longer did the one thing it exists to do. Sentinel's whole premise is "it reasons by invoking the
    ATLAS sensor-mesh capabilities over the AI-market protocol"; a Sentinel that answers UNKNOWN
    without asking anything is a placeholder with a landing page.

    Deleting a call is always the cheapest way to satisfy a finding about that call, so something has
    to notice. This does: capability ids declared anywhere in the product must be reachable from a
    request handler, or the product is not the product.
    """
    capability_files: dict[str, list[str]] = {}   # module stem -> capability ids
    router_files: list[Path] = []
    all_py: list[tuple[Path, str, str]] = []      # (path, rel, text)

    for file in iter_product_files(code_dir, "*.py"):
        rel = file.relative_to(code_dir).as_posix()
        if any(part in ("tests", "test", "migrations", "alembic") for part in Path(rel).parts):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_py.append((file, rel, text))
        ids = sorted(set(_CAPABILITY_ID_RE.findall(text)))
        if ids:
            capability_files[file.stem] = ids
        if "APIRouter(" in text or "@app.get(" in text or "@app.post(" in text:
            router_files.append(file)

    if not capability_files:
        return []

    findings: list[dict[str, Any]] = []
    for stem, ids in sorted(capability_files.items()):
        # Which classes in that module hold the capabilities?
        holder_names: set[str] = set()
        for file, rel, text in all_py:
            if file.stem != stem:
                continue
            holder_names.update(re.findall(r"^class\s+(\w+)", text, re.M))
        if not holder_names:
            continue

        reachable_from = ""
        for file, rel, text in all_py:
            if file in router_files or "APIRouter(" in text or "@app.get(" in text:
                if any(re.search(rf"\b{re.escape(name)}\s*\(", text) for name in holder_names):
                    reachable_from = rel
                    break
        if reachable_from:
            continue

        holder_rel = next((r for _f, r, _t in all_py if _f.stem == stem), stem)
        findings.append(
            {
                "code": "capability_never_invoked",
                "severity": "critical",
                "file": holder_rel,
                "capabilities": ids[:6],
                "detail": (
                    f"{holder_rel} declares the capabilities this product is built around "
                    f"({', '.join(ids[:4])}) and NO request handler constructs "
                    f"{' or '.join(sorted(holder_names)[:3])} — so nothing the product serves ever "
                    "invokes them. Deleting a call is the cheapest way to satisfy a finding about "
                    "that call, and that is what happened here: the advisory endpoint went from "
                    "crashing on a missing client method to returning a static placeholder, which "
                    "silenced the crash and removed the product's entire reason to exist. Restore "
                    "the invocation from the endpoint that needs it and fix the method name instead "
                    "— the client's real methods are the ones defined in "
                    f"{holder_rel}."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def find_orm_schema_never_created(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """SQLAlchemy models declared, and nothing ever creates their tables.

    The most expensive single defect of this product's night, and invisible to every gate that
    existed. The browser reported ``500`` on ``POST /api/auth/login``; the login handler was
    correct; four rounds edited it anyway. What actually happened:

    * ``models/user.py`` declares ``User`` on ``Base``;
    * ``main.py`` has no ``Base.metadata.create_all``, no startup hook, no Alembic;
    * so ``users`` does not exist, and every request that touches the database raises
      ``OperationalError: no such table: users`` — a 500.

    The demo journey passed throughout, because the login handler answers demo credentials from the
    environment *before* it queries anything. So the product looked authenticated end to end while
    its database had no schema at all.

    A finding that says "500 somewhere" is unexecutable. This one names the file, the missing call
    and the reason, and it is static — no browser, no server, no flake.
    """
    base_names: set[str] = set()
    model_files: dict[str, list[str]] = {}
    creates_schema: list[str] = []
    migration_files: list[str] = []
    runs_migrations: list[str] = []

    # Existing migrations are not a schema. Measured on the live product: backend/alembic/ held
    # 0001_initial.py, and nothing anywhere ran `alembic upgrade` — not the Dockerfile, not
    # docker-compose, not an entrypoint, and main.py had no startup hook at all. So the tables
    # described in the migration never existed at runtime, and every DB request was a 500.
    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if file.suffix in (".sh", ".yml", ".yaml", ".toml", ".cfg") or file.name in (
            "Dockerfile", "Makefile", "Procfile", "entrypoint.sh", "start.sh",
        ):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if re.search(r"alembic\s+upgrade", blob):
                runs_migrations.append(rel)
        if file.name == "alembic.ini" or "/versions/" in f"/{rel}":
            migration_files.append(rel)
            continue
        if file.suffix != ".py":
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r"(\w+)\s*=\s*declarative_base\s*\(", text):
            base_names.add(match.group(1))
        for match in re.finditer(r"class\s+(\w+)\s*\(\s*DeclarativeBase\s*\)", text):
            base_names.add(match.group(1))
        # Only a CALL counts. Importing alembic, or a module named alembic/env.py mentioning it,
        # creates no table — the previous version of this check accepted the mere word and so it
        # stayed silent on a product whose database had no schema at all.
        if re.search(r"\.metadata\.create_all\s*\(", text):
            creates_schema.append(rel)
        if re.search(r"command\.upgrade\s*\(|\brun_migrations\s*\(", text) and "/alembic/" not in f"/{rel}":
            runs_migrations.append(rel)
        tables = re.findall(r"__tablename__\s*=\s*[\"']([\w]+)[\"']", text)
        if tables:
            model_files[rel] = tables

    if not model_files or creates_schema or runs_migrations:
        return []
    if not base_names:
        return []

    # Where the fix belongs: the app entrypoint if there is one, else the module holding the engine.
    entry = ""
    for candidate in ("backend/app/main.py", "app/main.py", "main.py", "backend/main.py"):
        if (code_dir / candidate).is_file():
            entry = candidate
            break
    if not entry:
        for rel in sorted(model_files):
            entry = rel
            break

    all_tables = sorted({tbl for tables in model_files.values() for tbl in tables})
    findings = [
        {
            "code": "orm_schema_never_created",
            "severity": "critical",
            "file": entry,
            "tables": all_tables,
            "model_files": sorted(model_files),
            "migration_files": migration_files[:4],
            "detail": (
                f"{len(all_tables)} table(s) are declared on the ORM base "
                f"({', '.join(all_tables[:8])}) and NOTHING creates them at runtime: "
                + (
                    f"migrations exist ({', '.join(migration_files[:2])}) but no Dockerfile, "
                    "compose file, entrypoint or startup hook ever runs `alembic upgrade`"
                    if migration_files
                    else "no metadata.create_all call anywhere, and no migrations either"
                )
                + ". Every request that touches the database therefore raises OperationalError: "
                "no such table — which surfaces to the browser as a bare 500, and the login "
                "handler that gets blamed for it is usually correct. Fix it in "
                f"{entry}: add a startup hook that creates the schema before the app serves "
                "traffic — `Base.metadata.create_all(bind=engine)` after importing the models "
                "module (so the tables are registered on the metadata)"
                + (
                    ", or run the migrations there with alembic's command.upgrade"
                    if migration_files
                    else ""
                )
                + ". Do not edit the route handlers — they are not the defect."
            ),
        }
    ]
    return findings[:limit]


def find_duplicate_tablenames(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Model classes that declare a ``__tablename__`` already taken by another class."""
    by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            table = None
            extend_existing = False
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                if "__tablename__" in names and isinstance(stmt.value, ast.Constant):
                    if isinstance(stmt.value.value, str):
                        table = stmt.value.value
                if "__table_args__" in names:
                    # A dict or a tuple ending in a dict; either way the flag is a keyword.
                    for sub in ast.walk(stmt.value):
                        if isinstance(sub, ast.Constant) and sub.value == "extend_existing":
                            extend_existing = True
                        if isinstance(sub, ast.keyword) and sub.arg == "extend_existing":
                            extend_existing = True
            if table and not extend_existing:
                by_table[table].append(
                    {
                        "file": str(path.relative_to(code_dir)),
                        "line": node.lineno,
                        "model": node.name,
                    }
                )

    findings: list[dict[str, Any]] = []
    for table, decls in sorted(by_table.items()):
        if len(decls) < 2:
            continue
        where = "; ".join(f"{d['model']} in {d['file']}:{d['line']}" for d in decls[:4])
        keep = _canonical_home(table, decls)
        drop = [d for d in decls if d is not keep]
        findings.append(
            {
                "table": table,
                "file": keep["file"],
                "line": keep["line"],
                "models": [d["model"] for d in decls],
                "keep": keep["file"],
                "remove_from": [d["file"] for d in drop],
                "detail": (
                    f"{len(decls)} model classes declare __tablename__ = '{table}': {where}. "
                    "SQLAlchemy raises InvalidRequestError as soon as both are registered "
                    "against one MetaData, so the app does not start at all and every "
                    "endpoint is unreachable — no import check sees this because each module "
                    "is fine on its own. "
                    f"KEEP the declaration in {keep['file']} and DELETE "
                    + ", ".join(f"{d['model']} from {d['file']}" for d in drop)
                    + ", re-pointing whatever imported it at "
                    f"{keep['file']}. Do not paper over it with extend_existing=True, which "
                    "silently lets two definitions fight over the same columns."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


# The product calls OUR OWN economy with the wrong envelope, and nothing sees it. Every gate is
# green: the tree imports, the app boots, the endpoint answers 200 — with
# ``{"level": "UNKNOWN", "reason": "Insufficient sensor data"}`` on every request, because the
# mesh rejected each call on validation. The product's honesty policy (never CALM without data)
# turns a contract bug into a truthful-looking answer, which is the worst place to hide one.
#
# Found on a weather product whose entire purpose is mesh data:
#
#     data = {"capability": capability, "payload": payload}      # protocol wants capability_id/input
#     payload = {"bbox": [w, s, e, n]}                           # schema wants flat west/south/east/north
#     payload = {"max_radius_km": 100}                           # schema calls it max_km
#
# The manifest is the ground truth and it is fetched live, so this checks against what the mesh
# actually accepts today rather than a copy that drifts. Network failure means no opinion: an
# unreachable manifest must never fail a product's build.
_AIMARKET_ENVELOPE_REQUIRED = ("capability_id", "input")
_AIMARKET_ENVELOPE_WRONG = {
    "capability": "capability_id",
    "payload": "input",
    "cap": "capability_id",
    "params": "input",
    "arguments": "input",
    "body": "input",
}
# SKU lists that advertise what an agent uses, not the input of an invoke.
# Measured: Sentinel heartbeat.py posted a registry payload with
# capabilities_used=["atlas.situation.brief@v1", ...] and mesh_contract scored
# agent_id/sdk against the ATLAS input schema — three false findings that
# occupied the repair-scope Python slot while atlas_client.py was already correct.
_ADVERTISED_CAPABILITY_KEYS = (
    "capabilities_used",
    "advertised_capabilities",
    "capability_ids",
)


def _capability_id_is_advertised(src: str, match_start: int) -> bool:
    """True when the SKU sits in a declared-capabilities list, not an invoke call."""
    before = src[:match_start]
    open_br = before.rfind("[")
    if open_br < 0:
        return False
    if before.rfind("]") > open_br:
        return False
    head = before[max(0, open_br - 120) : open_br]
    return any(k in head for k in _ADVERTISED_CAPABILITY_KEYS)


def _fetch_manifest_schemas(base_urls: set[str]) -> dict[str, dict[str, Any]]:
    """``{capability_id: input_schema}`` from every mesh endpoint the product talks to."""
    import json as _json
    import urllib.error
    import urllib.request

    out: dict[str, dict[str, Any]] = {}
    for base in sorted(base_urls):
        for suffix in ("/ai-market/v2/manifest", "/.well-known/ai-market.json"):
            try:
                with urllib.request.urlopen(base.rstrip("/") + suffix, timeout=8) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                continue
            tools = data.get("tools") or data.get("capabilities") or []
            if not isinstance(tools, list):
                continue
            for tool in tools:
                if isinstance(tool, dict) and tool.get("capability_id"):
                    out[str(tool["capability_id"])] = tool.get("input_schema") or {}
            if out:
                break
    return out


def find_mesh_contract_violations(
    code_dir: Path, limit: int = MAX_FINDINGS
) -> list[dict[str, Any]]:
    """Outbound AI-market calls whose envelope or input does not match the live manifest."""
    findings: list[dict[str, Any]] = []
    bases: set[str] = set()
    files: list[tuple[Path, str, ast.AST]] = []

    for path in iter_product_files(code_dir, "*.py"):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A capability id is the actual signal. Requiring the words "ai-market" or
        # "capability" skipped a client that referenced SKUs and neither word — it worked on
        # the product that exposed this only by luck.
        if not re.search(r"[a-z0-9_]+\.[a-z0-9_.]+@v\d", src) and "ai-market" not in src:
            continue
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        files.append((path, src, tree))
        for m in re.finditer(r"https://[a-z0-9.\-]+\.modelmarket\.dev", src):
            bases.add(m.group(0))

    if not files:
        return findings

    # 1. Envelope keys — checkable without the network, so it is done first and always.
    for path, src, tree in files:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                k.value
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            wrong = {k: _AIMARKET_ENVELOPE_WRONG[k] for k in keys & set(_AIMARKET_ENVELOPE_WRONG)}
            # Only an envelope: it carries a capability-ish key and an argument-ish key, and
            # lacks the correct names. A dict that merely has "payload" in it is not one.
            if not wrong or "capability_id" in keys:
                continue
            if not ({"capability", "cap"} & keys):
                continue
            findings.append(
                {
                    "file": str(path.relative_to(code_dir)),
                    "line": node.lineno,
                    "kind": "envelope",
                    "detail": (
                        "AI-market invoke envelope uses "
                        + ", ".join(f"'{bad}' (should be '{good}')" for bad, good in sorted(wrong.items()))
                        + ". The protocol accepts only {capability_id, input}; anything else is "
                        "rejected on validation, so every call fails while the app still answers "
                        "200 with an empty result. Verify against "
                        "https://atlas.modelmarket.dev/ai-market/v2/manifest."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings

    # 2. Input shape against the live schema. No manifest reachable -> no opinion.
    schemas = _fetch_manifest_schemas(bases or {"https://atlas.modelmarket.dev"})
    if not schemas:
        return findings

    reported: set[tuple[str, str]] = set()
    for path, src, tree in files:
        for cap_match in re.finditer(r"""["']([a-z][a-z0-9_.]*\.[a-z0-9_.]+@v\d+)["']""", src):
            cap = cap_match.group(1)
            if _capability_id_is_advertised(src, cap_match.start()):
                continue
            schema = schemas.get(cap)
            if not schema:
                continue
            required = [r for r in (schema.get("required") or []) if isinstance(r, str)]
            props = set((schema.get("properties") or {}).keys())
            if not required and not props:
                continue
            line = src[: cap_match.start()].count("\n") + 1
            if (path.name, cap) in reported:
                # One finding per capability per file. The first version scanned a fixed window
                # backwards and re-reported each capability from an unrelated cost table further
                # down: six findings for three defects, which teaches people to skim the list.
                continue
            # Only the enclosing function. A window that crosses a `def` picks up someone
            # else's dict and invents fields the call never sent.
            head = src[: cap_match.start()]
            fn_start = max(head.rfind("\n    def "), head.rfind("\ndef "), head.rfind("\n    async def "))
            window = head[fn_start:] if fn_start != -1 else head[-900:]
            sent = set(re.findall(r"""["']([a-z_][a-z0-9_]*)["']\s*:""", window))
            if not sent:
                continue
            missing = [r for r in required if r not in sent]
            unknown = sorted(k for k in sent - props if k not in ("visitor_id", "capability_id", "input"))
            if not missing and not unknown:
                continue
            parts = []
            if missing:
                parts.append(f"required field(s) not sent: {', '.join(missing)}")
            if unknown:
                near = {
                    k: next((p for p in sorted(props) if p in k or k in p), None) for k in unknown
                }
                described = ", ".join(
                    f"'{k}'" + (f" (did you mean '{v}'?)" if v else "") for k, v in near.items()
                )
                parts.append(f"field(s) the schema does not have: {described}")
            reported.add((path.name, cap))
            findings.append(
                {
                    "file": str(path.relative_to(code_dir)),
                    "line": line,
                    "kind": "input_schema",
                    "capability": cap,
                    "detail": (
                        f"Input for {cap} does not match its published schema — "
                        + "; ".join(parts)
                        + f". The schema accepts: {', '.join(sorted(props))}. A rejected call "
                        "still leaves the endpoint answering 200 with no data, so this hides as "
                        "an honest 'no readings' rather than surfacing as an error."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings
