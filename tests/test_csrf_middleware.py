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
