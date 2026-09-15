"""Tests for fleet LLM routing profiles (Metis YAML patches)."""

from scripts.llm_routing import (
    patch_metis_deepseek_all,
    patch_metis_hybrid,
    patch_metis_openrouter_all,
)


def test_hybrid_metis_minimax_on_skeptic_seats_only():
    data = {
        "base_model": "minimax/minimax-m3",
        "modules": {
            "intent_parser_a": {"model": "x", "api_key_env": "DEEPSEEK_API_KEY"},
            "intent_parser_b": {"model": "x", "api_key_env": "DEEPSEEK_API_KEY", "temperature": 0.7},
            "intent_parser_c": {"model": "x", "api_key_env": "DEEPSEEK_API_KEY"},
            "moa_proposer_skeptic": {"model": "x", "api_key_env": "OPENROUTER_API_KEY"},
        },
    }
    out = patch_metis_hybrid(data)
    assert out["base_model"] == "deepseek-v4-pro"
    assert out["api_key_env"] == "DEEPSEEK_API_KEY"
    assert out["modules"]["intent_parser_a"]["model"] == "deepseek-v4-flash"
    assert out["modules"]["intent_parser_b"]["model"] == "minimax/minimax-m3"
    assert out["modules"]["intent_parser_b"]["api_key_env"] == "OPENROUTER_API_KEY"
    assert out["modules"]["intent_parser_c"]["model"] == "deepseek-v4-pro"
    assert out["modules"]["moa_proposer_skeptic"]["api_key_env"] == "OPENROUTER_API_KEY"


def test_deepseek_all_no_openrouter_seats():
    data = {
        "modules": {
            "intent_parser_b": {"model": "minimax/minimax-m3", "api_key_env": "OPENROUTER_API_KEY"},
            "moa_proposer_skeptic": {"model": "minimax/minimax-m3", "api_key_env": "OPENROUTER_API_KEY"},
        },
    }
    out = patch_metis_deepseek_all(data)
    assert out["base_model"] == "deepseek-v4-pro"
    assert out["modules"]["intent_parser_b"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert out["modules"]["moa_proposer_skeptic"]["api_key_env"] == "DEEPSEEK_API_KEY"


def test_openrouter_all_kimi_on_parser_c():
    data = {
        "modules": {
            "intent_parser_c": {"model": "deepseek-v4-pro", "api_key_env": "DEEPSEEK_API_KEY"},
            "intent_parser_b": {"model": "minimax/minimax-m3", "api_key_env": "OPENROUTER_API_KEY"},
        },
    }
    out = patch_metis_openrouter_all(data)
    assert out["base_model"] == "minimax/minimax-m3"
    assert out["modules"]["intent_parser_c"]["model"] == "moonshotai/kimi-k3"
    assert out["modules"]["intent_parser_b"]["model"] == "minimax/minimax-m3"
