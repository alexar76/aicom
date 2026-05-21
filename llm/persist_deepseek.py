"""
Persist DeepSeek API key and provider defaults so LLM config survives deploys and volume resets.

Called from entrypoint and deploy scripts — keeps model_providers.yaml, secrets file,
and circuit breaker state aligned with DEEPSEEK_API_KEY.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from core.paths import data_root, model_providers_path, secrets_dir
from llm.bootstrap_providers import ensure_model_providers_file
from llm.circuit_breaker import get_circuit_store
from llm.factory_defaults import (
    DEEPSEEK_V4_FLASH_CONTEXT_WINDOW,
    DEEPSEEK_V4_PRO_CONTEXT_WINDOW,
)

logger = logging.getLogger(__name__)

DEEPSEEK_PROVIDER_ID = "deepseek_api"
DEEPSEEK_SECRET_REL = "secrets/llm/deepseek_api_key"
DEFAULT_HEAVY = "deepseek-v4-pro"
DEFAULT_LIGHT = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


def _resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if env:
        return env
    path = data_root() / DEEPSEEK_SECRET_REL
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def _write_secret_file(key: str) -> Path:
    path = data_root() / DEEPSEEK_SECRET_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _merge_deepseek_provider(existing: dict[str, Any] | None, api_key: str) -> dict[str, Any]:
    """Apply DeepSeek defaults but preserve admin-edited models and capabilities."""
    block = _deepseek_provider_block(api_key)
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
        base_caps = block["capabilities"]
        out["capabilities"] = {**base_caps, **ex_caps}
    out["api_key"] = api_key
    out["api_key_env"] = None
    return out


def _deepseek_provider_block(api_key: str) -> dict[str, Any]:
    return {
        "api_key": api_key,
        "api_key_env": None,
        "base_url": DEFAULT_BASE_URL,
        "capabilities": {
            "context_window": DEEPSEEK_V4_PRO_CONTEXT_WINDOW,
            "context_window_light": DEEPSEEK_V4_FLASH_CONTEXT_WINDOW,
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
        "priority": 10,
        "provider_type": "openai_compatible",
    }


def sync_deepseek_provider_config(
    *,
    api_key: str | None = None,
    reset_circuit: bool = True,
    disable_local_fallbacks: bool = True,
) -> dict[str, Any]:
    """
    Merge DeepSeek into model_providers.yaml, persist key, export env, optionally reset circuit.

    Returns a short status dict for logging.
    """
    key = _resolve_api_key(api_key)
    if not key:
        return {"ok": False, "error": "no_deepseek_api_key"}

    secret_path = _write_secret_file(key)
    os.environ["DEEPSEEK_API_KEY"] = key

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

    existing = providers.get(DEEPSEEK_PROVIDER_ID)
    providers[DEEPSEEK_PROVIDER_ID] = _merge_deepseek_provider(
        existing if isinstance(existing, dict) else None,
        key,
    )

    if disable_local_fallbacks:
        for local_name in ("lm_studio", "local_ollama"):
            block = providers.get(local_name)
            if isinstance(block, dict):
                block["enabled"] = False

    raw["providers"] = providers
    raw["default_provider"] = DEEPSEEK_PROVIDER_ID

    rules = raw.get("routing_rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("preferred_provider") == "auto":
                continue
            role = rule.get("model_role")
            if role == "heavy" and rule.get("preferred_provider") not in (None, "auto"):
                rule["preferred_provider"] = DEEPSEEK_PROVIDER_ID

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    circuit_action = None
    if reset_circuit:
        try:
            store = get_circuit_store()
            store.force_closed(DEEPSEEK_PROVIDER_ID, reason="startup_sync")
            circuit_action = "reset_to_closed"
        except Exception as exc:
            logger.warning("Could not reset DeepSeek circuit: %s", exc)
            circuit_action = f"reset_failed:{exc}"

    logger.info(
        "DeepSeek provider synced: models %s / %s, secret=%s, circuit=%s",
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

    parser = argparse.ArgumentParser(description="Sync DeepSeek API key into factory LLM config")
    parser.add_argument("--api-key", default=None, help="DeepSeek API key (else env / secrets file)")
    parser.add_argument("--no-reset-circuit", action="store_true")
    args = parser.parse_args()
    result = sync_deepseek_provider_config(
        api_key=args.api_key,
        reset_circuit=not args.no_reset_circuit,
    )
    if not result.get("ok"):
        print(f"FAILED: {result.get('error')}")
        return 1
    print(yaml.safe_dump(result, default_flow_style=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
