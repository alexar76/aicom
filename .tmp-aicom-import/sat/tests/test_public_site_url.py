"""Public site URL resolution and watermark HTML."""

from __future__ import annotations

import pytest

from core.public_site_url import (
    DEFAULT_PUBLIC_SITE_URL,
    resolve_public_site_url,
    sync_watermark_in_html,
    watermark_badge_html,
)


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    monkeypatch.delenv("AIFACTORY_PUBLIC_SITE_URL", raising=False)
    assert resolve_public_site_url(config={"general": {}}) == DEFAULT_PUBLIC_SITE_URL


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://custom.example")
    assert (
        resolve_public_site_url(config={"general": {"public_site_url": "https://ignored.example"}})
        == "https://custom.example"
    )


def test_config_used_when_env_empty(monkeypatch):
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    assert (
        resolve_public_site_url(config={"general": {"public_site_url": "https://cfg.example"}})
        == "https://cfg.example"
    )


def test_watermark_uses_resolved_url(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    html_out = watermark_badge_html()
    assert 'href="https://magic-ai-factory.com"' in html_out
    assert "aifactory.dev" not in html_out


def test_sync_replaces_legacy_href():
    old = (
        '<div class="aifactory-badge">Made with '
        '<a href="https://aifactory.dev">AI-Factory</a></div></body>'
    )
    out = sync_watermark_in_html(old, "https://magic-ai-factory.com")
    assert "https://magic-ai-factory.com" in out
    assert "aifactory.dev" not in out


def test_sync_injects_before_body():
    out = sync_watermark_in_html("<html><body><p>x</p></body></html>", "https://magic-ai-factory.com")
    assert "aifactory-badge" in out
    assert out.index("aifactory-badge") < out.lower().index("</body>")


def test_audit_watermark_rejects_legacy_host():
    from core.public_site_url import audit_watermark_in_html

    html = (
        '<div class="aifactory-badge">Made with '
        '<a href="https://aifactory.dev">AI-Factory</a></div>'
    )
    issue = audit_watermark_in_html(html, expected="https://magic-ai-factory.com")
    assert issue is not None
    assert issue["code"] == "watermark_wrong_public_url"


def test_audit_watermark_accepts_configured_url():
    from core.public_site_url import audit_watermark_in_html, watermark_badge_html

    html = "<body>" + watermark_badge_html("https://magic-ai-factory.com") + "</body>"
    assert audit_watermark_in_html(html, expected="https://magic-ai-factory.com") is None
