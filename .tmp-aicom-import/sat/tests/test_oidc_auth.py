"""Tests for OIDC / trusted-header SSO helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_oidc_auth():
    """Load oidc_auth without importing web.backend.core (pulls passlib)."""
    path = Path(__file__).resolve().parents[1] / "web" / "backend" / "core" / "oidc_auth.py"
    spec = importlib.util.spec_from_file_location("oidc_auth_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


oa = _load_oidc_auth()


def test_oidc_enabled_flag(monkeypatch):
    monkeypatch.delenv("AIFACTORY_OIDC_ENABLED", raising=False)
    assert oa.oidc_enabled() is False
    monkeypatch.setenv("AIFACTORY_OIDC_ENABLED", "1")
    assert oa.oidc_enabled() is True


def test_map_groups_to_role_from_json(monkeypatch):
    monkeypatch.setenv(
        "AIFACTORY_OIDC_ROLE_MAP",
        json.dumps({"admins": "admin", "operators": "operator"}),
    )
    assert oa.map_groups_to_role(["operators"]) == "operator"
    assert oa.map_groups_to_role(["unknown"]) == "viewer"
    # Invalid role names in the map are rejected and fall back to the default role.
    monkeypatch.setenv("AIFACTORY_OIDC_ROLE_MAP", json.dumps({"x": "superuser"}))
    assert oa.map_groups_to_role(["x"]) == "viewer"


def test_claims_to_username_prefers_preferred_username():
    claims = {"sub": "uuid-1", "email": "Admin@Example.com", "preferred_username": "admin"}
    assert oa.claims_to_username(claims) == "admin"


def test_trusted_header_sso_from_private_cidr(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_HEADER", "X-Remote-User")
    # The secure default trusts loopback only; operators must explicitly opt into a
    # wider, tightly-scoped CIDR for a non-loopback reverse proxy.
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_CIDRS", "127.0.0.1,::1,10.0.0.0/8")
    headers = {"X-Remote-User": "alice@corp.example"}
    assert oa.username_from_trusted_header(headers, "10.0.0.5") == "alice@corp.example"


def test_trusted_header_rejects_untrusted_cidr(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_HEADER", "X-Remote-User")
    headers = {"X-Remote-User": "alice@corp.example"}
    assert oa.username_from_trusted_header(headers, "203.0.113.50") is None


def test_client_in_trusted_cidr_loopback():
    assert oa.client_in_trusted_cidr("127.0.0.1") is True
    assert oa.client_in_trusted_cidr("8.8.8.8") is False


def test_safe_post_login_url_rejects_external(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PUBLIC_BASE_URL", raising=False)
    assert oa.safe_post_login_url("/admin/dashboard") == "/admin/dashboard"
    assert oa.safe_post_login_url("https://evil.example/phish") == "/admin"


def test_safe_post_login_url_allows_own_domain(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_BASE_URL", "https://factory.example")
    assert oa.safe_post_login_url("https://factory.example/admin") == "https://factory.example/admin"
