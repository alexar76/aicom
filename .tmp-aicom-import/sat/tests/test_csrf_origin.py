"""CSRF middleware origin checks for customer/support mutations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from web.backend.middleware.csrf import _origin_allowed


def _request(headers: dict[str, str], method: str = "POST", path: str = "/api/customer/register") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    return Request(scope)


def test_origin_allowed_for_configured_site(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    req = _request({"origin": "https://magic-ai-factory.com"})
    assert _origin_allowed(req) is True


def test_origin_rejects_unknown(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    req = _request({"origin": "https://evil.example"})
    assert _origin_allowed(req) is False


def test_no_origin_allows_non_browser_clients():
    req = _request({})
    assert _origin_allowed(req) is True
