"""A rate-limited endpoint must declare `request`, and the finding has to say so.

Measured on a shipped product whose backend had just stopped importing at all:

    Exception: No "request" or "websocket" argument on function "get_advisory"

`@rate_limit(times=10, seconds=60)` is a two-level factory around `limiter.limit(...)`, and slowapi
reads the request out of the handler's own signature. Without that parameter the module never loads,
so every route in the app is dead — not just the decorated one.

The detector saw the defect and named the wrong remedy: it walked to the innermost function of the
factory, found `def decorator(func)`, and reported "whose wrapper requires func". A round following
that instruction would add a `func` parameter to an HTTP handler, which is worse than doing nothing.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_route_handlers_with_broken_injection

DEPS = '''from slowapi import Limiter
limiter = Limiter(key_func=lambda r: r.client.host)


def rate_limit(times: int, seconds: int):
    """Apply slowapi limiter to endpoint."""
    def decorator(func):
        return limiter.limit(f"{times}/{seconds}seconds")(func)
    return decorator
'''

ROUTER_BROKEN = '''from fastapi import APIRouter, Query
from ..deps import rate_limit

router = APIRouter()


@router.get("/advisory")
@rate_limit(times=10, seconds=60)
async def get_advisory(lat: float = Query(...)):
    return {"ok": True}
'''

ROUTER_FIXED = '''from fastapi import APIRouter, Query, Request
from ..deps import rate_limit

router = APIRouter()


@router.get("/advisory")
@rate_limit(times=10, seconds=60)
async def get_advisory(request: Request, lat: float = Query(...)):
    return {"ok": True}
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_the_finding_asks_for_request_not_func(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/deps.py": DEPS, "backend/app/routers/advisory.py": ROUTER_BROKEN},
    )
    found = find_route_handlers_with_broken_injection(code)
    assert len(found) == 1
    detail = found[0]["detail"]
    assert "request: Request" in detail
    assert "whose wrapper requires func" not in detail, "the old instruction was unfollowable"
    assert "every route in the app is dead" in detail, "the blast radius belongs in the finding"
    assert "do not remove the decorator" in detail


def test_declaring_request_satisfies_it(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/deps.py": DEPS, "backend/app/routers/advisory.py": ROUTER_FIXED},
    )
    assert find_route_handlers_with_broken_injection(code) == []


def test_a_factory_parameter_is_never_demanded_of_a_handler(tmp_path):
    """func/fn/handler name the decorated function itself — no handler declares them."""
    deps = '''def audit(label: str):
    def decorator(func):
        return func
    return decorator
'''
    router = '''from fastapi import APIRouter
from ..deps import audit

router = APIRouter()


@router.get("/x")
async def get_x():
    return {}
'''
    code = _tree(tmp_path / "code", {"backend/app/deps.py": deps, "backend/app/routers/x.py": router})
    assert find_route_handlers_with_broken_injection(code) == []
