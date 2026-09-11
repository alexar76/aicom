"""A spend figure must be a price or an admission, never a guess wearing four decimals.

Not one of the models this ecosystem actually runs was in the price table, so every real call
was charged at a generic $0.50/Mtok fallback and every recorded figure looked exact. Measured
on one day of remediation traffic: recorded $0.3862, honest range $0.028 to $1.42, depending
on which of three disagreeing tables you believed.

A number nobody can bill against is worse than no number, because it stops people asking.
"""

from __future__ import annotations

import pytest

from llm.pricing_estimate import (
    estimate_llm_call_cost_usd,
    reset_unpriced_models,
    unpriced_models,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_unpriced_models()
    yield
    reset_unpriced_models()


#: Every model this ecosystem is configured to run, with the rate read from the provider's
#: live price list on 2026-08-30. If one of these ever falls out of the table, the loop goes
#: back to guessing and nothing else would say so.
IN_USE = [
    ("minimax/minimax-m3", 0.30, 1.20),
    ("moonshotai/kimi-k3", 3.00, 15.00),
    ("deepseek/deepseek-v4-pro", 0.4578, 0.9156),
    ("deepseek/deepseek-v4-flash", 0.0806, 0.1613),
    ("qwen/qwen3-coder", 0.30, 1.00),
    ("qwen/qwen3.6-35b-a3b", 0.10, 0.90),
]


@pytest.mark.parametrize("model,inp,out", IN_USE)
def test_a_model_we_actually_run_is_priced_not_guessed(model, inp, out):
    cost = estimate_llm_call_cost_usd(
        "openai_compatible", model, prompt_tokens=1_000_000, completion_tokens=0)
    assert cost == pytest.approx(inp, rel=1e-3)
    assert unpriced_models() == {}, f"{model} fell through to the fallback"


@pytest.mark.parametrize("model,inp,out", IN_USE)
def test_output_is_priced_separately_from_input(model, inp, out):
    # Remediation is output-heavy — the model returns whole files — so a blended rate
    # understates it by roughly the ratio between these two numbers.
    cost = estimate_llm_call_cost_usd(
        "openai_compatible", model, prompt_tokens=0, completion_tokens=1_000_000)
    assert cost == pytest.approx(out, rel=1e-3)


def test_the_measured_council_run_now_prices_correctly():
    # The real numbers from one METIS council deliberation, read from its usage log.
    cost = estimate_llm_call_cost_usd(
        "openai_compatible", "minimax/minimax-m3",
        prompt_tokens=96_222, completion_tokens=109_448)
    assert cost == pytest.approx(0.0289 + 0.1313, abs=0.002)
    assert unpriced_models() == {}


def test_kimi_is_twelve_times_minimax_on_the_same_traffic():
    # The reason the council runs on minimax. Worth pinning: a silent switch to kimi would
    # multiply the loop's model spend by an order of magnitude.
    args = dict(prompt_tokens=96_222, completion_tokens=109_448)
    mini = estimate_llm_call_cost_usd("openai_compatible", "minimax/minimax-m3", **args)
    kimi = estimate_llm_call_cost_usd("openai_compatible", "moonshotai/kimi-k3", **args)
    assert kimi / mini > 10


# ── what we cannot price must be named ────────────────────────────────────────────

def test_an_unknown_model_is_recorded_rather_than_silently_averaged():
    cost = estimate_llm_call_cost_usd(
        "openai_compatible", "someone/brand-new-model",
        prompt_tokens=1000, completion_tokens=1000)

    assert cost is not None, "refusing to estimate would break every caller"
    assert unpriced_models() == {"openai_compatible:someone/brand-new-model": 1}


def test_repeated_calls_are_counted_not_re_warned():
    for _ in range(5):
        estimate_llm_call_cost_usd("openai_compatible", "someone/unknown",
                                   prompt_tokens=10, completion_tokens=10)
    assert unpriced_models()["openai_compatible:someone/unknown"] == 5


def test_the_warning_names_the_model_once(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            estimate_llm_call_cost_usd("openai_compatible", "someone/unknown",
                                       prompt_tokens=10, completion_tokens=10)

    assert caplog.text.count("no price for") == 1, "once per model, not once per call"
    assert "someone/unknown" in caplog.text


def test_a_totals_only_call_is_recorded_too():
    estimate_llm_call_cost_usd("openai_compatible", "someone/unknown", tokens_used=5000)
    assert "openai_compatible:someone/unknown" in unpriced_models()


def test_two_unknown_models_are_tracked_apart():
    estimate_llm_call_cost_usd("openai_compatible", "a/one", prompt_tokens=1, completion_tokens=1)
    estimate_llm_call_cost_usd("openai_compatible", "b/two", prompt_tokens=1, completion_tokens=1)
    assert len(unpriced_models()) == 2


def test_a_priced_model_never_appears_in_the_unpriced_list():
    estimate_llm_call_cost_usd("openai_compatible", "minimax/minimax-m3",
                               prompt_tokens=100, completion_tokens=100)
    estimate_llm_call_cost_usd("openai_compatible", "unknown/x",
                               prompt_tokens=100, completion_tokens=100)
    assert list(unpriced_models()) == ["openai_compatible:unknown/x"]
