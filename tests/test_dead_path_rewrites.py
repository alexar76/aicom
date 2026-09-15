"""ASGI middleware rewriting a live path onto a dead one — the saboteur behind the immortal 405.

    class PathRewriteMiddleware:
        if path == "/api/auth/login":
            scope["path"] = "/login"        # /login no longer exists

A compatibility shim from when login lived at `/login`. The routes moved; the shim stayed; now it
rewrites the CORRECT path onto a dead one, where the GET-only SPA catch-all answers 405 to the login
POST. Every observable symptom pointed at the auth router — file attribution, OpenAPI, the static route
table all said the endpoint exists, because it does; requests just never reach it. Rounds edited
auth.py in vain for hours, and the ground truth came only from booting the app and asking it.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_dead_path_rewrites

AUTH = (
    "from fastapi import APIRouter\n"
    'router = APIRouter(prefix="/api/auth")\n'
    '@router.post("/login")\ndef login():\n    return {}\n'
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _main(rewrite_to: str) -> str:
    return (
        "from fastapi import FastAPI\n"
        "from app.routers import auth\n"
        "app = FastAPI()\n"
        "class PathRewriteMiddleware:\n"
        "    def __init__(self, app):\n"
        "        self.app = app\n"
        "    async def __call__(self, scope, receive, send):\n"
        '        if scope["type"] == "http":\n'
        '            if scope.get("path") == "/api/auth/login":\n'
        f'                scope["path"] = "{rewrite_to}"\n'
        "        await self.app(scope, receive, send)\n"
        "app.add_middleware(PathRewriteMiddleware)\n"
        "app.include_router(auth.router)\n"
    )


def test_the_live_saboteur_is_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/main.py": _main("/login"), "backend/app/routers/auth.py": AUTH},
    )
    found = find_dead_path_rewrites(code)
    assert len(found) == 1, found
    f = found[0]
    assert f["source"] == "/api/auth/login" and f["target"] == "/login"
    assert f["severity"] == "critical"
    assert "DELETE the rewrite" in f["detail"]
    assert "Do not edit the router" in f["detail"], (
        "without this the rounds keep editing the innocent file, as they did for hours"
    )


def test_an_alias_between_a_dead_source_and_a_live_target_is_legitimate(tmp_path):
    """Old bookmarked /login forwarding to the real route is a feature, not a defect."""
    main = _main("/api/auth/login").replace('== "/api/auth/login"', '== "/login"')
    code = _tree(
        tmp_path / "code",
        {"backend/app/main.py": main, "backend/app/routers/auth.py": AUTH},
    )
    assert find_dead_path_rewrites(code) == []


def test_a_product_without_rewrites_is_silent(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "backend/app/routers/auth.py": AUTH,
        },
    )
    assert find_dead_path_rewrites(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not dead_rewrites" in passed_expr
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "10 * len(find_dead_path_rewrites(code_root, limit=200))" in score
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"dead_path_rewrite"' in qa[: qa.index("# Deletions next")]
