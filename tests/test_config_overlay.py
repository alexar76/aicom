"""Tests for config overlay bootstrap and legacy JSON mirror."""

from __future__ import annotations

import json

import yaml

from core.config_overlay import ensure_primary_config_overlay, patch_primary_overlay


def test_ensure_primary_config_overlay_creates_json_mirror(tmp_path, monkeypatch):
    data = tmp_path / "data"
    overlay = data / "config" / "admin_config_overlay.yaml"
    fragments = tmp_path / "config" / "fragments"
    fragments.mkdir(parents=True)
    (fragments / "10-general.yaml").write_text(
        "general:\n  platform_name: Test Factory\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.setenv("AIFACTORY_CONFIG_YAML", str(overlay))
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(fragments))

    ensure_primary_config_overlay()

    assert overlay.is_file()
    mirror = data / "state" / "config.json"
    assert mirror.is_file()
    doc = json.loads(mirror.read_text(encoding="utf-8"))
    assert doc["general"]["platform_name"] == "Test Factory"


def test_patch_primary_overlay_updates_yaml_and_mirror(tmp_path, monkeypatch):
    data = tmp_path / "data"
    overlay = data / "config" / "admin_config_overlay.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("general:\n  factory_on_hold: true\n", encoding="utf-8")

    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.setenv("AIFACTORY_CONFIG_YAML", str(overlay))
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(tmp_path / "missing"))

    patch_primary_overlay({"general.factory_on_hold": False})

    saved = yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert saved["general"]["factory_on_hold"] is False
    mirror = json.loads((data / "state" / "config.json").read_text(encoding="utf-8"))
    assert mirror["general"]["factory_on_hold"] is False
