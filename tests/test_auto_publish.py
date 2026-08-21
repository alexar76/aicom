"""Unit tests for static auto-publish helpers (Vercel / Netlify / Cloudflare Pages)."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_vercel_token_from_secrets_file(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    secret = tmp_path / "secrets" / "vercel_token"
    secret.parent.mkdir(parents=True)
    secret.write_text("tok_from_file\n", encoding="utf-8")
    assert ap._vercel_token() == "tok_from_file"


def test_which_vercel_falls_back_to_data_npm_global(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(ap.shutil, "which", lambda _name: None)
    bin_path = tmp_path / ".npm-global" / "bin" / "vercel"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")
    assert ap._which_vercel() == str(bin_path)


def test_the_runtime_image_installs_the_vercel_cli():
    """A full_software product that passed every sandbox gate was still not published:
    the container had node and npm, and no `vercel` binary. Publish returned
    'vercel CLI not found on PATH' and never opened a live URL."""
    text = Path(__file__).resolve().parents[1].joinpath("Dockerfile").read_text(encoding="utf-8")
    assert "npm install -g vercel" in text


def test_full_software_publishes_working_app_not_vercel(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        ap,
        "_read_general",
        lambda: {
            "auto_publish_enabled": True,
            "auto_publish_landing_only": True,
            "auto_publish_provider": "vercel",
        },
    )
    monkeypatch.setattr(ap, "_product_delivery_profile", lambda _pid: "full_software")

    def fake_working(pid: str):
        return {
            "ok": True,
            "product_id": pid,
            "provider": "factory_compose",
            "published_url": "https://magic-ai-factory.com/api/sandbox/view/sandbox-x",
        }

    monkeypatch.setattr(
        "web.backend.services.working_app_publish.try_publish_working_app",
        fake_working,
    )
    out = ap.try_publish_after_devops("prod-app-1")
    assert out.get("ok") is True
    assert out.get("provider") == "factory_compose"
    assert "sandbox" in out["published_url"]


def test_working_app_publish_uses_compose_view_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")

    def fake_start(pid, storefront=False):
        assert pid == "prod-x"
        assert storefront is False
        return {
            "sandbox_id": "sandbox-abc",
            "url": "/api/sandbox/view/sandbox-abc?preview=tok",
            "compose_preview": {
                "status": "ok",
                "proxy_prefix": "/api/sandbox/compose/sandbox-abc/",
            },
            "preview_api": {"enabled": False},
        }

    monkeypatch.setattr(
        "web.backend.services.working_app_publish._sandbox_starter",
        lambda: fake_start,
    )
    from web.backend.services.working_app_publish import try_publish_working_app

    out = try_publish_working_app("prod-x")
    assert out["ok"] is True
    assert out["provider"] == "factory_compose"
    assert out["published_url"] == (
        "https://magic-ai-factory.com/api/sandbox/view/sandbox-abc?preview=tok"
    )
    saved = json.loads((tmp_path / "state" / "prod-x" / "auto_publish.json").read_text())
    assert saved["published_url"] == out["published_url"]
