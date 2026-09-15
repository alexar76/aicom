"""Tests for OpenRouter persist helper (emergency DeepSeek failover)."""

from __future__ import annotations

import yaml

from llm.persist_openrouter import OPENROUTER_PROVIDER_ID, sync_openrouter_provider_config


def test_sync_openrouter_writes_provider_and_default(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cfg = data / "config"
    cfg.mkdir(parents=True)
    (cfg / "model_providers.yaml").write_text(
        yaml.safe_dump(
            {
                "default_provider": "deepseek_api",
                "providers": {"deepseek_api": {"enabled": True}},
                "routing_rules": [
                    {"task_type": "code_generation", "preferred_provider": "deepseek_api"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.chdir(tmp_path)

    result = sync_openrouter_provider_config(api_key="sk-or-test", reset_circuit=False)
    assert result["ok"] is True

    raw = yaml.safe_load((cfg / "model_providers.yaml").read_text(encoding="utf-8"))
    assert raw["default_provider"] == OPENROUTER_PROVIDER_ID
    block = raw["providers"][OPENROUTER_PROVIDER_ID]
    assert block["base_url"] == "https://openrouter.ai/api/v1"
    assert block["models"]["heavy"] == "minimax/minimax-m3"
    assert (data / "secrets" / "llm" / "openrouter_api_key").read_text().strip() == "sk-or-test"
    assert raw["routing_rules"][0]["preferred_provider"] == OPENROUTER_PROVIDER_ID


def test_sync_openrouter_missing_key():
    assert sync_openrouter_provider_config(api_key="").get("ok") is False
