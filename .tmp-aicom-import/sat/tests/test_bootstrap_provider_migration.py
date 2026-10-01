"""Auto-migration of legacy LLM provider ids on bootstrap."""

from __future__ import annotations

import yaml

from llm.bootstrap_providers import auto_migrate_provider_ids, migrate_model_providers_yaml
from llm.pricing_estimate import migrate_llm_calls_provider_ids


def test_migrate_model_providers_yaml_renames_legacy_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    cfg = tmp_path / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        yaml.safe_dump(
            {
                "default_provider": "deep-seek",
                "providers": {"deep-seek": {"enabled": True}},
                "routing_rules": [{"preferred_provider": "deep-seek"}],
            }
        ),
        encoding="utf-8",
    )
    stats = migrate_model_providers_yaml(cfg)
    assert stats["keys_renamed"] == 1
    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "deepseek_api" in loaded["providers"]
    assert loaded["default_provider"] == "deepseek_api"
    assert loaded["routing_rules"][0]["preferred_provider"] == "deepseek_api"


def test_auto_migrate_provider_ids_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_AUTO_MIGRATE_PROVIDER_IDS", "1")
    log = tmp_path / "logs" / "llm_calls.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(
        '{"provider":"deep-seek","estimated_cost_usd":0.01,"tokens":10}\n',
        encoding="utf-8",
    )
    out = auto_migrate_provider_ids(migrate_yaml=False)
    assert out["jsonl"]["migrated"] == 1
    line = log.read_text(encoding="utf-8").strip()
    assert '"provider": "deepseek_api"' in line or '"provider":"deepseek_api"' in line
