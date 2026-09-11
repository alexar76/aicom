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


def test_sync_deepseek_preserves_admin_capabilities(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cfg = data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        yaml.safe_dump(
            {
                "default_provider": DEEPSEEK_PROVIDER_ID,
                "providers": {
                    DEEPSEEK_PROVIDER_ID: {
                        "enabled": True,
                        "capabilities": {
                            "context_window": 64000,
                            "context_window_light": 32000,
                            "max_tokens": 16000,
                        },
                        "models": {"heavy": "custom-heavy", "light": "custom-light"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))

    sync_deepseek_provider_config(api_key="sk-keep", reset_circuit=False, disable_local_fallbacks=False)

    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ds = loaded["providers"][DEEPSEEK_PROVIDER_ID]
    assert ds["capabilities"]["context_window"] == 64000
    assert ds["capabilities"]["context_window_light"] == 32000
    assert ds["models"]["heavy"] == "custom-heavy"
    assert ds["api_key"] == "sk-keep"
