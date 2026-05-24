"""Unified secret resolution: env → Fernet vault → HashiCorp Vault KV v2."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib import error, request

logger = logging.getLogger(__name__)

# Standard LLM env var → relative secret file under data/secrets/llm/
LLM_SECRET_FILES: dict[str, str] = {
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "GROQ_API_KEY": "groq_api_key",
    "TOGETHER_API_KEY": "together_api_key",
}


def _backend() -> str:
    """auto | env | fernet | hashicorp"""
    return (os.environ.get("AIFACTORY_SECRETS_BACKEND") or "auto").strip().lower()


def _hashicorp_configured() -> bool:
    addr = (os.environ.get("AIFACTORY_HASHICORP_VAULT_ADDR") or os.environ.get("VAULT_ADDR") or "").strip()
    token = (os.environ.get("AIFACTORY_HASHICORP_VAULT_TOKEN") or os.environ.get("VAULT_TOKEN") or "").strip()
    return bool(addr and token)


def _fernet_manager():
    from security.secrets_manager import SecretsManager

    return SecretsManager()


def _read_hashicorp(path: str) -> dict[str, Any] | None:
    addr = (os.environ.get("AIFACTORY_HASHICORP_VAULT_ADDR") or os.environ.get("VAULT_ADDR") or "").rstrip("/")
    token = (os.environ.get("AIFACTORY_HASHICORP_VAULT_TOKEN") or os.environ.get("VAULT_TOKEN") or "").strip()
    mount = (os.environ.get("AIFACTORY_HASHICORP_VAULT_MOUNT") or "secret").strip().strip("/")
    if not addr or not token:
        return None
    if addr.startswith("http://") and not _vault_http_allowed(addr):
        logger.error(
            "Refusing HashiCorp Vault over plain HTTP (%s) — set https:// or "
            "AIFACTORY_HASHICORP_VAULT_ALLOW_HTTP=1 for loopback-only dev",
            addr,
        )
        return None
    if addr.startswith("http://"):
        logger.warning("HashiCorp Vault token sent over plain HTTP to %s", addr)
    url = f"{addr}/v1/{mount}/data/{path.lstrip('/')}"
    req = request.Request(url, headers={"X-Vault-Token": token})
    try:
        with request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
        logger.debug("HashiCorp Vault read failed for %s: %s", path, exc)
        return None
    data = payload.get("data", {}).get("data")
    return data if isinstance(data, dict) else None


def _vault_http_allowed(addr: str) -> bool:
    if os.environ.get("AIFACTORY_HASHICORP_VAULT_ALLOW_HTTP", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    from urllib.parse import urlparse

    host = (urlparse(addr).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _resolve_backend() -> str:
    mode = _backend()
    if mode == "auto":
        if _hashicorp_configured():
            return "hashicorp"
        from core.paths import encrypted_vault_path

        if encrypted_vault_path().exists():
            return "fernet"
        return "env"
    return mode


def get_secret(
    key: str,
    *,
    env_names: list[str] | None = None,
    default: str | None = None,
) -> str | None:
    """
    Resolve a secret by logical key (e.g. ``deepseek-api-key``) or env name.

    Lookup order (``AIFACTORY_SECRETS_BACKEND=auto``):
      1. HashiCorp Vault KV v2 (when ``VAULT_ADDR`` + token set)
      2. Local Fernet vault (``encrypted_vault.json``)
      3. Process environment
      4. ``data/secrets/llm/*`` flat files
    """
    names = env_names or [key.upper().replace("-", "_")]
    backend = _resolve_backend()

    if backend == "hashicorp":
        base = (os.environ.get("AIFACTORY_HASHICORP_VAULT_PATH") or "aicom").strip().strip("/")
        for name in names:
            vault_key = name.lower().replace("_", "-")
            blob = _read_hashicorp(f"{base}/{vault_key}")
            if blob and blob.get("value"):
                return str(blob["value"]).strip()
            blob = _read_hashicorp(f"{base}/llm/{vault_key}")
            if blob and blob.get("value"):
                return str(blob["value"]).strip()

    if backend in ("fernet", "auto", "hashicorp"):
        try:
            mgr = _fernet_manager()
            for name in names:
                val = mgr.get_secret(name.lower().replace("_", "-"))
                if val:
                    return str(val).strip()
                val = mgr.get_secret(name)
                if val:
                    return str(val).strip()
        except Exception as exc:
            logger.debug("Fernet vault read skipped: %s", exc)

    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val

    from core.paths import data_root

    for name in names:
        rel = LLM_SECRET_FILES.get(name)
        if not rel:
            continue
        fpath = data_root() / "secrets" / "llm" / rel
        if fpath.is_file():
            val = fpath.read_text(encoding="utf-8").strip()
            if val:
                return val

    return default


def export_llm_keys_to_env() -> int:
    """Populate unset LLM env vars from vault / files. Returns count exported."""
    count = 0
    for env_name in LLM_SECRET_FILES:
        if (os.environ.get(env_name) or "").strip():
            continue
        val = get_secret(env_name, env_names=[env_name])
        if val:
            os.environ[env_name] = val
            count += 1
    return count


@lru_cache(maxsize=1)
def sync_file_secrets_into_fernet_vault() -> int:
    """
    Import ``data/secrets/llm/*`` into the local Fernet vault when
    ``AIFACTORY_SECRETS_SYNC_FROM_FILES=1`` (default on first boot).
    """
    if os.environ.get("AIFACTORY_SECRETS_SYNC_FROM_FILES", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return 0
    from core.paths import data_root

    llm_dir = data_root() / "secrets" / "llm"
    if not llm_dir.is_dir():
        return 0
    mgr = _fernet_manager()
    imported = 0
    for env_name, filename in LLM_SECRET_FILES.items():
        fpath = llm_dir / filename
        if not fpath.is_file():
            continue
        val = fpath.read_text(encoding="utf-8").strip()
        if not val:
            continue
        key = env_name.lower().replace("_", "-")
        if not mgr.has_secret(key):
            mgr.set_secret(key, val)
            imported += 1
    if imported:
        logger.info("Synced %d LLM secret(s) from files into Fernet vault", imported)
    return imported
