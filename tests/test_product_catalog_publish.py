"""Tests for selective product catalog GitHub publish helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from web.backend.services import product_catalog_publish as pcp


def test_github_house_ok_requires_contributing_and_badges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pid = "prod-testcatalog01"
    root = tmp_path / pid
    root.mkdir()
    (root / "README.md").write_text("# X\n", encoding="utf-8")
    monkeypatch.setattr(pcp, "code_dir", lambda _pid: root)
    monkeypatch.setenv("GH_PAT", "test-token")

    general = {
        "product_catalog_enabled": True,
        "product_catalog_require_github_house": True,
    }
    ok, reason = pcp.github_house_ok(pid, general)
    assert ok is False
    assert "CONTRIBUTING" in reason

    (root / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
    ok, reason = pcp.github_house_ok(pid, general)
    assert ok is False
    assert "badge" in reason.lower()

    (root / "README.md").write_text(
        "# X\n<!-- aicom-readme-badges -->\n![ci](docs/badges/ci.svg)\n<!-- /aicom-readme-badges -->\n",
        encoding="utf-8",
    )
    ok, reason = pcp.github_house_ok(pid, general)
    assert ok is False
    assert "dead README" in reason

    (root / "docs" / "badges").mkdir(parents=True)
    (root / "docs" / "badges" / "ci.svg").write_text("<svg/>\n", encoding="utf-8")
    ok, reason = pcp.github_house_ok(pid, general)
    assert ok is True
    assert reason == ""


def test_github_house_ok_skipped_without_github(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    pid = "prod-x"
    root = tmp_path / pid
    root.mkdir()
    monkeypatch.setattr(pcp, "code_dir", lambda _pid: root)
    ok, reason = pcp.github_house_ok(pid, {"product_catalog_enabled": False})
    assert ok is True
    assert reason == ""


def test_try_publish_skips_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pcp, "_read_general", lambda: {"product_catalog_enabled": False})
    out = pcp.try_publish_product_catalog("prod-x")
    assert out["skipped"] is True
    assert out["ok"] is False


def test_try_publish_skips_without_pat(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        pcp,
        "_read_general",
        lambda: {
            "product_catalog_enabled": True,
            "product_catalog_allowlist": "prod-x",
            "product_catalog_require_github_house": True,
        },
    )
    out = pcp.try_publish_product_catalog("prod-x")
    assert out["skipped"] is True
    assert "github_not_configured" in out["detail"]


def test_resolve_product_live_url_from_auto_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state" / "prod-x"
    state.mkdir(parents=True)
    (state / "auto_publish.json").write_text(
        '{"vercel_url": "https://prod-x.vercel.app", "ok": true}',
        encoding="utf-8",
    )
    monkeypatch.setattr(pcp, "data_root", lambda: tmp_path)
    assert pcp.resolve_product_live_url("prod-x") == "https://prod-x.vercel.app"
