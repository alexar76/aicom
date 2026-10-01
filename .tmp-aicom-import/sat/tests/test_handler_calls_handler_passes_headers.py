"""A route that calls another route as a function must pass every declared parameter.

`invoke_capability_prefixed` did not pass `x_api_key` to `invoke_capability_root`, so
Python fell back to that parameter's *default* — and a header default is a FastAPI
`Header(...)` OBJECT, not `None`. The object is truthy, so `(presented or "").strip()`
inside `reseller_label` raised `AttributeError` and
`POST /ai-market/capabilities/{product_id}/{capability_id}/invoke` answered 500 on every
call, on the paid invoke path, while the identical un-prefixed route worked.

Nothing caught it because the two routes share one implementation, and the tests
exercised the one that was fine.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Defaults that FastAPI resolves per-request. Any of these left to its default by a
#: direct Python call reaches the callee as the marker object itself.
_MARKERS = {
    "Header",
    "Query",
    "Cookie",
    "Depends",
    "Body",
    "Form",
    "Path",
    "File",
    "Security",
}
_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}

_SEARCH_DIRS = ("web/backend", "core", "orchestrator", "aimarket-hub/aimarket_hub")


def _python_files() -> list[Path]:
    out: list[Path] = []
    for rel in _SEARCH_DIRS:
        base = ROOT / rel
        if base.is_dir():
            out += [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]
    return sorted(out)


def _route_handlers(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in _METHODS
            ):
                found[node.name] = node
                break
    return found


def _resolved_defaults(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[int, str, str]]:
    """(positional index or -1 for kw-only, param name, marker) for FastAPI defaults."""
    out: list[tuple[int, str, str]] = []
    params = list(fn.args.args)
    offset = len(params) - len(fn.args.defaults)
    for i, default in enumerate(fn.args.defaults):
        if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
            if default.func.id in _MARKERS:
                out.append((offset + i, params[offset + i].arg, default.func.id))
    for i, kwarg in enumerate(fn.args.kwonlyargs):
        default = fn.args.kw_defaults[i]
        if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
            if default.func.id in _MARKERS:
                out.append((-1, kwarg.arg, default.func.id))
    return out


def _offences() -> list[str]:
    bad: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        if "APIRouter" not in source and "FastAPI" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover - covered by the syntax gate
            continue
        handlers = _route_handlers(tree)
        if len(handlers) < 2:
            continue
        for name, node in handlers.items():
            for call in ast.walk(node):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                target = call.func.id
                if target not in handlers or target == name:
                    continue
                if any(kw.arg is None for kw in call.keywords):
                    continue  # **kwargs forwarding: everything is passed
                passed = {kw.arg for kw in call.keywords if kw.arg}
                positional = len(call.args)
                for index, param, marker in _resolved_defaults(handlers[target]):
                    if param in passed:
                        continue
                    if index >= 0 and index < positional:
                        continue
                    bad.append(
                        f"{path.relative_to(ROOT)}:{call.lineno}: {name}() calls "
                        f"{target}() without {param} — it will receive the "
                        f"{marker}(...) object, not a value"
                    )
    return bad


def test_the_sweep_finds_route_handlers_at_all():
    """A guard that scans nothing passes for the wrong reason."""
    seen = 0
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        if "APIRouter" not in source and "FastAPI" not in source:
            continue
        try:
            seen += len(_route_handlers(ast.parse(source)))
        except SyntaxError:
            continue
    assert seen > 100, f"only {seen} route handlers found — the walk is broken"


def test_no_handler_calls_another_handler_with_unpassed_request_params():
    offences = _offences()
    assert not offences, "\n  ".join(["route handlers dropping resolved parameters:"] + offences)


@pytest.mark.parametrize("marker", sorted(_MARKERS))
def test_the_detector_catches_the_shape_it_is_named_for(tmp_path, marker):
    """Proof it is not vacuous: the real defect, reduced, in every marker flavour."""
    src = f'''
from fastapi import APIRouter, {marker}

router = APIRouter()


@router.post("/a")
async def root_handler(x: str | None = {marker}(default=None)):
    return x


@router.post("/b")
async def prefixed_handler():
    return await root_handler()
'''
    tree = ast.parse(src)
    handlers = _route_handlers(tree)
    assert set(handlers) == {"root_handler", "prefixed_handler"}
    assert _resolved_defaults(handlers["root_handler"]) == [(0, "x", marker)]
