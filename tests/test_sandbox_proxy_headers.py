"""Sandbox reverse-proxy: forward product JWTs, drop cookies, survive slash mismatches."""

from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers


@pytest.fixture(autouse=True)
def _customer_issuer(monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "customer-test-issuer-" * 3)

from web.backend.services.sandbox_proxy_headers import (
    sandbox_proxy_forward_headers,
    sandbox_proxy_slash_variant,
    sandbox_proxy_upstream_url,
)
from web.backend.services.sandbox_static_rewrite import inject_preview_api_fetch_shim


class _Req:
    def __init__(self, headers: dict[str, str]):
        self.headers = Headers(headers)
        self.app = SimpleNamespace(state=SimpleNamespace(security_manager=SimpleNamespace(
            secret_key="admin-test-issuer-" * 3, jwt_algorithm="HS256",
        )))


def test_upstream_url_preserves_path_and_query():
    assert (
        sandbox_proxy_upstream_url("127.0.0.1", 32773, "api/v1/accounts/", "limit=10")
        == "http://127.0.0.1:32773/api/v1/accounts/?limit=10"
    )
    assert (
        sandbox_proxy_upstream_url("127.0.0.1", 32773, "/api/v1/accounts")
        == "http://127.0.0.1:32773/api/v1/accounts"
    )


def test_slash_variant_strips_only_a_real_path_slash():
    assert (
        sandbox_proxy_slash_variant("http://127.0.0.1:8000/api/v1/accounts/?a=1")
        == "http://127.0.0.1:8000/api/v1/accounts?a=1"
    )
    assert sandbox_proxy_slash_variant("http://127.0.0.1:8000/api/v1/accounts") is None
    # The origin root must never collapse to a path-less URL.
    assert sandbox_proxy_slash_variant("http://127.0.0.1:8000/") is None


def test_forward_bearer_not_cookies():
    req = _Req(
        {
            "Authorization": "Bearer product-jwt",
            "Cookie": "aif_admin_session=factory-secret",
            "X-CSRF-Token": "csrf",
            "Accept": "application/json",
        }
    )
    out = sandbox_proxy_forward_headers(req)
    lowered = {k.lower(): v for k, v in out.items()}
    assert lowered["authorization"] == "Bearer product-jwt"
    assert "cookie" not in lowered
    assert "x-csrf-token" not in lowered
    assert lowered["accept"] == "application/json"


def test_block_non_bearer_authorization():
    req = _Req({"Authorization": "Basic dXNlcjpwYXNz"})
    out = sandbox_proxy_forward_headers(req)
    assert "Authorization" not in out


@pytest.mark.parametrize("issuer", ["admin", "customer"])
@pytest.mark.parametrize("expiry", [1, 4_000_000_000])
def test_factory_session_jwts_never_reach_generated_apps(issuer, expiry):
    from core.jwt_tokens import encode_hs256
    from web.backend.services.commerce import _resolve_customer_jwt_secret
    req = _Req({})
    secret = req.app.state.security_manager.secret_key if issuer == "admin" else _resolve_customer_jwt_secret()
    token = encode_hs256({"sub": "factory-user", "exp": expiry}, secret)
    req.headers = Headers({"Authorization": "Bearer " + token})
    assert "Authorization" not in sandbox_proxy_forward_headers(req)


def test_independent_product_jwt_is_preserved():
    from core.jwt_tokens import encode_hs256
    token = encode_hs256({"sub": "product-user", "exp": 4_000_000_000}, "product-only-secret-" * 3)
    req = _Req({"Authorization": "Bearer " + token})
    assert sandbox_proxy_forward_headers(req)["Authorization"] == "Bearer " + token


def test_issuer_unavailable_fails_closed():
    req = _Req({"Authorization": "Bearer unknown"})
    del req.app
    assert "Authorization" not in sandbox_proxy_forward_headers(req)


def test_fetch_shim_patches_fetch_and_xhr():
    html = inject_preview_api_fetch_shim(
        "<html><head></head><body></body></html>",
        "sandbox-abc",
        preview_token="tok",
    )
    assert "XMLHttpRequest" in html
    assert "X-Sandbox-Preview-Token" in html
    assert "/api/sandbox/backend/sandbox-abc" in html
    # Opaque iframe must not ride the operator's session cookies.
    assert "credentials='omit'" in html or 'credentials="omit"' in html
    assert "withCredentials=false" in html
