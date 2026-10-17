"""FastAPI routing: doubled router prefixes, dead path rewrites, API routes shadowing the SPA,
broken handler injection, sync wrappers over async handlers.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import MAX_FINDINGS


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
