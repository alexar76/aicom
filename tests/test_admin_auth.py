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

    def test_login_invalid_credentials(self, client, tmp_path):
        """Test login with invalid password (admin.json mocked — no /app/data needed)."""
        audit = tmp_path / "audit.jsonl"
        sm = SecurityManager(
            secret_key="test-secret-key-12345-for-testing-only",
            audit_log_path=str(audit),
        )
        admin_path = tmp_path / "admin.json"
        admin_path.write_text(
            json.dumps({"password_hash": sm.hash_password("the_real_password")}),
            encoding="utf-8",
        )

        def _path(arg):
            if arg == "/app/data/config/admin.json":
                return admin_path
            return RealPath(arg)

        with patch("web.backend.api.admin.auth.Path", side_effect=_path):
            response = client.post(
                "/api/admin/auth/login",
                json={"username": "admin", "password": "wrong_password"},
            )
        assert response.status_code == 401

    def test_theme_config(self, client):
        """Test theme configuration endpoint."""
        response = client.get("/api/config/theme")
        assert response.status_code == 200
        data = response.json()
        assert "theme" in data
