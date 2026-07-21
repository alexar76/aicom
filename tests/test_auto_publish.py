"""Unit tests for static auto-publish helpers (Vercel / Netlify / Cloudflare Pages)."""

from __future__ import annotations

from web.backend.services import auto_publish as ap


def test_extract_url_vercel():
    url = ap._extract_url(
        "Deployment ready\nhttps://my-app.vercel.app\n",
        "",
        "vercel",
    )
    assert url == "https://my-app.vercel.app"


def test_extract_url_netlify():
    url = ap._extract_url(
        "",
        "Website URL: https://sparkling-cupcake-123.netlify.app",
        "netlify",
    )
    assert url and "netlify.app" in url


def test_extract_url_cloudflare_pages():
    url = ap._extract_url(
        "Success! https://my-project.pages.dev",
        "",
        "cloudflare_pages",
    )
    assert url == "https://my-project.pages.dev"


def test_try_publish_skipped_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    cfg.write_text("general:\n  auto_publish_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_CONFIG_PATH", str(cfg))

    out = ap.try_publish_after_devops("prod-test-1")
    assert out.get("skipped") is True
    assert out.get("reason") == "disabled"
