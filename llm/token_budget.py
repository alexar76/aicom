"""
Resolve effective ``max_tokens`` per provider + model.

Agents request FACTORY_MAX_OUTPUT_TOKENS_*; the router clamps to the highest
output budget the active model supports (never the legacy 32k factory cap alone).
"""

from __future__ import annotations

import contextlib

from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_MAX_OUTPUT_TOKENS_LIGHT

# Substring match on active model id (lowercase). Values are API output ceilings.
_MODEL_OUTPUT_CEILINGS: dict[str, int] = {
    "deepseek-v4-pro": 384_000,
    "deepseek-v4-flash": 384_000,
    "deepseek-reasoner": 128_000,
    "deepseek-chat": 128_000,
    "deepseek-coder": 128_000,
    "claude": 8192,
    "gpt-4": 128_000,
    "gpt-5": 128_000,
    "llama": 8192,
    "mixtral": 4096,
    "qwen": 32_000,
}

_DEFAULT_CEILING = FACTORY_MAX_OUTPUT_TOKENS_HEAVY


def model_output_ceiling(model: str | None) -> int:
    """Best-known max *output* tokens for ``model`` (defaults to factory heavy budget)."""
    if not model or not str(model).strip():
        return _DEFAULT_CEILING
    m = str(model).strip().lower()
    best = 0
    for needle, limit in _MODEL_OUTPUT_CEILINGS.items():
        if needle in m:
            best = max(best, int(limit))
    return best if best > 0 else _DEFAULT_CEILING


def resolve_max_output_tokens(
    requested: int | None,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    provider_config: dict | None = None,
    default_heavy: bool = True,
) -> int:
    """
  Return ``min(requested, yaml_cap, model_ceiling)`` with sensible defaults.

  When ``requested`` is missing or zero, use the model/provider ceiling (up to 128k for DeepSeek).
  """
    req = int(requested or 0)
    if req <= 0:
        req = _DEFAULT_CEILING if default_heavy else FACTORY_MAX_OUTPUT_TOKENS_LIGHT

    ceilings: list[int] = [model_output_ceiling(model)]
    if provider_config:
        cap = (provider_config.get("capabilities") or {}).get("max_tokens")
        if cap is not None:
            with contextlib.suppress(TypeError, ValueError):
                ceilings.append(int(cap))

    ceiling = min(ceilings) if ceilings else _DEFAULT_CEILING
    # Never below 1; never above model ceiling (use max of req and ... no user wants max not min)

    # Use the largest generation the stack allows: min(requested, ceiling) only caps downward.
    effective = min(max(req, 1), max(ceiling, 1))
    return effective


def resolve_max_output_tokens_for_generation(
    requested: int | None,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    provider_config: dict | None = None,
) -> int:
    """
    Prefer the model/provider maximum when the caller asked for the legacy factory cap.

    If ``requested`` is at or below the old 32_000 heavy default, bump to ``ceiling``.
    """
    ceiling = resolve_max_output_tokens(
        None,
        provider_name=provider_name,
        model=model,
        provider_config=provider_config,
    )
    req = int(requested or 0)
    if req <= 0:
        return ceiling
    legacy_caps = {32_000, 16_000}
    if req in legacy_caps and ceiling > req:
        return ceiling
    return min(req, ceiling)
