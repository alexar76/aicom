"""
Canonical LLM provider ids and legacy aliases (e.g. deep-seek → deepseek_api).
"""

from __future__ import annotations

# Canonical id used in model_providers.yaml, fragments, and admin UI.
CANONICAL_DEEPSEEK_API = "deepseek_api"

# Legacy provider keys seen in old configs and llm_calls.jsonl.
LEGACY_PROVIDER_ALIASES: dict[str, str] = {
    "deep-seek": CANONICAL_DEEPSEEK_API,
    "dee-seek": CANONICAL_DEEPSEEK_API,
    "deepseek": CANONICAL_DEEPSEEK_API,
}


def normalize_llm_provider_id(provider: str | None) -> str:
    """Map legacy provider id to canonical; unknown ids returned trimmed unchanged."""
    if provider is None:
        return ""
    raw = str(provider).strip()
    if not raw:
        return ""
    return LEGACY_PROVIDER_ALIASES.get(raw.lower(), raw)


def is_legacy_provider_id(provider: str | None) -> bool:
    if not provider:
        return False
    return str(provider).strip().lower() in LEGACY_PROVIDER_ALIASES
