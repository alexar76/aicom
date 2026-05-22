"""Showcase capture must use a base URL reachable from the app process (8080 in Docker)."""

from __future__ import annotations

from unittest.mock import patch

from web.backend.services import product_showcase as ps


def test_resolve_showcase_base_url_rewrites_9080_in_docker(monkeypatch):
    monkeypatch.delenv("AIFACTORY_SHOWCASE_BASE_URL", raising=False)
    monkeypatch.delenv("AIFACTORY_PUBLIC_URL", raising=False)
    with patch.object(ps.Path, "is_file", return_value=True):
        url = ps._resolve_showcase_capture_base_url("http://127.0.0.1:9080")
    assert url == "http://127.0.0.1:8080"


def test_resolve_showcase_base_url_explicit_passthrough(monkeypatch):
    with patch.object(ps.Path, "is_file", return_value=True):
        url = ps._resolve_showcase_capture_base_url("https://magic-ai-factory.com")
    assert url == "https://magic-ai-factory.com"
