"""Public demo: admin mutations are refused unless a guest is meant to make them.

On the demo the admin login is passwordless, so the admin API is every visitor's API.
Before this guard ``PUT /api/admin/providers/{name}`` could repoint a provider's base_url,
and the next provider probe sent the factory's own provider key to that host.
"""

from __future__ import annotations

import pytest

from web.backend.middleware.public_demo_readonly import demo_refusal


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/admin/providers/openrouter_api"),
        ("POST", "/api/admin/providers"),
        ("PUT", "/api/admin/providers/routing-rules"),
        ("POST", "/api/admin/outreach/announcements/a1/send"),
        ("PUT", "/api/admin/blog/posts/hello"),
        ("POST", "/api/admin/wow/prompts/apply"),
        ("POST", "/api/admin/auth/setup-2fa"),
        ("POST", "/api/admin/pipeline-database/test-connection"),
        ("PATCH", "/api/admin/pipeline/products/p1/storefront-pricing"),
        # the version prefix reaches the same routes and must not be a way around
        ("PUT", "/api/v1/admin/providers/openrouter_api"),
        ("put", "/api/admin/providers/openrouter_api/"),
    ],
)
def test_demo_refuses_admin_mutations_off_the_allow_list(method, path):
    assert demo_refusal(method, path)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/admin/auth/login"),
        ("POST", "/api/admin/auth/logout"),
        ("POST", "/api/admin/settings"),
        ("POST", "/api/admin/products/create"),
        ("POST", "/api/v1/admin/products/create"),
        ("GET", "/api/admin/providers"),
        ("GET", "/api/admin/pipeline/products"),
        ("POST", "/api/sandbox/start"),
        ("POST", "/api/support/sessions"),
    ],
)
def test_demo_lets_guests_do_what_the_demo_offers(method, path):
    assert demo_refusal(method, path) is None


@pytest.mark.parametrize(
    "path",
    ["/api/admin/funnel", "/api/admin/outreach/channels", "/api/admin/support-queue",
     "/api/v1/admin/funnel/"],
)
def test_demo_refuses_reads_of_other_peoples_data(path):
    assert demo_refusal("GET", path)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from web.backend.main import app

    with TestClient(app) as c:
        yield c


def _demo_admin_token(client, tmp_path, monkeypatch):
    from web.backend.core.security import SecurityManager
    from web.backend.services import admin_users_store as aus

    monkeypatch.setattr(aus, "USERS_PATH", tmp_path / "admin_users.json")
    sm = SecurityManager(secret_key="test-secret-key-12345-for-testing-only")
    aus.create_user(username="admin", password_hash=sm.hash_password("x" * 16), role="super_admin")
    r = client.post("/api/admin/auth/login", json={"username": "admin", "password": ""})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(client, token):
    # A browser session sends the double-submit CSRF token with every mutation.
    return {"Authorization": f"Bearer {token}", "X-CSRF-Token": client.cookies.get("csrf_token") or ""}


def test_demo_visitor_cannot_repoint_a_provider(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    token = _demo_admin_token(client, tmp_path, monkeypatch)
    headers = _headers(client, token)
    body = {"base_url": "https://attacker.example/v1"}
    for path in ("/api/admin/providers/no_such_provider", "/api/v1/admin/providers/no_such_provider"):
        r = client.put(path, json=body, headers=headers)
        # Without the guard the handler runs and answers 404 for the unknown name.
        assert r.status_code == 403, (path, r.status_code, r.text)
        assert "Public demo mode" in r.json()["detail"]


def test_demo_off_leaves_the_admin_api_alone(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    token = _demo_admin_token(client, tmp_path, monkeypatch)
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "0")
    r = client.put(
        "/api/admin/providers/no_such_provider",
        json={"base_url": "https://example.org/v1"},
        headers=_headers(client, token),
    )
    assert r.status_code == 404, r.text
