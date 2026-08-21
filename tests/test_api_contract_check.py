"""Frontend↔backend API contract gate: catches the calls a generated SPA gets wrong."""

from pathlib import Path

from web.backend.services.api_contract_check import (
    check_api_contract,
    detect_catchall_shadowing,
    extract_client_api_calls,
    extract_server_routes,
    path_matches,
)

BACKEND_MAIN = '''
from fastapi import FastAPI
from app.api import accounts

app = FastAPI()
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["accounts"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/{full_path:path}")
def spa(full_path: str):
    return index_response()
'''

BACKEND_ROUTER = '''
from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_accounts():
    return []


@router.get("/{account_id}")
def get_account(account_id: str):
    return {}
'''


def _product(tmp_path: Path, frontend: str, *, main: str = BACKEND_MAIN) -> Path:
    root = tmp_path / "code" / "prod-test"
    (root / "backend" / "app" / "api").mkdir(parents=True)
    (root / "frontend" / "src" / "pages").mkdir(parents=True)
    (root / "backend" / "main.py").write_text(main, encoding="utf-8")
    (root / "backend" / "app" / "api" / "accounts.py").write_text(BACKEND_ROUTER, encoding="utf-8")
    (root / "frontend" / "src" / "pages" / "Dashboard.tsx").write_text(frontend, encoding="utf-8")
    return root


def test_extract_server_routes_resolves_include_router_prefix(tmp_path):
    root = _product(tmp_path, "const x = 1")
    routes = extract_server_routes(root)
    assert "/api/v1/accounts" in routes
    assert "/api/v1/accounts/{account_id}" in routes
    assert "/api/health" in routes


def test_extract_client_calls_normalizes_query_and_template(tmp_path):
    root = _product(
        tmp_path,
        """
        const r = await fetch(`/api/v1/accounts/?risk=${risk}`);
        const d = await fetch(`/api/v1/accounts/${id}`);
        """,
    )
    paths = {c["path"] for c in extract_client_api_calls(root)}
    assert "/api/v1/accounts/" in paths
    assert "/api/v1/accounts/{param}" in paths


def test_trailing_slash_call_is_reported(tmp_path):
    """The production bug: SPA asks for /accounts/, API serves /accounts."""
    root = _product(tmp_path, "fetch('/api/v1/accounts/?risk_band=high')")
    report = check_api_contract(root)
    codes = {i["code"] for i in report["issues"]}
    assert report["passed"] is False
    assert "api_client_trailing_slash" in codes


def test_exact_call_passes(tmp_path):
    root = _product(
        tmp_path,
        """
        fetch('/api/v1/accounts?risk_band=high')
        fetch(`/api/v1/accounts/${id}`)
        fetch('/api/health')
        """,
        main=BACKEND_MAIN.replace(
            "def spa(full_path: str):",
            'def spa(full_path: str):\n    if full_path.startswith("api/"):\n        raise HTTPException(404)',
        ),
    )
    report = check_api_contract(root)
    assert report["passed"] is True, report["issues"]


def test_missing_route_is_reported(tmp_path):
    root = _product(tmp_path, "fetch('/api/v1/opportunities')")
    report = check_api_contract(root)
    assert {i["code"] for i in report["issues"]} >= {"api_client_route_missing"}


def test_unguarded_catchall_is_reported(tmp_path):
    root = _product(tmp_path, "fetch('/api/v1/accounts')")
    assert detect_catchall_shadowing(root)
    report = check_api_contract(root)
    assert {i["code"] for i in report["issues"]} == {"spa_catchall_shadows_api"}


def test_guarded_catchall_is_clean(tmp_path):
    guarded = BACKEND_MAIN.replace(
        "def spa(full_path: str):",
        'def spa(full_path: str):\n    if full_path.startswith("api/"):\n        raise HTTPException(status_code=404)',
    )
    root = _product(tmp_path, "fetch('/api/v1/accounts')", main=guarded)
    assert detect_catchall_shadowing(root) == []


def test_axios_baseurl_is_applied(tmp_path):
    root = _product(
        tmp_path,
        """
        const api = axios.create({ baseURL: '/api/v1' });
        api.get('/accounts');
        api.get('/missing-thing');
        """,
    )
    report = check_api_contract(root, server_paths=["/api/v1/accounts"])
    codes = {(i["code"], i.get("client_path")) for i in report["issues"]}
    assert ("api_client_route_missing", "/api/v1/missing-thing") in codes
    assert not any(c[1] == "/api/v1/accounts" for c in codes)


def test_path_matches_param_segments():
    assert path_matches("/api/v1/accounts/{param}", "/api/v1/accounts/{account_id}")
    assert path_matches("/api/v1/accounts/abc", "/api/v1/accounts/{account_id}")
    assert not path_matches("/api/v1/accounts", "/api/v1/accounts/{account_id}")


def test_skipped_when_no_frontend_calls(tmp_path):
    root = _product(tmp_path, "const greeting = 'hello'")
    report = check_api_contract(root)
    assert report["skipped"] is True
    assert report["passed"] is True
