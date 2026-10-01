"""Tests for production LLM key validation."""

from __future__ import annotations

import yaml

from llm import startup_validation as sv


def test_production_llm_key_issues_missing_config(tmp_path, monkeypatch):
    cfg = tmp_path / "model_providers.yaml"
    monkeypatch.setattr(sv, "model_providers_path", lambda: cfg)
    issues = sv.production_llm_key_issues()
    assert len(issues) == 1
    assert "missing" in issues[0].lower()


def test_production_llm_key_issues_no_keys(tmp_path, monkeypatch):
    cfg = tmp_path / "model_providers.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "default_provider": "deepseek_api",
                "providers": {
                    "deepseek_api": {
                        "enabled": True,
                        "api_key_env": "DEEPSEEK_API_KEY",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sv, "model_providers_path", lambda: cfg)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    issues = sv.production_llm_key_issues()
    assert any("No API keys" in i for i in issues)


def test_production_llm_key_issues_env_ok(tmp_path, monkeypatch):
    cfg = tmp_path / "model_providers.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "default_provider": "deepseek_api",
                "providers": {
                    "deepseek_api": {
                        "enabled": True,
                        "api_key_env": "DEEPSEEK_API_KEY",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sv, "model_providers_path", lambda: cfg)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real-key-not-placeholder")
    assert sv.production_llm_key_issues() == []
