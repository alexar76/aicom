"""Provider restart and storage regressions use only disposable canary values."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from starlette.requests import Request

from llm.provider_secrets import (
    provider_secret_reference,
    read_provider_secret,
    resolve_provider_api_key,
    save_provider_config,
    write_provider_secret,
)

CANARY = "disposable-provider-credential-for-storage-regression"
REPLACEMENT = "different-disposable-provider-credential"


@pytest.fixture(autouse=True)
def private_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_SECRETS_BACKEND", "env")
    for name in ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "AUDIT_PROVIDER_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "data"


def request_with_json(body):
    raw = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request({
        "type": "http", "method": "PUT", "path": "/providers/custom",
        "headers": [(b"content-type", b"application/json")],
        "app": SimpleNamespace(state=SimpleNamespace()),
    }, receive)


def test_private_from_creation_and_atomic_replacement(private_data, monkeypatch):
    real_open = os.open
    observed = []

    def inspect_open(path, flags, mode=0o777, **kwargs):
        fd = real_open(path, flags, mode, **kwargs)
        if flags & os.O_CREAT:
            observed.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return fd

    monkeypatch.setattr(os, "open", inspect_open)
    previous = os.umask(0)
    try:
        path = write_provider_secret("custom_key", CANARY)
        first_inode = path.stat().st_ino
        write_provider_secret("custom_key", REPLACEMENT)
    finally:
        os.umask(previous)
    assert observed and all(mode == 0o600 for mode in observed)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.stat().st_ino != first_inode
    assert read_provider_secret("custom_key") == REPLACEMENT
    assert sorted(p.name for p in path.parent.iterdir()) == ["custom_key"]


@pytest.mark.parametrize("reference", ["../outside", "/etc/passwd", "..", ".", "dir/key", "", "a\\b", "a\x00b"])
def test_rejects_config_file_path_injection(reference):
    with pytest.raises(ValueError):
        read_provider_secret(reference)
    with pytest.raises(ValueError):
        write_provider_secret(reference, CANARY)


@pytest.mark.parametrize("operation", ["read", "write"])
def test_rejects_secret_file_symlink(private_data, tmp_path, operation):
    directory = private_data / "secrets" / "llm"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("outside-must-remain-unchanged")
    (directory / "custom_key").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        if operation == "read":
            read_provider_secret("custom_key")
        else:
            write_provider_secret("custom_key", CANARY)
    assert outside.read_text() == "outside-must-remain-unchanged"


@pytest.mark.parametrize("component", ["secrets", "llm"])
def test_rejects_secret_parent_symlink(private_data, tmp_path, component):
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = private_data if component == "secrets" else private_data / "secrets"
    parent.mkdir(parents=True)
    (parent / component).symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        write_provider_secret("custom_key", CANARY)
    assert list(outside.iterdir()) == []


def test_rejects_hardlinks_and_devices(private_data, tmp_path):
    directory = private_data / "secrets" / "llm"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text(CANARY)
    os.link(outside, directory / "custom_key")
    with pytest.raises(ValueError):
        read_provider_secret("custom_key")
    with pytest.raises(ValueError):
        write_provider_secret("custom_key", REPLACEMENT)
    (directory / "custom_key").unlink()
    os.mkfifo(directory / "custom_key")
    with pytest.raises(ValueError):
        read_provider_secret("custom_key")
    with pytest.raises(ValueError):
        write_provider_secret("custom_key", CANARY)


def test_existing_file_permissions_tightened_on_read():
    path = write_provider_secret("custom_key", CANARY)
    path.chmod(0o644)
    assert read_provider_secret("custom_key") == CANARY
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("provider_name", ["deepseek_api", "openrouter_api"])
@pytest.mark.asyncio
async def test_sync_key_survives_restart_without_env_or_yaml_duplication(private_data, monkeypatch, provider_name):
    from llm.persist_deepseek import sync_deepseek_provider_config
    from llm.persist_openrouter import sync_openrouter_provider_config
    from llm.router import LLMRouter
    from llm.startup_validation import _key_resolved

    cfg = private_data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({"providers": {provider_name: {
        "enabled": True, "api_key": CANARY,
        "models": {"heavy": "admin-custom-model"},
    }}}))
    sync = sync_deepseek_provider_config if provider_name == "deepseek_api" else sync_openrouter_provider_config
    assert sync(api_key=REPLACEMENT, reset_circuit=False)["ok"]
    raw = cfg.read_text()
    assert CANARY not in raw and REPLACEMENT not in raw
    config = yaml.safe_load(raw)
    provider = config["providers"][provider_name]
    assert provider["models"]["heavy"] == "admin-custom-model"
    assert provider["api_key"] is None
    monkeypatch.delenv(provider["api_key_env"])
    assert resolve_provider_api_key(provider) == REPLACEMENT
    assert _key_resolved(provider)
    router = LLMRouter(cfg)
    try:
        assert router.providers[provider_name].api_key == REPLACEMENT
        assert router._provider_has_credentials(provider_name)
        assert router.providers[provider_name]._client.headers["Authorization"] == "Bearer " + REPLACEMENT
    finally:
        for loaded in router.providers.values():
            await loaded._client.aclose()
    assert sync(reset_circuit=False)["ok"]
    assert read_provider_secret(provider["api_key_file"]) == REPLACEMENT


def test_env_override_and_file_fallback_are_consistent(monkeypatch):
    write_provider_secret("custom_key", CANARY)
    provider = {"api_key_env": "AUDIT_PROVIDER_KEY", "api_key_file": "custom_key"}
    assert resolve_provider_api_key(provider) == CANARY
    monkeypatch.setenv("AUDIT_PROVIDER_KEY", REPLACEMENT)
    assert resolve_provider_api_key(provider) == REPLACEMENT


@pytest.mark.asyncio
async def test_custom_admin_create_update_restart_and_no_secret_response(private_data, monkeypatch):
    from llm.router import LLMRouter
    from web.backend.api.admin.dashboard import routes_providers as routes

    cfg = private_data / "config" / "model_providers.yaml"
    monkeypatch.setattr(routes, "model_providers_path", lambda: cfg)
    created = await routes.create_provider(request_with_json({
        "name": "Custom Cloud", "api_key": CANARY,
        "base_url": "https://provider.example/v1",
        "models": {"heavy": "custom-heavy", "light": "custom-light"},
    }))
    assert created["name"] == "custom_cloud"
    config = yaml.safe_load(cfg.read_text())
    assert CANARY not in cfg.read_text()
    reference = config["providers"]["custom_cloud"]["api_key_file"]
    assert read_provider_secret(reference) == CANARY
    # Existing unknown fields may contain credentials; the public update result
    # must not reflect those values or an newly submitted API key.
    config["providers"]["custom_cloud"]["extra_headers"] = {"X-Secret": "disposable-private-header"}
    save_provider_config(cfg, config)
    result = await routes.update_provider("custom_cloud", request_with_json({"api_key": REPLACEMENT}))
    assert result["provider"]["api_key_configured"]
    encoded = json.dumps(result)
    assert "api_key\"" not in encoded
    assert CANARY not in encoded and REPLACEMENT not in encoded
    assert "disposable-private-header" not in encoded
    assert read_provider_secret(reference) == REPLACEMENT
    # A settings-only change preserves the key across reload and restart.
    await routes.update_provider_models("custom_cloud", request_with_json({"heavy": "new-heavy"}))
    await routes.toggle_provider("custom_cloud", request_with_json({"enabled": False}))
    await routes.toggle_provider("custom_cloud", request_with_json({"enabled": True}))
    router = LLMRouter(cfg)
    try:
        assert router.providers["custom_cloud"].api_key == REPLACEMENT
        assert router.providers["custom_cloud"].model == "new-heavy"
    finally:
        for loaded in router.providers.values():
            await loaded._client.aclose()
    assert REPLACEMENT not in cfg.read_text()


def test_legacy_inline_migration_retains_identity_and_sanitizes_backup(private_data, monkeypatch):
    from llm.bootstrap_providers import ensure_model_providers_file, migrate_model_providers_yaml

    cfg = private_data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({"providers": {"deep-seek": {
        "enabled": True, "api_key": CANARY, "api_key_env": "AUDIT_PROVIDER_KEY",
    }}, "default_provider": "deep-seek"}))
    monkeypatch.setenv("AUDIT_PROVIDER_KEY", REPLACEMENT)
    assert ensure_model_providers_file(cfg)
    assert CANARY not in cfg.read_text()
    assert migrate_model_providers_yaml(cfg)["keys_renamed"] == 1
    config = yaml.safe_load(cfg.read_text())
    provider = config["providers"]["deepseek_api"]
    assert provider["api_key_env"] is None
    assert resolve_provider_api_key(provider) == CANARY
    assert CANARY not in cfg.with_suffix(".yaml.bak").read_text()


def test_startup_sync_preserves_legacy_provider_identity(private_data):
    from llm.persist_deepseek import sync_deepseek_provider_config

    cfg = private_data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({"providers": {"deep-seek": {
        "enabled": True, "api_key": CANARY,
    }}}))
    assert sync_deepseek_provider_config(reset_circuit=False)["ok"]
    provider = yaml.safe_load(cfg.read_text())["providers"]["deepseek_api"]
    assert resolve_provider_api_key(provider) == CANARY
    assert CANARY not in cfg.read_text()


@pytest.mark.asyncio
async def test_admin_health_and_prompt_use_private_key_and_redact_echo(private_data, monkeypatch):
    import httpx
    from web.backend.api.admin.dashboard import routes_providers as routes

    cfg = private_data / "config" / "model_providers.yaml"
    monkeypatch.setattr(routes, "model_providers_path", lambda: cfg)
    save_provider_config(cfg, {"providers": {"custom": {
        "enabled": True, "api_key": CANARY,
        "base_url": "https://provider.example/v1", "models": {"heavy": "custom-heavy"},
    }}})
    probed = []

    def probe(**kwargs):
        probed.append(kwargs["api_key"])
        return ["custom-heavy"]

    monkeypatch.setattr(routes, "_provider_models_probe", probe)
    public = await routes.get_providers()
    assert probed == [CANARY]
    assert CANARY not in json.dumps(public)
    monkeypatch.setattr(routes, "_assert_url_safe_for_outbound", lambda url: None)

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json, headers):
            assert headers["Authorization"] == "Bearer " + CANARY
            return SimpleNamespace(status_code=401, text="Echoed credential: " + CANARY)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = await routes.test_provider("custom", request_with_json({}))
    assert result["status_code"] == 401
    assert CANARY not in json.dumps(result)


def test_provider_names_cannot_choose_private_file_paths(private_data):
    cfg = private_data / "config" / "providers.yaml"
    name = "../../outside"
    config = save_provider_config(cfg, {"providers": {name: {"api_key": CANARY}}})
    reference = config["providers"][name]["api_key_file"]
    assert reference == provider_secret_reference(name)
    assert "/" not in reference
    assert resolve_provider_api_key(config["providers"][name]) == CANARY


def test_compromised_fingerprint_rejected_before_private_write(monkeypatch):
    import hashlib
    from security import compromised_credentials

    monkeypatch.setattr(compromised_credentials, "COMPROMISED_SHA256", frozenset({hashlib.sha256(CANARY.encode()).hexdigest()}))
    with pytest.raises(ValueError) as exc:
        write_provider_secret("custom_key", CANARY)
    assert CANARY not in str(exc.value)


def test_malformed_inline_config_does_not_echo_key_in_logs_or_validation(private_data, caplog, monkeypatch):
    from llm.router import LLMRouter
    from llm import startup_validation

    cfg = private_data / "config" / "model_providers.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("providers:\n  custom:\n    api_key: [" + CANARY + "\n")
    monkeypatch.setattr(startup_validation, "model_providers_path", lambda: cfg)
    assert not LLMRouter(cfg).providers
    issues = startup_validation.production_llm_key_issues()
    assert issues
    assert CANARY not in json.dumps(issues)
    assert CANARY not in caplog.text
