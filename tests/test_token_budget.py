"""Tests for per-model max output token resolution."""

from llm.token_budget import (
    model_output_ceiling,
    resolve_max_output_tokens,
    resolve_max_output_tokens_for_generation,
)


def test_deepseek_chat_ceiling_128k():
    assert model_output_ceiling("deepseek-chat") == 128_000
    assert model_output_ceiling("deepseek-reasoner") == 128_000


def test_resolve_bumps_legacy_32k_cap():
    cfg = {"capabilities": {"max_tokens": 128_000}}
    out = resolve_max_output_tokens_for_generation(
        32_000,
        provider_name="deepseek_api",
        model="deepseek-chat",
        provider_config=cfg,
    )
    assert out == 128_000


def test_resolve_respects_small_explicit_request():
    out = resolve_max_output_tokens(
        1024,
        model="deepseek-chat",
        provider_config={"capabilities": {"max_tokens": 128_000}},
    )
    assert out == 1024


def test_groq_provider_cap():
    out = resolve_max_output_tokens_for_generation(
        128_000,
        model="llama3-70b-8192",
        provider_config={"capabilities": {"max_tokens": 4096}},
    )
    assert out == 4096
