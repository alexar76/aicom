"""
Persist OpenRouter API key and provider defaults for emergency DeepSeek failover.

Called from scripts/llm_failover_openrouter.py and factory entrypoint hooks — keeps
model_providers.yaml, secrets file, and circuit breaker aligned with OPENROUTER_API_KEY.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING, Any

import yaml

from core.paths import data_root, model_providers_path
from llm.bootstrap_providers import ensure_model_providers_file
from llm.circuit_breaker import get_circuit_store

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

OPENROUTER_PROVIDER_ID = "openrouter_api"
OPENROUTER_SECRET_REL = "secrets/llm/openrouter_api_key"
PROFILE_MARKER_REL = "config/llm_active_profile"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_HEAVY = "minimax/minimax-m3"
DEFAULT_LIGHT = "minimax/minimax-m3"
DEFAULT_CONTEXT_WINDOW = 200_000


def _resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if env:
        return env
    path = data_root() / OPENROUTER_SECRET_REL
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def _write_secret_file(key: str) -> Path:
    path = data_root() / OPENROUTER_SECRET_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip() + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return path


def _openrouter_provider_block(api_key: str) -> dict[str, Any]:
    return {
        "api_key": api_key,
        "api_key_env": None,
        "base_url": OPENROUTER_BASE_URL,
        "capabilities": {
            "context_window": DEFAULT_CONTEXT_WINDOW,
            "context_window_light": DEFAULT_CONTEXT_WINDOW,
            "max_tokens": 64_000,
            "supports_streaming": True,
            "supports_vision": False,
        },
        "enabled": True,
        "health_check_endpoint": "/v1/models",
        "models": {
            "heavy": DEFAULT_HEAVY,
            "light": DEFAULT_LIGHT,
        },
        "priority": 12,
        "provider_type": "openai_compatible",
        "extra_headers": {
            "HTTP-Referer": "https://magic-ai-factory.com",
            "X-Title": "AI-Factory",
        },
    }


def _merge_openrouter_provider(existing: dict[str, Any] | None, api_key: str) -> dict[str, Any]:
    block = _openrouter_provider_block(api_key)
    if not isinstance(existing, dict):
        return block
    out = dict(block)
    for key in ("models", "priority", "health_check_endpoint", "enabled", "provider_type", "base_url"):
        if key in existing and existing[key] is not None:
            if key == "models" and isinstance(existing["models"], dict):
                out["models"] = {**block["models"], **existing["models"]}
            else:
                out[key] = existing[key]
    ex_caps = existing.get("capabilities")
    if isinstance(ex_caps, dict) and ex_caps:
        out["capabilities"] = {**block["capabilities"], **ex_caps}
    out["api_key"] = api_key
    out["api_key_env"] = None
    return out


def _write_active_profile(name: str) -> Path:
    path = data_root() / PROFILE_MARKER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name.strip() + "\n", encoding="utf-8")
    return path


def sync_openrouter_provider_config(
    *,
    api_key: str | None = None,
    reset_circuit: bool = True,
    set_default: bool = True,
    rewrite_routing: bool = True,
) -> dict[str, Any]:
    """Merge OpenRouter into model_providers.yaml, persist key, export env."""
    key = _resolve_api_key(api_key)
    if not key:
        return {"ok": False, "error": "no_openrouter_api_key"}

    secret_path = _write_secret_file(key)
    os.environ["OPENROUTER_API_KEY"] = key

    cfg_path = model_providers_path()
    ensure_model_providers_file(cfg_path)
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except OSError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    providers = raw.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    existing = providers.get(OPENROUTER_PROVIDER_ID)
    providers[OPENROUTER_PROVIDER_ID] = _merge_openrouter_provider(
        existing if isinstance(existing, dict) else None,
        key,
    )
    ds = providers.get("deepseek_api")
    if isinstance(ds, dict):
        ds["enabled"] = False
    raw["providers"] = providers
    if set_default:
        raw["default_provider"] = OPENROUTER_PROVIDER_ID
    _write_active_profile("openrouter-all")

    if rewrite_routing:
        rules = raw.get("routing_rules")
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                pref = rule.get("preferred_provider")
                if pref in (None, "auto"):
                    continue
                rule["preferred_provider"] = OPENROUTER_PROVIDER_ID
                fb = rule.get("fallback_provider")
                if fb and fb not in ("auto", OPENROUTER_PROVIDER_ID):
                    rule["fallback_provider"] = OPENROUTER_PROVIDER_ID

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    circuit_action = None
    if reset_circuit:
        try:
            store = get_circuit_store()
            store.force_closed(OPENROUTER_PROVIDER_ID, reason="openrouter_failover_sync")
            circuit_action = "reset_to_closed"
        except Exception as exc:
            logger.warning("Could not reset OpenRouter circuit: %s", exc)
            circuit_action = f"reset_failed:{exc}"

    logger.info(
        "OpenRouter provider synced: models %s / %s, secret=%s, circuit=%s",
        DEFAULT_HEAVY,
        DEFAULT_LIGHT,
        secret_path,
        circuit_action,
    )
    return {
        "ok": True,
        "secret_path": str(secret_path),
        "config_path": str(cfg_path),
        "heavy": DEFAULT_HEAVY,
        "light": DEFAULT_LIGHT,
        "circuit": circuit_action,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sync OpenRouter API key into factory LLM config")
    parser.add_argument("--api-key", default=None, help="OpenRouter API key (else env / secrets file)")
    parser.add_argument("--no-reset-circuit", action="store_true")
    parser.add_argument("--no-set-default", action="store_true")
    args = parser.parse_args()
    result = sync_openrouter_provider_config(
        api_key=args.api_key,
        reset_circuit=not args.no_reset_circuit,
        set_default=not args.no_set_default,
    )
    if not result.get("ok"):
        logger.error("FAILED: %s", result.get("error"))
        return 1
    logger.info(yaml.safe_dump(result, default_flow_style=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
