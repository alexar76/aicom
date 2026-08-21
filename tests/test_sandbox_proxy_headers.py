"""Sandbox reverse-proxy: forward product JWTs, drop cookies, survive slash mismatches."""

from starlette.datastructures import Headers

from web.backend.services.sandbox_proxy_headers import (
    sandbox_proxy_forward_headers,
    sandbox_proxy_slash_variant,
    sandbox_proxy_upstream_url,
)
from web.backend.services.sandbox_static_rewrite import inject_preview_api_fetch_shim


class _Req:
    def __init__(self, headers: dict[str, str]):
        self.headers = Headers(headers)


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


def test_fetch_shim_patches_fetch_and_xhr():
    html = inject_preview_api_fetch_shim(
        "<html><head></head><body></body></html>",
        "sandbox-abc",
        preview_token="tok",
    )
    assert "XMLHttpRequest" in html
    assert "X-Sandbox-Preview-Token" in html
    assert "/api/sandbox/backend/sandbox-abc" in html
