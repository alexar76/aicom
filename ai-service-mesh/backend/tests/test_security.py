"""Security unit tests."""

import pytest

from ai_service_mesh.security import (
    INSECURE_DEFAULT_TOKENS,
    RateLimiter,
    assert_production_tokens,
    url_is_safe,
)


def test_url_blocks_localhost():
    assert url_is_safe("https://localhost/api") is False
    assert url_is_safe("https://127.0.0.1/api") is False


def test_url_requires_https():
    assert url_is_safe("http://example.com/api") is False


def test_url_allows_localhost_when_configured():
    assert url_is_safe("http://127.0.0.1:8091", allow_localhost=True) is True
    assert url_is_safe("http://127.0.0.1:8091", allow_localhost=False) is False


def test_url_allows_public_https(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    import socket

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert url_is_safe("https://example.com/agent") is True


def test_rate_limiter_blocks_burst():
    from fastapi import HTTPException

    lim = RateLimiter(3)
    lim.check("1.2.3.4")
    lim.check("1.2.3.4")
    lim.check("1.2.3.4")
    try:
        lim.check("1.2.3.4")
        raise AssertionError("expected 429")
    except HTTPException as e:
        assert e.status_code == 429


def test_rate_limiter_prunes_stale_ips():
    import time

    lim = RateLimiter(5)
    lim.check("10.0.0.1")
    assert "10.0.0.1" in lim._hits
    lim._prune_stale_keys(time.time() + 61)
    assert "10.0.0.1" not in lim._hits


def test_production_rejects_default_tokens():
    with pytest.raises(RuntimeError, match="MESH_API_TOKEN"):
        assert_production_tokens("production", "mesh-local-api", "secret-admin")
    with pytest.raises(RuntimeError):
        assert_production_tokens("production", "good-token", "mesh-local-admin")


def test_production_allows_insecure_when_flagged():
    assert_production_tokens(
        "production",
        "mesh-local-api",
        "mesh-local-admin",
        allow_insecure_tokens=True,
    )


def test_insecure_defaults_documented():
    assert "mesh-local-api" in INSECURE_DEFAULT_TOKENS
