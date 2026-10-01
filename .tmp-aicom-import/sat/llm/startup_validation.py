"""Production LLM provider key validation (AIFACTORY_PROD=1)."""

from __future__ import annotations

import re
from typing import Any

import yaml

from core.paths import model_providers_path

_PLACEHOLDER = re.compile(
    r"^(?:changeme|replace[_-]?me|your[_-]?key|sk-xxx|null|none|test|demo)$",
    re.IGNORECASE,
)


def _key_resolved(provider: dict[str, Any]) -> bool:
    inline = provider.get("api_key")
    if isinstance(inline, str) and inline.strip() and not _PLACEHOLDER.match(inline.strip()):
        return True

    env_name = provider.get("api_key_env")
    if isinstance(env_name, str) and env_name.strip():
        from security.secret_resolver import get_secret

        val = get_secret(env_name.strip(), env_names=[env_name.strip()])
        if val and not _PLACEHOLDER.match(val):
            return True
    return False


def production_llm_key_issues() -> list[str]:
    """
    Return blocking issues when production mode is on but no enabled LLM provider
    has a resolvable API key (env, secret file, or inline api_key in YAML).
    """
    cfg_path = model_providers_path()
    if not cfg_path.is_file():
        return [
            f"model_providers.yaml missing at {cfg_path} — pipeline cannot call LLM APIs. "
            "Bootstrap via Admin → LLM Providers or copy model_providers.example.yaml."
        ]

    try:
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"Cannot read {cfg_path}: {exc}"]

    providers = config.get("providers")
    if not isinstance(providers, dict):
        return [f"{cfg_path}: 'providers' section missing or invalid."]

    enabled = [
        (name, p)
        for name, p in providers.items()
        if isinstance(p, dict) and p.get("enabled", True) is not False
    ]
    if not enabled:
        return ["No enabled LLM providers in model_providers.yaml."]

    missing = [name for name, p in enabled if not _key_resolved(p)]
    if len(missing) == len(enabled):
        return [
            "No API keys configured for any enabled LLM provider "
            f"({', '.join(missing)}). Set keys via Admin → LLM Providers, "
            "data/secrets/llm/*_api_key, or provider api_key_env in .env."
        ]

    default = config.get("default_provider")
    if isinstance(default, str):
        dp = providers.get(default)
        if isinstance(dp, dict) and dp.get("enabled", True) is not False and not _key_resolved(dp):
            return [
                f"default_provider {default!r} is enabled but has no resolvable API key. "
                "Set DEEPSEEK_API_KEY (or the provider's api_key_env) before AIFACTORY_PROD=1."
            ]

    return []
