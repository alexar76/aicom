"""invoke_url host-gateway rewrite for Hub-in-Docker dev flows."""

import os

import pytest

from aimarket_hub.outbound_http import invoke_url_is_safe, resolve_invoke_url


def test_resolve_invoke_url_rewrites_localhost(monkeypatch):
    monkeypatch.setenv("AIMARKET_INVOKE_HOST_GATEWAY", "host.docker.internal")
    assert (
        resolve_invoke_url("http://127.0.0.1:3456/invoke")
        == "http://host.docker.internal:3456/invoke"
    )
    assert resolve_invoke_url("https://example.com/invoke") == "https://example.com/invoke"


def test_invoke_url_is_safe_allows_csv_gateway_hosts(monkeypatch):
    monkeypatch.setenv("AIMARKET_INVOKE_HOST_GATEWAY", "api,kova-api")
    assert invoke_url_is_safe("http://api:8000/capabilities/x/y/invoke")
    assert invoke_url_is_safe("http://kova-api:8000/capabilities/x/y/invoke")
    assert not invoke_url_is_safe("http://other-api:8000/invoke")


def test_resolve_invoke_url_noop_without_gateway(monkeypatch):
    monkeypatch.delenv("AIMARKET_INVOKE_HOST_GATEWAY", raising=False)
    url = "http://127.0.0.1:3456/invoke"
    assert resolve_invoke_url(url) == url
