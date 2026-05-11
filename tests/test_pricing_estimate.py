"""LLM log cost estimates (blended $/Mtok)."""

import importlib.util

import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_pe = importlib.util.spec_from_file_location(
    "pricing_estimate_standalone",
    _ROOT / "llm" / "pricing_estimate.py",
)
assert _pe and _pe.loader
_mod = importlib.util.module_from_spec(_pe)
_pe.loader.exec_module(_mod)
estimate_llm_call_cost_usd = _mod.estimate_llm_call_cost_usd
enrich_llm_log_entry = _mod.enrich_llm_log_entry


def test_estimate_deepseek_chat():
    # 1M tokens at 0.27/M blended (no in/out split)
    assert estimate_llm_call_cost_usd("deep-seek", "deepseek-chat", 1_000_000) == 0.27


def test_estimate_deepseek_prompt_completion_split():
    # Builtin in/out: 0.14 in + 0.28 out per MTok
    cost = estimate_llm_call_cost_usd(
        "deep-seek",
        "deepseek-chat",
        0,
        prompt_tokens=500_000,
        completion_tokens=500_000,
    )
    assert cost == round(0.5 * 0.14 + 0.5 * 0.28, 6)


def test_estimate_groq_light_role_fallback():
    assert estimate_llm_call_cost_usd(
        "groq_api",
        "custom-unknown-model",
        1_000_000,
        model_role="light",
    ) == pytest.approx(0.05)


def test_estimate_groq_heavy_role_fallback():
    assert estimate_llm_call_cost_usd(
        "groq_api",
        "custom-unknown-model",
        1_000_000,
        model_role="heavy",
    ) == pytest.approx(0.08)


def test_enrich_backfill():
    e = {"provider": "x", "model": "deepseek-chat", "tokens_used": 1000}
    enrich_llm_log_entry(e)
    assert e.get("estimated_cost_usd") == round(1000 / 1_000_000 * 0.27, 6)


def test_enrich_idempotent():
    e = {"provider": "x", "model": "deepseek-chat", "tokens_used": 100, "estimated_cost_usd": 0.99}
    enrich_llm_log_entry(e)
    assert e["estimated_cost_usd"] == 0.99


def test_write_llm_pricing_yaml_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_LLM_PRICING_YAML", str(tmp_path / "llm_pricing.yaml"))
    import importlib.util

    _pe = importlib.util.spec_from_file_location(
        "pricing_estimate_reload",
        _ROOT / "llm" / "pricing_estimate.py",
    )
    assert _pe and _pe.loader
    pe = importlib.util.module_from_spec(_pe)
    _pe.loader.exec_module(pe)

    assert pe.yaml_override_usd_per_mtok_for_provider("groq_api") is None
    pe.write_llm_pricing_provider_rate("groq_api", 0.11)
    assert pe.yaml_override_usd_per_mtok_for_provider("groq_api") == 0.11
    eff, src = pe.effective_provider_fallback_usd_per_mtok("groq_api")
    assert eff == 0.11 and src == "override"
    pe.write_llm_pricing_provider_rate("groq_api", None)
    assert pe.yaml_override_usd_per_mtok_for_provider("groq_api") is None
