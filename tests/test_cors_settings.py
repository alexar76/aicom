"""CORS allow-origins from environment."""

from __future__ import annotations

import pytest

from web.backend.cors_settings import DEFAULT_CORS_ORIGINS, get_cors_allow_origins


def test_explicit_origins_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_CORS_ORIGINS", "https://app.example.com, https://admin.example.com ")
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    assert get_cors_allow_origins() == ["https://app.example.com", "https://admin.example.com"]


def test_default_list_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFACTORY_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    assert get_cors_allow_origins() == list(DEFAULT_CORS_ORIGINS)


def test_appends_next_public_site_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFACTORY_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://factory.example.org")
    out = get_cors_allow_origins()
    assert "https://factory.example.org" in out
    assert out[0] == DEFAULT_CORS_ORIGINS[0]
