"""Layered config: primary overlay path vs bundled fragments directory."""

from __future__ import annotations

from pathlib import Path

import yaml

from core.config_merge import config_fragments_dir, load_merged_config


def test_config_fragments_dir_default():
    primary = Path("/app/config.yaml")
    assert config_fragments_dir(primary) == Path("/app/config/fragments")


def test_config_fragments_dir_env_override(monkeypatch):
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", "/opt/aicom/fragments")
    assert config_fragments_dir(Path("/data/writable.yaml")) == Path("/opt/aicom/fragments")


def test_load_merged_overlay_under_arbitrary_dir_uses_fragments_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parent.parent
    frags = repo_root / "config" / "fragments"
    assert frags.is_dir(), "repo must ship config/fragments for this test"

    overlay = tmp_path / "data" / "config" / "admin_config_overlay.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(
        yaml.dump({"general": {"published_site_head_html": "<script id=\"x\">1</script>"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(frags))
    merged = load_merged_config(overlay)

    assert merged.get("general", {}).get("published_site_head_html") == '<script id="x">1</script>'
    # At least one known fragment default should still be present
    assert "storefront" in merged or "web" in merged
