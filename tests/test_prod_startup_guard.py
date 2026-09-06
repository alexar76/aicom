"""Production mode must refuse known demo passwords."""

from __future__ import annotations

import json

import pytest

from security import prod_startup_guard as guard


def test_production_mode_off_allows_demo_env(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.setenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", "demo123")
    assert guard.production_startup_issues() == []


def test_production_rejects_dev_bootstrap_demo_password(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", "demo123")
    issues = guard.production_startup_issues()
    assert any("AIFACTORY_DEV_BOOTSTRAP_PASSWORD" in i for i in issues)


def test_production_rejects_demo_readonly_combo(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    issues = guard.production_startup_issues()
    assert any("DEMO_READONLY" in i for i in issues)


def test_production_rejects_stored_demo123_hash(monkeypatch, tmp_path):
    from web.backend.core.security import SecurityManager

    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)

    sec = SecurityManager(audit_log_path=str(tmp_path / "audit.jsonl"))
    admin_json = tmp_path / "admin.json"
    admin_json.write_text(
        json.dumps({"username": "admin", "password_hash": sec.hash_password("demo123")}),
        encoding="utf-8",
    )
    monkeypatch.setattr("security.prod_startup_guard.legacy_admin_path", lambda: admin_json)
    monkeypatch.setattr(
        "security.prod_startup_guard.admin_users_path",
        lambda: tmp_path / "missing-users.json",
    )

    issues = guard.production_startup_issues()
    assert any("weak password" in i for i in issues)


def test_production_rejects_ephemeral_jwt(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "1")
    issues = guard.production_startup_issues()
    assert any("EPHEMERAL" in i for i in issues)


def test_production_off_allows_ephemeral_jwt(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.setenv("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "1")
    assert guard.production_startup_issues() == []


def test_production_rejects_broad_sso_cidrs(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_HEADER", "X-Remote-User")
    monkeypatch.delenv("AIFACTORY_SSO_TRUSTED_CIDRS", raising=False)
    issues = guard.production_startup_issues()
    assert any("AIFACTORY_SSO_TRUSTED_CIDRS" in i for i in issues)


def test_production_allows_narrow_sso_cidr(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_HEADER", "X-Remote-User")
    monkeypatch.setenv("AIFACTORY_SSO_TRUSTED_CIDRS", "10.0.0.10/32")
    issues = guard.production_startup_issues()
    assert not any("AIFACTORY_SSO_TRUSTED_CIDRS" in i for i in issues)


def test_production_rejects_sqlite_backend(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("USE_SQLITE", "true")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "0")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr(
        "llm.startup_validation.production_llm_key_issues",
        lambda: [],
    )
    issues = guard.production_startup_issues()
    assert any("SQLite" in i for i in issues)


def test_production_rejects_missing_llm_keys(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.delenv("USE_SQLITE", raising=False)
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "postgres")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "0")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr(
        "llm.startup_validation.production_llm_key_issues",
        lambda: ["No API keys configured for any enabled LLM provider."],
    )
    issues = guard.production_startup_issues()
    assert any("No API keys" in i for i in issues)


def test_production_requires_2fa_when_flag_set(monkeypatch, tmp_path):
    import sys
    import types

    fake_wa = types.ModuleType("security.webauthn_admin")
    fake_wa.webauthn_is_enabled = lambda cfg: False
    monkeypatch.setitem(sys.modules, "security.webauthn_admin", fake_wa)

    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_REQUIRE_ADMIN_2FA", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.delenv("USE_SQLITE", raising=False)
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "postgres")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "0")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr("llm.startup_validation.production_llm_key_issues", lambda: [])
    monkeypatch.setattr("security.zk_artifacts.production_zk_issues", lambda: [])

    admin_json = tmp_path / "admin.json"
    admin_json.write_text(json.dumps({"username": "admin", "totp_enabled": False}), encoding="utf-8")
    monkeypatch.setattr("security.prod_startup_guard.legacy_admin_path", lambda: admin_json)

    issues = guard.production_startup_issues()
    assert any("AIFACTORY_REQUIRE_ADMIN_2FA" in i for i in issues)


def test_production_zk_groth16_missing_artifacts(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_REQUIRE_ADMIN_2FA", raising=False)
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.delenv("USE_SQLITE", raising=False)
    monkeypatch.setenv("PIPELINE_DB_BACKEND", "postgres")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIMARKET_ZK_SIMULATED", "0")
    monkeypatch.setenv("AIMARKET_ZK_BACKEND", "groth16")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr("llm.startup_validation.production_llm_key_issues", lambda: [])

    issues = guard.production_startup_issues()
    assert any("AIMARKET_ZK_WASM" in i or "snarkjs" in i for i in issues)


def test_production_rejects_sandbox_on_local_docker(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "1")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    issues = guard.production_startup_issues()
    assert any("AIFACTORY_SANDBOX_REQUIRE_CONTAINER" in i for i in issues)


def test_production_allows_sandbox_with_remote_docker_host(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "1")
    monkeypatch.setenv("DOCKER_HOST", "tcp://sandbox-host:2376")
    issues = guard.production_startup_issues()
    assert not any("AIFACTORY_SANDBOX_REQUIRE_CONTAINER" in i for i in issues)


def test_production_rejects_host_docker_socket(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("AIFACTORY_USE_HOST_DOCKER", "1")
    issues = guard.production_startup_issues()
    assert any("AIFACTORY_USE_HOST_DOCKER" in i for i in issues)


def test_production_off_allows_host_docker_socket(monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    monkeypatch.setenv("AIFACTORY_USE_HOST_DOCKER", "1")
    assert guard.production_startup_issues() == []


def test_production_rejects_anvil_payment_recipient(monkeypatch):
    """An Anvil/Hardhat dev address is a live, working recipient whose private key is
    public — the money arrives and anyone can sweep it. It must fail closed exactly
    like an unset recipient, not pass because it looks like a valid address.
    """
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.delenv("AIFACTORY_DEV_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_CONTRACT", "0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017")
    # Anvil account #0 — printed by every local node, private key in every tutorial.
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
    issues = guard.production_startup_issues()
    assert any("AIMARKET_PAYMENT_RECIPIENT" in i for i in issues)


def test_production_allows_a_real_payment_recipient(monkeypatch):
    """The dev-address blocklist must not reject an ordinary wallet."""
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "0")
    monkeypatch.setenv("AIFACTORY_AI_MARKET_CONTRACT", "0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x029B4B0e5D8e3F1a2C7d9E4f6A8b1C3d5E7f8eb3")
    issues = guard.production_startup_issues()
    assert not any("AIMARKET_PAYMENT_RECIPIENT" in i for i in issues)
