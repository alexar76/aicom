"""CSRF middleware — double-submit cookie for admin session cookies."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.middleware.csrf import CSRF_COOKIE, CSRF_HEADER, csrf_protect_middleware


@pytest.fixture
def csrf_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(csrf_protect_middleware)

    @app.post("/api/admin/auth/login")
    async def login():
        return {"ok": True}

    @app.post("/api/admin/protected")
    async def protected():
        return {"ok": True}

    @app.post("/api/sandbox/start")
    async def sandbox_start():
        return {"ok": True}

    @app.post("/api/uni/treasury/audit")
    async def uni_audit():
        return {"ok": True}

    @app.get("/api/admin/protected")
    async def protected_get():
        return {"ok": True}

    return app


def test_csrf_blocks_cookie_session_without_header(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("access_token", "fake-jwt")
    client.cookies.set(CSRF_COOKIE, "tok")
    r = client.post("/api/admin/protected")
    assert r.status_code == 403


def test_csrf_allows_matching_token(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("access_token", "fake-jwt")
    client.cookies.set(CSRF_COOKIE, "matching-token")
    r = client.post("/api/admin/protected", headers={CSRF_HEADER: "matching-token"})
    assert r.status_code == 200


def test_csrf_skips_when_no_session_cookie(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    r = client.post("/api/admin/protected", headers={"Authorization": "Bearer only-bearer"})
    assert r.status_code == 200


def test_csrf_login_exempt(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("access_token", "fake-jwt")
    r = client.post("/api/admin/auth/login")
    assert r.status_code == 200


def test_csrf_get_unaffected(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("access_token", "fake-jwt")
    r = client.get("/api/admin/protected")
    assert r.status_code == 200


def test_aif_admin_session_cookie_is_covered(csrf_app: FastAPI) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("aif_admin_session", "fake-jwt")
    client.cookies.set(CSRF_COOKIE, "tok")
    assert client.post("/api/admin/protected").status_code == 403


@pytest.mark.parametrize("path", ["/api/sandbox/start", "/api/uni/treasury/audit"])
def test_cookie_authenticated_admin_routes_are_covered_regardless_of_prefix(
    csrf_app: FastAPI, path: str
) -> None:
    client = TestClient(csrf_app)
    client.cookies.set("aif_admin_session", "fake-jwt")
    assert client.post(path).status_code == 403

    client.cookies.set(CSRF_COOKIE, "matching-token")
    assert client.post(path, headers={CSRF_HEADER: "matching-token"}).status_code == 200


# ── 2026-08 audit: /api/v1 was a CSRF bypass ─────────────────────────────────
# ApiVersionMiddleware is added FIRST in web/backend/main.py, which in Starlette makes it
# the INNERMOST layer — so csrf_protect_middleware saw "/api/v1/admin/settings", matched
# none of its "/api/admin" prefixes, waved the request through, and only then was the path
# rewritten to "/api/admin/settings" and executed with the caller's session cookie.


@pytest.fixture
def versioned_app() -> FastAPI:
    """The real middleware stack order from web/backend/main.py."""
    from web.backend.middleware.api_version import ApiVersionMiddleware

    app = FastAPI()

    @app.post("/api/admin/protected")
    async def protected():
        return {"ok": True}

    @app.post("/api/customer/orders")
    async def orders():
        return {"ok": True}

    app.add_middleware(ApiVersionMiddleware)          # added first  -> innermost
    app.middleware("http")(csrf_protect_middleware)   # added second -> outside it
    return app


@pytest.mark.parametrize(
    "path",
    ["/api/admin/protected", "/api/v1/admin/protected"],
)
def test_admin_csrf_cannot_be_dodged_with_the_v1_prefix(versioned_app: FastAPI, path: str) -> None:
    client = TestClient(versioned_app)
    client.cookies.set("access_token", "fake-jwt")
    assert client.post(path).status_code == 403


@pytest.mark.parametrize(
    "path",
    ["/api/customer/orders", "/api/v1/customer/orders"],
)
def test_customer_csrf_cannot_be_dodged_with_the_v1_prefix(versioned_app: FastAPI, path: str) -> None:
    client = TestClient(versioned_app)
    client.cookies.set("customer_token", "fake-jwt")
    assert client.post(path).status_code == 403


def test_v1_prefix_still_works_with_a_valid_token(versioned_app: FastAPI) -> None:
    client = TestClient(versioned_app)
    client.cookies.set("access_token", "fake-jwt")
    client.cookies.set(CSRF_COOKIE, "matching-token")
    r = client.post("/api/v1/admin/protected", headers={CSRF_HEADER: "matching-token"})
    assert r.status_code == 200


def test_canonicalization_leaves_non_versioned_paths_alone() -> None:
    from web.backend.middleware.api_version import canonical_api_path

    assert canonical_api_path("/api/admin/x") == "/api/admin/x"
    assert canonical_api_path("/api/v1/admin/x") == "/api/admin/x"
    assert canonical_api_path("/api/v1") == "/api"
    assert canonical_api_path("/api/v10/admin/x") == "/api/v10/admin/x"   # not the v1 prefix
    assert canonical_api_path("/health") == "/health"
