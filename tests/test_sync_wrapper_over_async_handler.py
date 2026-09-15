"""A sync wrapper over an async handler answers every request with a coroutine object.

The last runtime defect of a very long repair, and it hid behind a traceback that blamed the wrong
thing. The product's own rate-limit decorator built a synchronous wrapper around
`async def get_advisory(...)`, so FastAPI called it, got a coroutine back, and reported:

    ResponseValidationError: {'type': 'model_attributes_type', 'loc': ('response',),
      'input': <coroutine object get_advisory ...>}
    RuntimeWarning: coroutine 'get_advisory' was never awaited

Every request to the product's main endpoint answered 500. The message names the response model, so
three rounds went to advisory.py and to the schema — and the handler was correct all along; the defect
was in deps.py.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_sync_wrapper_over_async_handler

SYNC_FACTORY = '''from fastapi import Request


def rate_limit(times: int, seconds: int):
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
'''

ASYNC_FACTORY = '''import functools


def rate_limit(times: int, seconds: int):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator
'''

ROUTER = '''from fastapi import APIRouter
from ..deps import rate_limit

router = APIRouter()


@router.get("/advisory")
@rate_limit(times=10, seconds=60)
async def get_advisory(lat: float, lon: float):
    return {"ok": True}
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_the_live_shape_is_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/deps.py": SYNC_FACTORY, "backend/app/routers/advisory.py": ROUTER},
    )
    found = find_sync_wrapper_over_async_handler(code)
    assert len(found) == 1
    f = found[0]
    assert f["file"].endswith("deps.py"), "the fix belongs where the wrapper is, not in the router"
    assert f["handler"] == "get_advisory"
    assert "never awaited" in f["detail"]
    assert "do not edit it" in f["detail"] and "response model" in f["detail"]
    assert "await func" in f["detail"], "the finding must state the fix"


def test_an_async_wrapper_is_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/deps.py": ASYNC_FACTORY, "backend/app/routers/advisory.py": ROUTER},
    )
    assert find_sync_wrapper_over_async_handler(code) == []


def test_a_sync_handler_with_a_sync_wrapper_is_fine(tmp_path):
    sync_router = ROUTER.replace("async def get_advisory", "def get_advisory")
    code = _tree(
        tmp_path / "code",
        {"backend/app/deps.py": SYNC_FACTORY, "backend/app/routers/advisory.py": sync_router},
    )
    assert find_sync_wrapper_over_async_handler(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not sync_wrappers" in passed
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "find_sync_wrapper_over_async_handler(code_root, limit=200)" in score
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"sync_wrapper_over_async_handler"' in qa[: qa.index("# Deletions next")]
