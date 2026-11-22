"""Which provider a task starts on, and where it goes after a failure.

The admin routing editor sets a provider per task type. It must take effect even when a default
provider is configured, "auto" must mean the default, and the rule's fallback provider must only be
used after a failure.
"""

from __future__ import annotations

import pytest

from llm.provider import GenerationConfig, ProviderStatus
from llm.router import LLMRouter


class _Health:
    def __init__(self, status=ProviderStatus.ONLINE, latency_ms=1.0):
        self.status = status
        self.latency_ms = latency_ms


class _Provider:
    def __init__(self, status=ProviderStatus.ONLINE, latency_ms=1.0):
        self.health = _Health(status, latency_ms)


@pytest.fixture
def router(monkeypatch):
    monkeypatch.delenv("AIFACTORY_LLM_CRITICAL_ESCALATION_ENABLED", raising=False)
    r = LLMRouter()
    r.default_provider = "openrouter_api"
    r.providers = {"openrouter_api": _Provider(), "deepseek_api": _Provider(), "groq_api": _Provider(latency_ms=0.5)}
    r._provider_configs = {
        "openrouter_api": {"models": {"heavy": "or-heavy", "light": "or-light"}},
        "deepseek_api": {"models": {"heavy": "ds-pro", "light": "ds-flash"}},
        "groq_api": {"models": {"heavy": "groq-70b", "light": "groq-8b"}},
    }
    r.routing_rules = [
        {"task_type": "architecture_design", "preferred_provider": "deepseek_api", "model_role": "heavy"},
        {"task_type": "qa_testing", "preferred_provider": "auto", "model_role": "light",
         "fallback_provider": "groq_api"},
        {"task_type": "code_generation", "preferred_provider": "local_ollama", "model_role": "heavy",
         "fallback_provider": "deepseek_api"},
    ]
    return r


def test_rule_provider_wins_over_default(router):
    assert router._select_provider("architecture_design") == "deepseek_api"
    assert router._get_model_for_role("deepseek_api", "heavy") == "ds-pro"


def test_auto_and_no_rule_use_default(router):
    assert router._select_provider("qa_testing") == "openrouter_api"
    assert router._select_provider("marketing_copy") == "openrouter_api"


def test_fallback_is_not_a_first_choice(router):
    # qa_testing names groq_api only as fallback: it starts on the default, not on groq_api
    assert router._select_provider("qa_testing") == "openrouter_api"
    router.default_provider = None
    # without a default the fastest provider is used; the fallback is still not picked for being one
    router.providers["groq_api"].health.latency_ms = 50.0
    assert router._select_provider("qa_testing") != "groq_api"


def test_unloaded_or_down_preferred_falls_back_to_default(router):
    # local_ollama is not loaded (disabled), as on the live factory
    assert router._select_provider("code_generation") == "openrouter_api"
    router.providers["deepseek_api"].health.status = ProviderStatus.UNAVAILABLE
    assert router._select_provider("architecture_design") == "openrouter_api"


def test_failover_from_preferred_goes_to_rule_fallback_then_default(router):
    router.routing_rules[0]["fallback_provider"] = "groq_api"
    assert router._next_failover("architecture_design", "deepseek_api", {"deepseek_api"}) == "groq_api"
    tried = {"deepseek_api", "groq_api"}
    assert router._next_failover("architecture_design", "groq_api", tried) == "openrouter_api"
    assert router._next_failover("architecture_design", "openrouter_api", tried | {"openrouter_api"}) is None


def test_failover_from_default_without_fallback_ends(router):
    assert router._next_failover("marketing_copy", "openrouter_api", {"openrouter_api"}) is None


def test_failover_rebinds_the_model_to_the_new_provider(router):
    cfg = GenerationConfig(model_role="heavy", task_type="architecture_design")
    router._rebind_model_for_provider("openrouter_api", cfg, "architecture_design", caller_override=None)
    assert cfg.model_override == "or-heavy"
