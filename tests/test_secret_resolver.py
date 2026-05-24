"""Tests for unified secret resolution."""

from __future__ import annotations

import os

import pytest

from security import secret_resolver as sr


def test_get_secret_from_env(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "env")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-env")
    assert sr.get_secret("DEEPSEEK_API_KEY", env_names=["DEEPSEEK_API_KEY"]) == "sk-test-env"


def test_get_secret_from_file(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "env")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm_dir = tmp_path / "secrets" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "deepseek_api_key").write_text("sk-from-file\n", encoding="utf-8")
    monkeypatch.setattr("core.paths.data_root", lambda: tmp_path)
    assert sr.get_secret("DEEPSEEK_API_KEY", env_names=["DEEPSEEK_API_KEY"]) == "sk-from-file"


def test_resolve_backend_auto_falls_back_to_env_without_vault(monkeypatch, tmp_path):
    monkeypatch.delenv("AIFACTORY_HASHICORP_VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "auto")
    monkeypatch.setattr("core.paths.encrypted_vault_path", lambda: tmp_path / "missing-vault.json")
    assert sr._resolve_backend() == "env"


def test_export_llm_keys_to_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "env")
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    llm_dir = tmp_path / "secrets" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "together_api_key").write_text("together-sk-test\n", encoding="utf-8")
    monkeypatch.setattr("core.paths.data_root", lambda: tmp_path)
    count = sr.export_llm_keys_to_env()
    assert count == 1
    assert os.environ.get("TOGETHER_API_KEY") == "together-sk-test"


def test_hashicorp_configured_requires_addr_and_token(monkeypatch):
    monkeypatch.delenv("AIFACTORY_HASHICORP_VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    assert sr._hashicorp_configured() is False
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.com")
    monkeypatch.setenv("VAULT_TOKEN", "hvs.test")
    assert sr._hashicorp_configured() is True
