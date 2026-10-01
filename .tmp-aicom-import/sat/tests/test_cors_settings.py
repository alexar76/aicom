"""CORS allow-origins from environment."""

from __future__ import annotations

import pytest

from web.backend.cors_settings import (
    DEFAULT_CORS_ORIGINS,
    PUBLIC_LANDING_CORS_ORIGINS,
    get_cors_allow_origins,
)


def test_explicit_origins_merge_public_landing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_CORS_ORIGINS", "https://app.example.com, https://admin.example.com ")
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    out = get_cors_allow_origins()
    assert out[:2] == ["https://app.example.com", "https://admin.example.com"]
    for origin in PUBLIC_LANDING_CORS_ORIGINS:
        assert origin in out


def test_default_list_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFACTORY_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    out = get_cors_allow_origins()
    assert out[: len(DEFAULT_CORS_ORIGINS)] == list(DEFAULT_CORS_ORIGINS)
    for origin in PUBLIC_LANDING_CORS_ORIGINS:
        assert origin in out


def test_appends_next_public_site_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFACTORY_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://factory.example.org")
    out = get_cors_allow_origins()
    assert "https://factory.example.org" in out
    assert out[0] == DEFAULT_CORS_ORIGINS[0]
    assert "https://alexar76.github.io" in out
