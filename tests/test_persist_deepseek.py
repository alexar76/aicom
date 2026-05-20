"""DeepSeek provider persistence."""

from __future__ import annotations

import yaml

from llm.persist_deepseek import (
    DEEPSEEK_PROVIDER_ID,
    DEFAULT_HEAVY,
    DEFAULT_LIGHT,
    sync_deepseek_provider_config,
)


def test_sync_deepseek_writes_config(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cfg = data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        yaml.safe_dump(
            {
                "default_provider": "lm_studio",
                "providers": {
                    "lm_studio": {"enabled": True},
                    DEEPSEEK_PROVIDER_ID: {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = sync_deepseek_provider_config(
        api_key="sk-test-key",
        reset_circuit=False,
        disable_local_fallbacks=True,
    )
    assert result["ok"] is True

    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert loaded["default_provider"] == DEEPSEEK_PROVIDER_ID
    ds = loaded["providers"][DEEPSEEK_PROVIDER_ID]
    assert ds["models"]["heavy"] == DEFAULT_HEAVY
    assert ds["models"]["light"] == DEFAULT_LIGHT
    assert ds["api_key"] == "sk-test-key"
    assert loaded["providers"]["lm_studio"]["enabled"] is False

    secret = data / "secrets" / "llm" / "deepseek_api_key"
    assert secret.read_text(encoding="utf-8").strip() == "sk-test-key"
