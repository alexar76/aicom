"""Admin quality YAML + env resolution for per-product LLM cap."""

from __future__ import annotations

import pytest

from core.quality_settings import bump_quality_cache_after_config_write, max_pipeline_cost_usd


def test_max_pipeline_cost_from_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.delenv("AIFACTORY_MAX_PIPELINE_COST_USD", raising=False)
    cfg_dir = tmp_path / "data" / "config"
    cfg_dir.mkdir(parents=True)
    overlay = cfg_dir / "admin_config_overlay.yaml"
    overlay.write_text(
        "quality:\n  max_pipeline_cost_usd: 25.5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_CONFIG_YAML", str(overlay))
    bump_quality_cache_after_config_write()
    assert max_pipeline_cost_usd() == pytest.approx(25.5)


def test_env_overrides_yaml_max_pipeline_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_MAX_PIPELINE_COST_USD", "40")
    cfg_dir = tmp_path / "data" / "config"
    cfg_dir.mkdir(parents=True)
    overlay = cfg_dir / "admin_config_overlay.yaml"
    overlay.write_text(
        "quality:\n  max_pipeline_cost_usd: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_CONFIG_YAML", str(overlay))
    bump_quality_cache_after_config_write()
    assert max_pipeline_cost_usd() == pytest.approx(40.0)
