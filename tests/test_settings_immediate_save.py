"""Admin settings: boolean toggles persist via POST /api/admin/settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.core.admin_roles import AdminRole, require_admin_with_rbac


@pytest.fixture
def settings_client(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    overlay = cfg_dir / "admin_config_overlay.yaml"
    overlay.write_text(
        yaml.dump({"general": {"local_high_throughput_enabled": True, "factory_on_hold": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_CONFIG_YAML", str(overlay))
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(Path(__file__).resolve().parents[1] / "config/fragments"))

    from web.backend.core.config import AppConfig
    from web.backend import main as main_mod

    app = main_mod.app
    app.state.config = AppConfig(str(overlay))
    app.dependency_overrides[require_admin_with_rbac] = lambda: AdminRole.ADMIN
    return TestClient(app), overlay


def test_post_local_high_throughput_false_persists(settings_client):
    client, overlay = settings_client
    resp = client.post("/api/admin/settings", json={"local_high_throughput_enabled": False})
    assert resp.status_code == 200
    assert "local_high_throughput_enabled" in resp.json().get("updated", [])

    get_resp = client.get("/api/admin/settings")
    assert get_resp.status_code == 200
    assert get_resp.json()["local_high_throughput_enabled"] is False

    saved = yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert saved["general"]["local_high_throughput_enabled"] is False


def test_post_factory_on_hold_true_persists(settings_client):
    client, overlay = settings_client
    resp = client.post("/api/admin/settings", json={"factory_on_hold": True})
    assert resp.status_code == 200
    get_resp = client.get("/api/admin/settings")
    assert get_resp.json()["factory_on_hold"] is True
