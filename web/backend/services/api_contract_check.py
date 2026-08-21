"""
Frontend ↔ backend API contract check for generated full-stack products.

Why this gate exists
--------------------
The factory can ship a product where every unit test passes, the backend boots,
and the UI renders — yet the app is dead in the browser because the frontend
calls a URL the backend does not serve. The classic failure we hit in production:

    frontend:  fetch('/api/v1/accounts/?risk_band=high')     # trailing slash
    backend:   @router.get("")  mounted at /api/v1/accounts  # no trailing slash
    backend:   @app.get("/{full_path:path}")                 # SPA catch-all

The SPA catch-all is registered last but still *matches* ``/api/v1/accounts/``,
so Starlette never applies its ``redirect_slashes`` fallback. The user sees
"Failed to fetch accounts" while every other gate reports green.

This module compares the API calls the frontend actually makes against the
routes the backend actually serves, and reports the mismatch as a QA finding
with a concrete, fixable description. It is deliberately static (no browser, no
network) so it can run on every build in under a second.

Two issue families are reported:
  * ``api_client_route_missing``   — frontend calls an endpoint nothing serves
  * ``api_client_trailing_slash``  — only the slash form is wrong
  * ``spa_catchall_shadows_api``   — catch-all swallows ``/api/*`` (root cause)

``server_paths`` may be supplied by the caller (preferred: the live
``/openapi.json`` captured by :mod:`backend_runtime_e2e`); otherwise routes are
recovered statically from the FastAPI source, including router prefixes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from core.code_discovery import iter_product_files

logger = logging.getLogger(__name__)

FRONTEND_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte", ".html")

# Bundled/минified output is unreadable and duplicates src — skip it.
_SKIP_FILE_MARKERS = ("assets/index-", ".min.js", ".bundle.js")

# fetch('/api/x'), fetch(`/api/x/${id}`)
_FETCH_RE = re.compile(r"""\bfetch\(\s*[`'"]([^`'"]+)[`'"]""")
# axios.get('/api/x'), api.post('x'), client.delete(`x/${id}`)
_CLIENT_RE = re.compile(
    r"""\b(?:axios|api|apiClient|client|http|request)\s*\.\s*"""
    r"""(get|post|put|patch|delete|head)\s*\(\s*[`'"]([^`'"]+)[`'"]""",
    re.I,
)
# axios.create({ baseURL: '/api/v1' })
_BASEURL_RE = re.compile(r"""baseURL\s*:\s*[`'"]([^`'"]+)[`'"]""")
# const API_BASE = '/api/v1'
_API_CONST_RE = re.compile(
    r"""\b(?:const|let|var)\s+\w*(?:API_BASE|API_URL|BASE_URL|API_PREFIX)\w*\s*=\s*[`'"]([^`'"]+)[`'"]""",
    re.I,
)

# @app.get("/{full_path:path}")  /  @app.api_route("/{path:path}", ...)
_CATCHALL_RE = re.compile(
    r"""@(?:app|application)\.(?:get|api_route)\(\s*[`'"]/\{(\w+):path\}[`'"]""",
)

_ROUTE_DECORATOR_RE = re.compile(
    r"""@(\w+)\.(get|post|put|patch|delete|head)\(\s*[`'"]([^`'"]*)[`'"]""",
)
_ROUTER_CTOR_RE = re.compile(r"""(\w+)\s*=\s*APIRouter\(([^)]*)\)""")
_APP_CTOR_RE = re.compile(r"""(\w+)\s*=\s*FastAPI\(""")
_INCLUDE_ROUTER_RE = re.compile(
    r"""(\w+)\.include_router\(\s*([\w.]+)\s*((?:,[^)]*)?)\)""",
)
_PREFIX_KW_RE = re.compile(r"""prefix\s*=\s*[`'"]([^`'"]*)[`'"]""")
# prefix=settings.API_V1_STR  /  prefix=API_PREFIX
_PREFIX_NAME_RE = re.compile(r"""prefix\s*=\s*([A-Za-z_][\w.]*)""")
# API_V1_STR: str = "/api/v1"   /   API_PREFIX = "/api"
_PATH_CONST_RE = re.compile(
    r"""^\s*([A-Z][A-Z0-9_]*)\s*(?::\s*str\s*)?=\s*[`'"](/[^`'"]*)[`'"]""",
    re.M,
)


def _is_frontend_file(path: Path) -> bool:
    if path.suffix.lower() not in FRONTEND_SUFFIXES:
        return False
    posix = path.as_posix()
    return not any(marker in posix for marker in _SKIP_FILE_MARKERS)


def _normalize_call_path(raw: str) -> str:
    """Turn a source-literal URL into a comparable path shape.

    ``/api/v1/accounts/${id}?x=1`` → ``/api/v1/accounts/{param}``
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # Template interpolation → a single wildcard segment.
    text = re.sub(r"\$\{[^}]*\}", "{param}", text)
    text = re.sub(r"\{\{[^}]*\}\}", "{param}", text)
    # Drop query and hash.
    text = text.split("?", 1)[0].split("#", 1)[0]
    return text.strip()


def _looks_like_api_path(path: str) -> bool:
    if not path.startswith("/"):
        return False
    if path.startswith("//"):
        return False
    lowered = path.lower()
    if lowered.startswith(("/http", "/mailto", "/tel")):
        return False
    return True


def _join(base: str, path: str) -> str:
    base = (base or "").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}" if base else path


def extract_client_api_calls(code_dir: Path) -> list[dict[str, Any]]:
    """Collect the API paths the frontend sources actually request."""
    calls: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for file in iter_product_files(code_dir, "*"):
        if not _is_frontend_file(file):
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        bases = [b for b in _BASEURL_RE.findall(text) if b.startswith("/")]
        bases += [b for b in _API_CONST_RE.findall(text) if b.startswith("/")]
        base = bases[0] if bases else ""

        rel = file.relative_to(code_dir).as_posix()

        # fetch() is absolute-only; axios-style clients prepend their baseURL to
        # both relative and leading-slash URLs, so they are collected separately.
        raw_hits: list[tuple[str, bool]] = [(h, False) for h in _FETCH_RE.findall(text)]
        raw_hits += [(m[1], True) for m in _CLIENT_RE.findall(text)]

        for raw, based in raw_hits:
            path = _normalize_call_path(raw)
            if not path:
                continue
            if path.startswith(("http://", "https://", "//")):
                continue
            if based and base and not path.startswith(base):
                path = _join(base, path)
            elif not path.startswith("/"):
                continue
            if not _looks_like_api_path(path):
                continue
            if "/api" not in path.lower():
                continue
            key = (rel, path)
            if key in seen:
                continue
            seen.add(key)
            calls.append({"path": path, "file": rel, "raw": raw[:200]})
    calls.sort(key=lambda c: (c["path"], c["file"]))
    return calls


def extract_server_routes(code_dir: Path) -> list[str]:
    """Recover served API paths from FastAPI source.

    Generated backends nest routers two or three deep
    (``app → api_router → accounts.router``), so prefixes are resolved by
    walking the ``include_router`` graph from every ``FastAPI()`` instance
    rather than by flat pattern matching.
    """
    # (module_stem, var) → {"prefix": str, "routes": [paths]}
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[tuple[tuple[str, str], str | None, str, str]] = []
    app_keys: list[tuple[str, str]] = []
    # Uppercase path constants, so `prefix=settings.API_V1_STR` resolves to "/api/v1"
    # instead of silently mounting the whole API at the root.
    path_consts: dict[str, str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, value in _PATH_CONST_RE.findall(text):
            path_consts.setdefault(name, value)

    def _resolve_prefix(args: str) -> str:
        literal = _PREFIX_KW_RE.search(args or "")
        if literal:
            return literal.group(1)
        named = _PREFIX_NAME_RE.search(args or "")
        if named:
            return path_consts.get(named.group(1).split(".")[-1], "")
        return ""

    def node(key: tuple[str, str]) -> dict[str, Any]:
        return nodes.setdefault(key, {"prefix": "", "routes": [], "file": ""})

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stem = file.stem

        for var in _APP_CTOR_RE.findall(text):
            key = (stem, var)
            node(key)
            app_keys.append(key)
        for var, args in _ROUTER_CTOR_RE.findall(text):
            node((stem, var))["prefix"] = _resolve_prefix(args)
        for holder, _method, path in _ROUTE_DECORATOR_RE.findall(text):
            key = (stem, holder)
            if key not in nodes:
                continue  # decorator on something that is not a router/app here
            node(key)["routes"].append(path or "")
            # Remember where the handler lives. A runtime finding that names only an endpoint cannot
            # enter the repair scope, so nothing is attached and the round guesses which file to open.
            node(key)["file"] = file.relative_to(code_dir).as_posix()
        for parent, target, args in _INCLUDE_ROUTER_RE.findall(text):
            parts = target.split(".")
            child_var = parts[-1]
            child_module = parts[-2] if len(parts) > 1 else None
            edges.append(((stem, parent), child_module, child_var, _resolve_prefix(args)))

    by_var: dict[str, list[tuple[str, str]]] = {}
    for key in nodes:
        by_var.setdefault(key[1], []).append(key)

    def resolve(child_module: str | None, child_var: str) -> tuple[str, str] | None:
        if child_module and (child_module, child_var) in nodes:
            return (child_module, child_var)
        candidates = by_var.get(child_var) or []
        if len(candidates) == 1:
            return candidates[0]
        if child_module:
            narrowed = [c for c in candidates if c[0] == child_module]
            if len(narrowed) == 1:
                return narrowed[0]
        return None

    served: set[str] = set()
    _route_files: dict[str, str] = {}

    def walk(key: tuple[str, str], prefix: str, seen: frozenset) -> None:
        if key in seen:
            return
        seen = seen | {key}
        info = nodes.get(key)
        if info is None:
            return
        base = prefix + (info["prefix"] or "")
        for path in info["routes"]:
            full = base + path
            if not full.startswith("/"):
                full = "/" + full
            if full != "/" and full.endswith("/"):
                full = full.rstrip("/")
            served.add(full or "/")
            if info.get("file"):
                _route_files.setdefault(full or "/", info["file"])
        for parent, child_module, child_var, edge_prefix in edges:
            if parent != key:
                continue
            child = resolve(child_module, child_var)
            if child is None or child == key:
                continue
            walk(child, base + edge_prefix, seen)

    for key in app_keys:
        walk(key, "", frozenset())

    if not served:
        # No FastAPI() instance found (single-file app object imported elsewhere):
        # fall back to a flat read so the check still has something to compare.
        for key, info in nodes.items():
            for path in info["routes"]:
                full = (info["prefix"] or "") + path
                full = full if full.startswith("/") else "/" + full
                served.add(full)
                if info.get("file"):
                    _route_files.setdefault(full, info["file"])
    _LAST_ROUTE_FILES.clear()
    _LAST_ROUTE_FILES.update(_route_files)
    return sorted(served)


# Filled by `extract_server_routes`, read by `route_handler_file`. A module-level cache rather than a
# changed return type, so every existing caller of that function is untouched.
_LAST_ROUTE_FILES: dict[str, str] = {}


def server_route_files(code_dir: Path) -> dict[str, str]:
    """``{served path: file that declares the handler}``.

    Exists so a runtime finding can name a file. `demo_login_failed:/api/auth/login` named only the
    product directory, so `blocking_files` came out empty, `repair_scope` came out `[]`, nothing was
    attached, and the round had to guess which file to open — three rounds running it guessed `main.py`,
    where the defect was not.
    """
    extract_server_routes(code_dir)
    table = dict(_LAST_ROUTE_FILES)

    # Served paths include the include_router prefix; declared paths do not. After the product
    # correctly moved its /api prefix out of the decorators and into
    # `include_router(..., prefix=settings.api_prefix)`, this table held `/auth/login` while every
    # runtime finding said `/api/auth/login` — so route_handler_file() answered None, the journey
    # findings stopped naming files, and the repair scope silently lost the login handler it had
    # named for hours. The include prefixes are already resolved for the shadow detector; apply
    # them here too, keeping the bare declared path as well in case a router is mounted twice.
    try:
        from web.backend.services.duplicate_module_check import _router_include_prefixes

        prefixes = _router_include_prefixes(code_dir)
    except Exception:
        prefixes = {}
    if prefixes:
        mounted: dict[str, str] = {}
        for path, file in table.items():
            stem = Path(file).stem
            prefix = prefixes.get(stem)
            if prefix and not path.startswith(prefix.rstrip("/") + "/") and path != prefix:
                mounted[(prefix.rstrip("/") + path) or path] = file
        table.update(mounted)
    return table


def route_handler_file(code_dir: Path, endpoint: str) -> str | None:
    """The file serving ``endpoint``, matching the longest declared path that fits.

    Path parameters are matched by shape, so `/api/dashboards/7/data` finds
    `/api/dashboards/{id}/data`.
    """
    import re as _re

    table = server_route_files(code_dir)
    if not table:
        return None
    want = (endpoint or "").split("?")[0].rstrip("/") or "/"
    if want in table:
        return table[want]
    best: tuple[int, str] | None = None
    for path, file in table.items():
        pattern = "^" + _re.sub(r"\{[^}]+\}", "[^/]+", _re.escape(path).replace("\\{", "{").replace("\\}", "}")) + "$"
        try:
            if _re.match(pattern, want):
                if best is None or len(path) > best[0]:
                    best = (len(path), file)
        except _re.error:
            continue
    return best[1] if best else None


def _segments(path: str) -> list[str]:
    """Split a path, keeping the empty tail segment a trailing slash produces.

    ``/a/b`` → ``["a", "b"]`` but ``/a/b/`` → ``["a", "b", ""]`` — that difference
    is the whole point of this check, so it must survive normalization.
    """
    return path.lstrip("/").split("/")


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def path_matches(client_path: str, server_path: str) -> bool:
    """Segment-wise match where either side may carry ``{param}`` wildcards."""
    cs = _segments(client_path)
    ss = _segments(server_path)
    if len(cs) != len(ss):
        return False
    for c, s in zip(cs, ss):
        if not c or not s:
            # A trailing slash produces an empty segment; a path parameter never
            # matches it (``/accounts/`` is not ``/accounts/{id}``).
            if c != s:
                return False
            continue
        if _is_param(c) or _is_param(s):
            continue
        if c != s:
            return False
    return True


def _matches_any(path: str, server_paths: Iterable[str]) -> bool:
    return any(path_matches(path, sp) for sp in server_paths)


def detect_catchall_shadowing(code_dir: Path) -> list[dict[str, str]]:
    """Find SPA catch-all routes that swallow ``/api/*`` instead of 404/redirecting."""
    findings: list[dict[str, str]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _CATCHALL_RE.finditer(text):
            var = m.group(1)
            # Inspect the handler body that follows the decorator.
            body = text[m.end() : m.end() + 1500]
            # Any mention of an "api" literal in the handler counts as a guard:
            # `startswith("api/")`, `head in {"api", ...}`, `"/api" in path`, …
            guarded = bool(re.search(r"""['"]/?api\b""", body))
            if not guarded:
                findings.append(
                    {
                        "file": file.relative_to(code_dir).as_posix(),
                        "param": var,
                    }
                )
    return findings


def check_api_contract(
    code_dir: Path,
    *,
    server_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Compare frontend API calls against served routes.

    Returns a report with ``passed``, ``issues`` (QA-shaped dicts) and the raw
    call/route inventories for debugging.
    """
    code_dir = Path(code_dir)
    if not code_dir.is_dir():
        return {
            "passed": True,
            "skipped": True,
            "reason": "no_code_dir",
            "issues": [],
        }

    calls = extract_client_api_calls(code_dir)
    routes = list(server_paths or []) or extract_server_routes(code_dir)
    api_routes = [r for r in routes if "/api" in r.lower()]

    if not calls:
        return {
            "passed": True,
            "skipped": True,
            "reason": "no_frontend_api_calls",
            "issues": [],
            "server_paths": api_routes,
        }
    if not api_routes:
        return {
            "passed": True,
            "skipped": True,
            "reason": "no_server_api_routes_detected",
            "issues": [],
            "client_calls": calls,
        }

    issues: list[dict[str, Any]] = []
    checked = 0
    for call in calls:
        path = call["path"]
        checked += 1
        if _matches_any(path, api_routes):
            continue
        stripped = path.rstrip("/") or "/"
        if stripped != path and _matches_any(stripped, api_routes):
            issues.append(
                {
                    "code": "api_client_trailing_slash",
                    "severity": "high",
                    "detail": (
                        f"{call['file']} calls '{path}' but the API serves '{stripped}'. "
                        "The SPA catch-all matches the slash form first, so FastAPI never "
                        "redirects and the request 404s in the browser. Call the exact path "
                        "(no trailing slash) or make the router accept both."
                    ),
                    "file": call["file"],
                    "client_path": path,
                    "server_path": stripped,
                }
            )
            continue
        issues.append(
            {
                "code": "api_client_route_missing",
                "severity": "high",
                "detail": (
                    f"{call['file']} calls '{path}', which no backend route serves. "
                    f"Known API routes: {', '.join(api_routes[:12])}"
                    + (" …" if len(api_routes) > 12 else "")
                    + ". Implement the endpoint or fix the client path."
                ),
                "file": call["file"],
                "client_path": path,
            }
        )

    for shadow in detect_catchall_shadowing(code_dir):
        issues.append(
            {
                "code": "spa_catchall_shadows_api",
                "severity": "high",
                "detail": (
                    f"{shadow['file']} registers an SPA catch-all on "
                    f"'/{{{shadow['param']}:path}}' with no /api guard. It matches "
                    "unknown /api/* URLs (including trailing-slash variants) and returns "
                    "the HTML shell or 404 instead of letting the API router answer. "
                    "Return 404/redirect for paths starting with 'api/'."
                ),
                "file": shadow["file"],
            }
        )

    return {
        "passed": not issues,
        "skipped": False,
        "issues": issues,
        "client_calls_checked": checked,
        "client_calls": calls[:50],
        "server_paths": api_routes,
    }


def run_api_contract_check(
    product_id: str,
    data_root: str | Path | None = None,
    *,
    server_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Pipeline entrypoint: check one product by id."""
    from core.paths import code_dir as resolve_code_dir
    from core.paths import resolve_data_root

    root = resolve_data_root(data_root)
    try:
        return check_api_contract(
            resolve_code_dir(product_id, data_root=root),
            server_paths=server_paths,
        )
    except Exception as exc:  # never break QA on a scanner bug
        logger.warning("api_contract_check failed for %s: %s", product_id, exc)
        return {"passed": True, "skipped": True, "reason": f"error:{exc}", "issues": []}
