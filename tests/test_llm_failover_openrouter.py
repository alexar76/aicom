"""Tests for Metis prod.yaml patch logic in llm_failover_openrouter."""

from scripts.llm_failover_openrouter import patch_metis_prod_yaml


def test_patch_metis_moves_deepseek_to_openrouter_and_kimi_on_parser_c():
    data = {
        "base_model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "modules": {
            "intent_parser_a": {
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "DEEPSEEK_API_KEY",
                "temperature": 0.5,
            },
            "intent_parser_b": {
                "model": "minimax/minimax-m3",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
            },
            "intent_parser_c": {
                "model": "deepseek-v4-pro",
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "DEEPSEEK_API_KEY",
                "temperature": 0.9,
            },
        },
    }
    out = patch_metis_prod_yaml(data)
    assert out["base_model"] == "minimax/minimax-m3"
    assert out["api_key_env"] == "OPENROUTER_API_KEY"
    assert out["modules"]["intent_parser_a"]["model"] == "minimax/minimax-m3"
    assert out["modules"]["intent_parser_c"]["model"] == "moonshotai/kimi-k3"
    assert out["modules"]["intent_parser_b"]["model"] == "minimax/minimax-m3"
