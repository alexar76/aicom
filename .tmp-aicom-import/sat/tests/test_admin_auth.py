# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Admin Authentication Tests
# ============================================================================

import json
import time
from pathlib import Path as RealPath
from unittest.mock import patch

import pytest

from web.backend.core.security import SecurityManager


class TestSecurityManager:
    """Tests for the Security Manager."""

    @pytest.fixture
    def security(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        return SecurityManager(
            secret_key="test-secret-key-12345-for-testing-only",
            jwt_algorithm="HS256",
            jwt_expiry_minutes=30,
            max_login_attempts=5,
            ban_minutes=15,
            audit_log_path=str(audit_path),
        )

    def test_password_hashing(self, security):
        """Test password hashing and verification."""
        password = "MySecurePassword123!"
        hashed = security.hash_password(password)

        assert hashed != password
        assert security.verify_password(password, hashed)
        assert not security.verify_password("WrongPassword", hashed)

    def test_jwt_token_creation(self, security):
        """Test JWT token creation and decoding."""
        token = security.create_access_token("admin", is_admin=True)
        assert token is not None

        payload = security.decode_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"
        assert payload["admin"] is True
        assert payload.get("role") == "super_admin"

    def test_jwt_token_expiry(self, security):
        """Test JWT token expiration."""
        security.jwt_expiry_minutes = 0
        token = security.create_access_token("admin", is_admin=True)
        time.sleep(0.15)
        payload = security.decode_token(token)
        assert payload is None

    def test_invalid_token(self, security):
        """Test invalid JWT token."""
        payload = security.decode_token("invalid.token.here")
        assert payload is None

    def test_brute_force_protection(self, security):
        """Test brute force attempt tracking."""
        ip = "10.0.0.100"
        security.max_login_attempts = 5
        for _ in range(5):
            assert security.check_login_attempts(ip)
            security.record_login_attempt(ip, False, "")
        assert not security.check_login_attempts(ip)

    def test_login_attempts_reset(self, security):
        """Test login attempts reset after manual clear."""
        ip = "10.0.0.101"
        security.max_login_attempts = 5
        for _ in range(5):
            security.record_login_attempt(ip, False, "")
        assert not security.check_login_attempts(ip)

        security.reset_login_attempts(ip)
        assert security.check_login_attempts(ip)

    def test_totp_generation(self, security):
        """Test TOTP secret generation."""
        secret = security.generate_totp_secret()
        assert len(secret) > 10

    def test_totp_verification(self, security):
        """Test TOTP code verification."""
        secret = security.generate_totp_secret()

        import pyotp

        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        assert security.verify_totp(secret, valid_code)
        assert not security.verify_totp(secret, "000000")

    def test_audit_logging_on_auth(self, security):
        """Test that authentication events are audited."""
        security.record_login_attempt("10.0.0.1", True, "admin")

        logs = security.get_audit_logs(limit=10)
        assert len(logs) >= 1
        assert logs[-1]["action"] == "login_attempt"

    def test_password_change(self, security):
        """Test password change flow."""
        old_password = "OldPassword123!"
        new_password = "NewPassword456!"

        old_hash = security.hash_password(old_password)
        new_hash = security.hash_password(new_password)

        assert security.verify_password(old_password, old_hash)
        assert security.verify_password(new_password, new_hash)
        assert not security.verify_password(old_password, new_hash)


class TestAdminAuthAPI:
    """Tests for the Admin Auth API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI app (runs lifespan — app.state populated)."""
        from fastapi.testclient import TestClient

        from web.backend.main import app

        with TestClient(app) as c:
            yield c

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_login_no_auth(self, client):
        """Test accessing protected endpoint without auth."""
        response = client.get("/api/admin/dashboard")
        assert response.status_code == 401

    def test_login_invalid_credentials(self, client, tmp_path, monkeypatch):
        """Login with a wrong password returns 401 (multi-user admin_users store)."""
        from web.backend.services import admin_users_store as aus

        audit = tmp_path / "audit.jsonl"
        sm = SecurityManager(
            secret_key="test-secret-key-12345-for-testing-only",
            audit_log_path=str(audit),
        )
        # Seed the admin_users store the login handler actually reads.
        monkeypatch.setattr(aus, "USERS_PATH", tmp_path / "admin_users.json")
        aus.create_user(
            username="admin",
            password_hash=sm.hash_password("the_real_password"),
            role="super_admin",
        )

        response = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "wrong_password"},
        )
        assert response.status_code == 401

    def test_public_demo_passwordless_admin_login(self, client, tmp_path, monkeypatch):
        """Shared demo host: admin enters with empty password."""
        from web.backend.services import admin_users_store as aus

        monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
        monkeypatch.setattr(aus, "USERS_PATH", tmp_path / "admin_users.json")
        sm = SecurityManager(secret_key="test-secret-key-12345-for-testing-only")
        aus.create_user(
            username="admin",
            password_hash=sm.hash_password("legacy-demo-password"),
            role="super_admin",
        )

        response = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": ""},
        )
        assert response.status_code == 200
        assert response.json().get("access_token")

    def test_public_demo_passwordless_ignores_autofill_password(self, client, tmp_path, monkeypatch):
        """Browser autofill must not block passwordless demo entry."""
        from web.backend.services import admin_users_store as aus

        monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
        monkeypatch.setattr(aus, "USERS_PATH", tmp_path / "admin_users.json")
        sm = SecurityManager(secret_key="test-secret-key-12345-for-testing-only")
        aus.create_user(
            username="admin",
            password_hash=sm.hash_password("legacy-demo-password"),
            role="super_admin",
        )

        response = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "autofilled-garbage"},
        )
        assert response.status_code == 200
        assert response.json().get("access_token")

    def test_public_demo_config_endpoint(self, client, monkeypatch):
        monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
        response = client.get("/api/public/demo-config")
        assert response.status_code == 200
        data = response.json()
        assert data["public_demo"] is True
        assert data["passwordless_admin"] is True

    def test_theme_config(self, client):
        """Test theme configuration endpoint."""
        response = client.get("/api/config/theme")
        assert response.status_code == 200
        data = response.json()
        assert "theme" in data


def _admin_whoami_request(sm, *, bearer: str | None = None, cookie: str | None = None):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from fastapi.security import HTTPAuthorizationCredentials

    request = MagicMock()
    request.client = SimpleNamespace(host="127.0.0.1")
    request.headers = {}
    request.cookies = {}
    if cookie:
        request.cookies["aif_admin_session"] = cookie
    request.app.state.security_manager = sm
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer) if bearer else None
    return request, creds


def test_stale_bearer_falls_back_to_admin_session_cookie(tmp_path):
    """Leftover localStorage JWT must not hide a valid HttpOnly session cookie."""
    import asyncio

    from web.backend.core.security import SecurityManager, get_current_admin

    audit_path = tmp_path / "logs" / "audit.jsonl"
    sm = SecurityManager(
        secret_key="test-secret-key-12345-for-testing-only",
        jwt_expiry_minutes=30,
        audit_log_path=str(audit_path),
    )
    good = sm.create_access_token("cookie-admin", is_admin=True)
    sm.jwt_expiry_minutes = 0
    stale = sm.create_access_token("stale-localstorage", is_admin=True)
    time.sleep(0.12)
    assert sm.decode_token(stale) is None

    request, creds = _admin_whoami_request(sm, bearer=stale, cookie=good)
    payload = asyncio.run(get_current_admin(request, creds))
    assert payload["sub"] == "cookie-admin"


def test_garbage_bearer_falls_back_to_admin_session_cookie(tmp_path):
    import asyncio

    from web.backend.core.security import SecurityManager, get_current_admin

    audit_path = tmp_path / "logs" / "audit.jsonl"
    sm = SecurityManager(
        secret_key="test-secret-key-12345-for-testing-only",
        jwt_expiry_minutes=30,
        audit_log_path=str(audit_path),
    )
    good = sm.create_access_token("cookie-admin", is_admin=True)
    request, creds = _admin_whoami_request(sm, bearer="null", cookie=good)
    payload = asyncio.run(get_current_admin(request, creds))
    assert payload["sub"] == "cookie-admin"


def test_non_admin_bearer_without_cookie_is_forbidden(tmp_path):
    import asyncio

    from fastapi import HTTPException

    from web.backend.core.security import SecurityManager, get_current_admin

    audit_path = tmp_path / "logs" / "audit.jsonl"
    sm = SecurityManager(
        secret_key="test-secret-key-12345-for-testing-only",
        jwt_expiry_minutes=30,
        audit_log_path=str(audit_path),
    )
    customer = sm.create_access_token("shopper", is_admin=False)
    request, creds = _admin_whoami_request(sm, bearer=customer)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(get_current_admin(request, creds))
    assert ei.value.status_code == 403


def test_non_admin_bearer_does_not_mask_admin_session_cookie(tmp_path):
    import asyncio

    from web.backend.core.security import SecurityManager, get_current_admin

    audit_path = tmp_path / "logs" / "audit.jsonl"
    sm = SecurityManager(
        secret_key="test-secret-key-12345-for-testing-only",
        jwt_expiry_minutes=30,
        audit_log_path=str(audit_path),
    )
    customer = sm.create_access_token("shopper", is_admin=False)
    admin = sm.create_access_token("cookie-admin", is_admin=True)
    request, creds = _admin_whoami_request(sm, bearer=customer, cookie=admin)
    payload = asyncio.run(get_current_admin(request, creds))
    assert payload["sub"] == "cookie-admin"


def test_files_tab_does_not_send_legacy_admin_token():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "frontend"
        / "components"
        / "admin"
        / "tabs"
        / "FilesTab.tsx"
    ).read_text(encoding="utf-8")
    assert "localStorage.getItem('admin_token')" not in src
    assert "getAdminProductFiles" in src
    assert "Loader2" in src
    assert "Loading file list" in src
