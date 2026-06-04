"""Tests for opt-in critical-task escalation across providers.

Covers the setting reader, the critical-task classifier, and the router's
escalation target selection / model re-binding.
"""

from __future__ import annotations

import pytest

from llm.provider import GenerationConfig, ProviderStatus
from llm.router import LLMRouter


class _FakeHealth:
    def __init__(self, status=ProviderStatus.ONLINE):
        self.status = status
        self.latency_ms = 1.0


class _FakeProvider:
    def __init__(self, status=ProviderStatus.ONLINE):
        self.health = _FakeHealth(status)


def _router_with_providers(monkeypatch):
    # Avoid env bleed from other tests.
    monkeypatch.delenv("AIFACTORY_LLM_DAILY_COST_CAP_USD", raising=False)
    monkeypatch.delenv("AIFACTORY_LLM_MONTHLY_COST_CAP_USD", raising=False)
    router = LLMRouter()
    router.default_provider = "deepseek_api"
    router.providers = {
        "deepseek_api": _FakeProvider(),
        "anthropic_cloud": _FakeProvider(),
        "no_key_cloud": _FakeProvider(),
        "local": _FakeProvider(),
    }
    router._provider_configs = {
        "deepseek_api": {"priority": 10, "api_key": "sk-deep", "provider_type": "openai_compatible",
                         "models": {"heavy": "deepseek-v4-pro", "light": "deepseek-v4-flash"}},
        "anthropic_cloud": {"priority": 8, "api_key": "sk-ant", "provider_type": "anthropic",
                            "models": {"heavy": "claude-x", "light": "claude-haiku"}},
        # Higher priority but NO key configured → must be skipped.
        "no_key_cloud": {"priority": 99, "provider_type": "openai_compatible",
                         "models": {"heavy": "big-model"}},
        "local": {"priority": 2, "provider_type": "local_ollama",
                  "models": {"heavy": "qwen2.5:14b"}},
    }
    return router


# ── setting reader ────────────────────────────────────────────────────────────

def test_escalation_setting_default_off(monkeypatch):
    from core.throughput_limits import effective_llm_critical_escalation_enabled

    monkeypatch.delenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", raising=False)
    # No config file in test env → defaults to False.
    assert effective_llm_critical_escalation_enabled() is False


def test_escalation_setting_env_on(monkeypatch):
    from core.throughput_limits import effective_llm_critical_escalation_enabled

    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    assert effective_llm_critical_escalation_enabled() is True
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "off")
    assert effective_llm_critical_escalation_enabled() is False


# ── critical classifier ───────────────────────────────────────────────────────

def test_is_critical_task():
    from llm.cost_guard import is_critical_task

    assert is_critical_task("security_scan")
    assert is_critical_task("code_generation")
    assert is_critical_task("CODE_GENERATION")  # case-insensitive
    assert not is_critical_task("marketing_copy")
    assert not is_critical_task(None)


# ── credential check ──────────────────────────────────────────────────────────

def test_provider_has_credentials(monkeypatch):
    router = _router_with_providers(monkeypatch)
    assert router._provider_has_credentials("deepseek_api")       # literal api_key
    assert router._provider_has_credentials("local")              # local needs none
    assert not router._provider_has_credentials("no_key_cloud")   # no key wired


def test_provider_credentials_via_env(monkeypatch):
    router = _router_with_providers(monkeypatch)
    router._provider_configs["no_key_cloud"]["api_key_env"] = "SOME_KEY_ENV"
    assert not router._provider_has_credentials("no_key_cloud")
    monkeypatch.setenv("SOME_KEY_ENV", "sk-from-env")
    assert router._provider_has_credentials("no_key_cloud")


# ── escalation target selection ───────────────────────────────────────────────

def test_no_escalation_when_disabled(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "0")
    router = _router_with_providers(monkeypatch)
    assert router._critical_escalation_target("security_scan", {"deepseek_api"}) is None


def test_no_escalation_for_noncritical(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    assert router._critical_escalation_target("marketing_copy", {"deepseek_api"}) is None


def test_escalation_picks_highest_priority_credentialed(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    # deepseek already tried; no_key_cloud (prio 99) skipped → anthropic (8) wins over local (2).
    target = router._critical_escalation_target("security_scan", {"deepseek_api"})
    assert target == "anthropic_cloud"


def test_escalation_skips_already_tried(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    # Both cloud options exhausted → falls to local.
    target = router._critical_escalation_target("security_scan", {"deepseek_api", "anthropic_cloud"})
    assert target == "local"


def test_escalation_none_when_all_tried(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    tried = {"deepseek_api", "anthropic_cloud", "local", "no_key_cloud"}
    assert router._critical_escalation_target("security_scan", tried) is None


# ── _next_failover wiring ─────────────────────────────────────────────────────

def test_next_failover_uses_escalation_when_no_rule_fallback(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    router.routing_rules = [{"task_type": "security_scan", "model_role": "heavy"}]  # no fallback_provider
    nxt = router._next_failover("security_scan", "deepseek_api", {"deepseek_api"})
    assert nxt == "anthropic_cloud"


def test_next_failover_prefers_rule_fallback(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    router = _router_with_providers(monkeypatch)
    router.routing_rules = [
        {"task_type": "security_scan", "model_role": "heavy", "fallback_provider": "local"}
    ]
    nxt = router._next_failover("security_scan", "deepseek_api", {"deepseek_api"})
    assert nxt == "local"  # explicit rule fallback wins over escalation ranking


# ── model re-bind across providers ────────────────────────────────────────────

def test_rebind_model_for_provider(monkeypatch):
    router = _router_with_providers(monkeypatch)
    cfg = GenerationConfig(model_role="heavy", task_type="security_scan")
    router._rebind_model_for_provider("anthropic_cloud", cfg, "security_scan", caller_override=None)
    assert cfg.model_override == "claude-x"  # anthropic's heavy, not deepseek's


def test_rebind_honors_caller_override(monkeypatch):
    router = _router_with_providers(monkeypatch)
    cfg = GenerationConfig(model_role="heavy", task_type="security_scan", model_override="deepseek-v4-pro")
    router._rebind_model_for_provider("anthropic_cloud", cfg, "security_scan", caller_override="pinned-model")
    assert cfg.model_override == "pinned-model"


# ── admin panel surface (settings UI backend) ─────────────────────────────────

def test_panel_dict_exposes_escalation(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", raising=False)
    from core.llm_limits import admin_llm_limits_panel_dict

    d = admin_llm_limits_panel_dict()
    assert "critical_escalation_enabled" in d["limits_saved"]
    assert d["limits_effective"]["critical_escalation_enabled"] is False
    assert d["env_overrides"]["critical_escalation_enabled"] is False


def test_panel_dict_reflects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", "1")
    from core.llm_limits import admin_llm_limits_panel_dict

    d = admin_llm_limits_panel_dict()
    assert d["limits_effective"]["critical_escalation_enabled"] is True
    assert d["env_overrides"]["critical_escalation_enabled"] is True


def test_put_body_accepts_escalation_flag():
    from web.backend.api.admin.dashboard.routes_providers import PutLlmLimitsBody

    body = PutLlmLimitsBody(critical_escalation_enabled=True)
    assert body.critical_escalation_enabled is True
    # Defaults off when omitted.
    assert PutLlmLimitsBody().critical_escalation_enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
