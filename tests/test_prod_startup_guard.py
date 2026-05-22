"""Production mode must refuse known demo passwords."""

from __future__ import annotations

import json

import pytest

from security import prod_startup_guard as guard


def test_production_mode_off_allows_demo_env(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.setenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", "demo123")
    assert guard.production_startup_issues() == []


def test_production_rejects_dev_bootstrap_demo_password(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", "demo123")
    issues = guard.production_startup_issues()
    assert any("AIFACTORY_DEV_BOOTSTRAP_PASSWORD" in i for i in issues)


def test_production_rejects_demo_readonly_combo(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    issues = guard.production_startup_issues()
    assert any("DEMO_READONLY" in i for i in issues)


def test_production_rejects_stored_demo123_hash(monkeypatch, tmp_path):
    from web.backend.core.security import SecurityManager

    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)

    sec = SecurityManager()
    admin_json = tmp_path / "admin.json"
    admin_json.write_text(
        json.dumps({"username": "admin", "password_hash": sec.hash_password("demo123")}),
        encoding="utf-8",
    )
    monkeypatch.setattr("security.prod_startup_guard.legacy_admin_path", lambda: admin_json)
    monkeypatch.setattr(
        "security.prod_startup_guard.admin_users_path",
        lambda: tmp_path / "missing-users.json",
    )

    issues = guard.production_startup_issues()
    assert any("weak password" in i for i in issues)
