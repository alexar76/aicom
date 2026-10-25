"""Admin revocation boundaries, using real routes and temporary stores only."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, WebSocketException
from fastapi.testclient import TestClient

from web.backend.api.admin import auth, oidc_auth, users_admin
from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.core.security import SecurityManager
from web.backend.core.websocket_admin import require_admin_websocket
from web.backend.services import admin_users_store as store


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AIFACTORY_SSO_TRUSTED_HEADER", raising=False)
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "0")
    monkeypatch.setattr(store, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(store, "LEGACY_ADMIN_PATH", tmp_path / "admin.json")
    monkeypatch.setattr(auth, "ADMIN_JSON", tmp_path / "admin.json")
    security = SecurityManager(audit_log_path=str(tmp_path / "audit.jsonl"))
    password = "defensive-test-password-1234"
    owner = store.create_user(username="owner", password_hash=security.hash_password(password), role="super_admin")
    app = FastAPI()
    app.state.security_manager = security
    app.include_router(auth.router)
    app.include_router(oidc_auth.router)
    app.include_router(users_admin.router)

    @app.get("/api/admin/security-check")
    async def security_check(admin=Depends(require_admin_with_rbac)):
        return {"username": admin["sub"], "role": admin["role"]}

    @app.get("/api/admin/session")
    async def session(admin=Depends(require_admin_with_rbac)):
        return {"username": admin["sub"], "role": admin["role"]}

    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        yield SimpleNamespace(client=client, security=security, password=password, owner=owner, app=app, root=tmp_path)


def bearer(token):
    return {"Authorization": "Bearer " + token}


def login_subject(sessions, *, role="super_admin"):
    row = store.create_user(username="subject", password_hash=sessions.security.hash_password(sessions.password), role=role)
    response = sessions.client.post("/api/admin/auth/login", json={"username": "subject", "password": sessions.password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    sessions.client.cookies.clear()
    assert sessions.client.get("/api/admin/security-check", headers=bearer(token)).status_code == 200
    return row, token


@pytest.mark.parametrize("change", ["demote", "disable", "password", "delete"])
def test_security_mutations_end_existing_sessions(sessions, change):
    row, token = login_subject(sessions, role="admin" if change == "delete" else "super_admin")
    owner_token = sessions.security.create_access_token("owner", role="super_admin")
    path = "/api/admin/users/" + row["id"]
    if change == "password":
        response = sessions.client.post(path + "/password", headers=bearer(owner_token), json={"new_password": "changed-defensive-password-1234"})
    elif change == "delete":
        response = sessions.client.delete(path, headers=bearer(owner_token))
    else:
        response = sessions.client.patch(path, headers=bearer(owner_token), json={"role": "viewer"} if change == "demote" else {"enabled": False})
    assert response.status_code == 200
    assert sessions.client.get("/api/admin/security-check", headers=bearer(token)).status_code == 401
    assert sessions.client.post("/api/admin/users", headers=bearer(token), json={
        "username": "unauthorized", "password": sessions.password, "role": "super_admin",
    }).status_code == 401


def test_reenabling_and_restoring_role_does_not_revive_old_session(sessions):
    row, token = login_subject(sessions)
    store.update_user(row["id"], enabled=False)
    store.update_user(row["id"], enabled=True)
    assert sessions.security.authenticate_admin_token(token) is None
    current = sessions.security.create_access_token("subject", role="super_admin")
    store.update_user(row["id"], role="viewer")
    store.update_user(row["id"], role="super_admin")
    assert sessions.security.authenticate_admin_token(current) is None


def test_recreated_username_cannot_inherit_deleted_users_session(sessions):
    row, token = login_subject(sessions, role="admin")
    store.delete_user(row["id"])
    store.create_user(username="subject", password_hash="!", role="super_admin")
    assert sessions.security.authenticate_admin_token(token) is None


def test_current_role_controls_authorization(sessions):
    store.create_user(username="viewer", password_hash="!", role="viewer")
    token = sessions.security.create_access_token("viewer", role="super_admin")
    response = sessions.client.get("/api/admin/session", headers=bearer(token))
    assert response.json()["role"] == "viewer"
    assert sessions.client.get("/api/admin/users", headers=bearer(token)).status_code == 403


def test_pre_migration_unbound_token_requires_new_login(sessions):
    from core.jwt_tokens import encode_hs256

    _, token = login_subject(sessions)
    claims = sessions.security.decode_token(token)
    claims.pop("uid")
    claims.pop("auth_version")
    old_token = encode_hs256(claims, sessions.security.secret_key)
    assert sessions.client.get("/api/admin/users", headers=bearer(old_token)).status_code == 401


def test_existing_user_row_without_session_version_can_login(sessions):
    row, _ = login_subject(sessions)
    raw = store._load_raw()
    next(user for user in raw["users"] if user["id"] == row["id"]).pop("session_version")
    store._save_raw(raw)
    response = sessions.client.post("/api/admin/auth/login", json={"username": "subject", "password": sessions.password})
    assert response.status_code == 200
    assert sessions.security.authenticate_admin_token(response.json()["access_token"])["auth_version"] == "0"


@pytest.mark.parametrize("source", ["bearer", "access_token", "aif_admin_session"])
def test_logout_revokes_presented_session_across_manager_restart(sessions, source):
    _, token = login_subject(sessions)
    other_session = sessions.security.create_access_token("subject", role="super_admin")
    headers = bearer(token) if source == "bearer" else {}
    if source != "bearer":
        sessions.client.cookies.set(source, token)
    assert sessions.client.post("/api/admin/auth/logout", headers=headers).status_code == 200
    sessions.client.cookies.clear()
    sessions.app.state.security_manager = SecurityManager(audit_log_path=str(sessions.root / "restarted-audit.jsonl"))
    assert sessions.client.get("/api/admin/users", headers=bearer(token)).status_code == 401
    assert sessions.client.get("/api/admin/users", headers=bearer(other_session)).status_code == 200


def test_logout_retains_audit_event(sessions, monkeypatch):
    from web.backend.services import admin_action_log

    _, token = login_subject(sessions)
    events = []
    monkeypatch.setattr(admin_action_log, "log_admin_action_from_request", lambda *args, **kwargs: events.append(kwargs))
    assert sessions.client.post("/api/admin/auth/logout", headers=bearer(token)).status_code == 200
    assert [event["action"] for event in events] == ["logout"]


def test_password_change_revokes_current_session(sessions):
    _, token = login_subject(sessions)
    response = sessions.client.post("/api/admin/auth/change-password", headers=bearer(token), json={
        "old_password": sessions.password, "new_password": "new-defensive-password-1234",
    })
    assert response.status_code == 200
    assert sessions.client.get("/api/admin/users", headers=bearer(token)).status_code == 401


def test_password_reset_during_login_cannot_issue_a_session_from_old_password(sessions, monkeypatch):
    row, _ = login_subject(sessions)
    verify = sessions.security.verify_password

    def reset_after_verification(password, hashed):
        valid = verify(password, hashed)
        store.update_user(row["id"], password_hash=sessions.security.hash_password("reset-during-signin-password"))
        return valid

    monkeypatch.setattr(sessions.security, "verify_password", reset_after_verification)
    response = sessions.client.post("/api/admin/auth/login", json={"username": "subject", "password": sessions.password})
    assert response.status_code == 401
    assert "aif_admin_session" not in response.cookies
    assert "access_token" not in response.json()


def test_legacy_bootstrap_login_issues_bound_session(sessions):
    store.USERS_PATH.unlink()
    auth.ADMIN_JSON.write_text(json.dumps({
        "username": "legacy", "password_hash": sessions.security.hash_password(sessions.password),
    }))
    response = sessions.client.post("/api/admin/auth/login", json={"username": "legacy", "password": sessions.password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    claims = sessions.security.authenticate_admin_token(token)
    assert claims and claims["role"] == "super_admin"
    assert claims["uid"] == store.get_user_by_username("legacy")["id"]


def test_oidc_provisioned_session_obeys_local_disable(sessions, monkeypatch):
    monkeypatch.setenv("AIFACTORY_OIDC_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_OIDC_DEFAULT_ROLE", "operator")
    monkeypatch.setattr(oidc_auth, "exchange_code", lambda code: {"id_token": "test-only"})
    monkeypatch.setattr(oidc_auth, "verify_id_token", lambda token, nonce: {"preferred_username": "oidc-user"})
    sessions.client.cookies.set("oidc_state", "test-state")
    sessions.client.cookies.set("oidc_nonce", "test-nonce")
    response = sessions.client.get("/api/admin/auth/oidc/callback?code=test&state=test-state", follow_redirects=False)
    assert response.status_code == 302
    token = response.cookies["aif_admin_session"]
    assert sessions.security.authenticate_admin_token(token)["role"] == "operator"
    store.update_user(store.get_user_by_username("oidc-user")["id"], enabled=False)
    assert sessions.security.authenticate_admin_token(token) is None


def test_trusted_header_preserves_sso_and_honors_local_account_state(sessions, monkeypatch):
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_HEADER", "X-Remote-User")
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_CIDRS", "127.0.0.1")
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_DEFAULT_ROLE", "operator")
    headers = {"X-Remote-User": "new-sso-user"}
    assert sessions.client.get("/api/admin/session", headers=headers).json()["role"] == "operator"
    row = store.create_user(username="new-sso-user", password_hash="!", role="viewer")
    assert sessions.client.get("/api/admin/session", headers=headers).json()["role"] == "viewer"
    store.update_user(row["id"], enabled=False)
    assert sessions.client.get("/api/admin/session", headers=headers).status_code == 403


@pytest.mark.asyncio
async def test_new_websocket_authentication_rejects_ended_session(sessions):
    row, token = login_subject(sessions)
    websocket = SimpleNamespace(app=sessions.app, headers=bearer(token), cookies={}, scope={})
    # Real Starlette headers are case insensitive.
    websocket.headers = {"authorization": "Bearer " + token}
    assert (await require_admin_websocket(websocket))["sub"] == "subject"
    store.update_user(row["id"], enabled=False)
    with pytest.raises(WebSocketException):
        await require_admin_websocket(websocket)


def test_missing_revocation_store_fails_closed(sessions):
    _, token = login_subject(sessions)
    sessions.security._rl_store = None
    assert sessions.client.get("/api/admin/users", headers=bearer(token)).status_code == 401
    assert sessions.client.post("/api/admin/auth/logout", headers=bearer(token)).status_code == 503
