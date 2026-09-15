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


# ── Dev escape hatches that must not survive into production ──────────────────
#
# Each of these was reachable on a live host before this gate existed. RELAXED is
# hardcoded to "1" in independent/verified-execution-hub/docker-compose.yml, and the
# other two default off but are one stale .env away from being on.

_ESCAPE_HATCHES = (
    ("AIMARKET_SUPPLY_SECURITY_RELAXED", "collateral"),
    ("AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", "proof of control"),
    ("AIMARKET_SANDBOX_STUB_INVOKE", "canned demo output"),
)


@pytest.fixture
def _clean_prod_env(monkeypatch):
    """Production mode with the unrelated hatches off, so one flag is under test."""
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    for var in (
        "AIFACTORY_DEV_BOOTSTRAP_PASSWORD",
        "AIFACTORY_DEMO_READONLY",
        "AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL",
        "AIFACTORY_SSO_TRUSTED_HEADER",
    ):
        monkeypatch.delenv(var, raising=False)
    for name, _ in _ESCAPE_HATCHES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("flag,phrase", _ESCAPE_HATCHES)
def test_production_refuses_dev_escape_hatch(monkeypatch, _clean_prod_env, flag, phrase):
    issues = guard.production_startup_issues()
    assert not any(flag in i for i in issues), f"{flag} flagged while unset"

    monkeypatch.setenv(flag, "1")
    issues = guard.production_startup_issues()
    matched = [i for i in issues if flag in i]
    assert matched, f"{flag}=1 did not block production startup"
    # The message has to say what actually goes wrong, not just name the variable —
    # an operator reading a boot refusal at 3am gets one chance to understand it.
    assert any(phrase in i for i in matched), matched


@pytest.mark.parametrize("flag,_phrase", _ESCAPE_HATCHES)
def test_escape_hatches_are_refused_by_the_standalone_hub_too(
    monkeypatch, _clean_prod_env, flag, _phrase
):
    """The hub image ships without `security`, so it has its own copy of this gate.

    The standalone fallback in aimarket_hub.cli is the ONLY gate that runs on
    independent/ and on any hub installed from PyPI. A flag added to
    prod_startup_guard alone would be a flag that production hub never checks —
    the "second entry point missing the first's guard" shape this ecosystem has
    shipped more than once. Asserted by calling both gates, not by reading either
    one's source, so renaming the list cannot silently detach the check.
    """
    cli = pytest.importorskip("aimarket_hub.cli")
    assert hasattr(cli, "prod_forbidden_flags_active"), (
        "aimarket_hub.cli is missing prod_forbidden_flags_active — the GitHub "
        "aimarket-hub satellite is behind the monorepo. Publish it with "
        "./scripts/publish_all_repos.sh --satellite aimarket-hub before "
        "factory CI can assert standalone-hub / factory-guard parity."
    )

    monkeypatch.delenv(flag, raising=False)
    assert flag not in cli.prod_forbidden_flags_active()

    monkeypatch.setenv(flag, "1")
    assert flag in cli.prod_forbidden_flags_active()
    assert any(flag in i for i in guard.production_startup_issues())


@pytest.mark.parametrize("spelling", ["true", "YES", "On", " 1 "])
def test_escape_hatch_truthiness_is_wider_than_the_runtime(
    monkeypatch, _clean_prod_env, spelling
):
    """`RELAXED=true` relaxes nothing (the runtime tests `== "1"`), and still refuses.

    Booting is the wrong response to an operator who plainly meant to switch a
    hatch on: either the flag works and production is unsafe, or it does not and
    the host is not configured the way whoever wrote that line believes it is.
    """
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", spelling)
    issues = guard.production_startup_issues()
    assert any("AIMARKET_SUPPLY_SECURITY_RELAXED" in i for i in issues)
