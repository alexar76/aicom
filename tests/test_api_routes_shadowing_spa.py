"""A JSON route outside /api shadows the SPA catch-all, and it wore three costumes all night.

FastAPI matches the route table before the catch-all, so a browser *navigating* to such a path never
reaches the app shell: `/login` rendered as raw JSON; `/` as API JSON; and `GET /dashboards` as an
unexplained 405 — the bare route serves only POST, so the path matched, the method did not, and the
console said "Failed to load resource: 405" with no path at all. Two rounds went guessing in App.tsx.

The live sweep also surfaced a whole hidden file — `analytics_top.py`, a duplicate analytics router
mounted at the root — which no finding of the night had ever named.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_api_routes_shadowing_spa

CATCHALL = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n"
    '@app.get("/{full_path:path}")\n'
    "def spa(full_path: str):\n    return None\n"
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_live_shapes_are_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": CATCHALL,
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
            "backend/app/routers/analytics_top.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.post("/dashboards")\ndef create():\n    return {}\n'
            ),
            "backend/app/routers/analytics.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/api/analytics")\n'
                '@router.post("/dashboards")\ndef create2():\n    return {}\n'
            ),
        },
    )
    found = find_api_routes_shadowing_spa(code)
    paths = {(f["method"], f["path"]) for f in found}
    assert ("POST", "/login") in paths
    assert ("POST", "/dashboards") in paths
    twin = next(f for f in found if f["path"] == "/dashboards")
    assert "DELETE this bare twin" in twin["detail"], (
        "when the resource already lives under /api, moving the copy would collide with it"
    )
    login = next(f for f in found if f["path"] == "/login")
    assert "MOVE it under /api" in login["detail"]
    assert "Do not touch the catch-all" in login["detail"]


def test_routes_under_api_are_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": CATCHALL,
            "backend/app/routers/ok.py": (
                "from fastapi import APIRouter\n"
                'router = APIRouter(prefix="/api/things")\n'
                '@router.post("/")\ndef create():\n    return {}\n'
            ),
        },
    )
    assert find_api_routes_shadowing_spa(code) == []


def test_an_api_only_product_is_never_flagged(tmp_path):
    """No SPA catch-all means no shadowing — an API may mount wherever it likes."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/auth.py": (
                "from fastapi import APIRouter\nrouter = APIRouter()\n"
                '@router.post("/login")\ndef login():\n    return {}\n'
            ),
        },
    )
    assert find_api_routes_shadowing_spa(code) == []


def test_health_and_root_are_exempt(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": CATCHALL
            + '@app.get("/healthz")\ndef health():\n    return {"ok": True}\n',
        },
    )
    assert find_api_routes_shadowing_spa(code) == []


def test_it_is_wired_everywhere():
    root = Path(__file__).resolve().parents[1]
    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not spa_shadows" in passed_expr
    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "5 * len(find_api_routes_shadowing_spa(code_root, limit=200))" in score
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert '"api_route_shadows_spa"' in qa[: qa.index("# Deletions next")]


def test_an_include_prefix_counts_as_a_mount(tmp_path):
    """Two detectors were about to fight each other over the same five files.

    `@router.get("/advisory")` in a module mounted with `prefix=settings.api_prefix` is served at
    /api/advisory — correct. Read on its own, the decorator looks like a route outside /api. Measured
    live: the round that correctly stripped /api from five routers immediately earned two shadow
    findings for doing so, and the next round would have put them back. Oscillation costs rounds and
    ends where it started.
    """
    code = tmp_path / "code"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "config.py").write_text(
        'class Settings:\n    api_prefix: str = "/api"\n', encoding="utf-8"
    )
    (code / "backend" / "app" / "main.py").write_text(
        "app.include_router(advisory.router, prefix=settings.api_prefix)\n\n\n"
        '@app.get("/{full_path:path}")\nasync def spa(full_path: str):\n    return 1\n',
        encoding="utf-8",
    )
    (code / "backend" / "app" / "routers" / "advisory.py").write_text(
        'router = APIRouter()\n\n\n@router.get("/advisory")\ndef advisory():\n    return {}\n',
        encoding="utf-8",
    )
    assert find_api_routes_shadowing_spa(code) == []


def test_a_route_genuinely_outside_any_mount_is_still_flagged(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "main.py").write_text(
        'from fastapi import FastAPI\napp = FastAPI()\n\n\n'
        '@app.get("/dashboards")\ndef dashboards():\n    return {}\n\n\n'
        '@app.get("/{full_path:path}")\nasync def spa(full_path: str):\n    return 1\n',
        encoding="utf-8",
    )
    found = find_api_routes_shadowing_spa(code)
    assert [f["path"] for f in found] == ["/dashboards"], found
