"""
Telegram bot token and chat id — do not commit real values in repository ``config.yaml``.

Each credential is resolved independently (first non-empty):
1. Environment: ``TELEGRAM_BOT_TOKEN``, ``TELEGRAM_CHAT_ID``
2. ``<data_root>/secrets/telegram.yaml`` (under gitignored ``data/secrets/``)
3. Legacy ``general.*`` in main ``config.yaml`` (deprecated; stripped on save)

Admin UI saves into ``secrets/telegram.yaml`` via :func:`write_telegram_credentials`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from core.paths import data_root

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))


def _secrets_file() -> Path:
    p = data_root() / "secrets" / "telegram.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_general_config() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.is_file():
            return {}
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("telegram: could not read config: %s", e)
        return {}


def _read_secrets_file() -> dict[str, str]:
    path = _secrets_file()
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {
            "telegram_bot_token": str(raw.get("telegram_bot_token") or "").strip(),
            "telegram_chat_id": str(raw.get("telegram_chat_id") or "").strip(),
        }
    except Exception as e:
        logger.warning("telegram: could not read %s: %s", path, e)
        return {}


def resolve_telegram_token_chat_id() -> tuple[str, str]:
    """Return (token, chat_id) for outbound Telegram API calls."""
    env_tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    env_chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    sec = _read_secrets_file()
    leg = _read_general_config()
    tok = env_tok or sec.get("telegram_bot_token") or str(leg.get("telegram_bot_token") or "").strip()
    chat = env_chat or sec.get("telegram_chat_id") or str(leg.get("telegram_chat_id") or "").strip()
    return tok, chat


def telegram_token_configured() -> bool:
    tok, _ = resolve_telegram_token_chat_id()
    return bool(tok)


def write_telegram_credentials(token: str, chat_id: str) -> None:
    """Persist token and chat id to data/secrets/telegram.yaml (creates/overwrites)."""
    path = _secrets_file()
    data: dict[str, str] = {}
    if token.strip():
        data["telegram_bot_token"] = token.strip()
    if chat_id.strip():
        data["telegram_chat_id"] = chat_id.strip()
    if data:
        path.write_text(yaml.safe_dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    elif path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    _strip_legacy_telegram_keys_in_config_yaml()


def revoke_telegram_credentials() -> None:
    """Remove stored Telegram secrets file and legacy keys from config.yaml."""
    path = _secrets_file()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    _strip_legacy_telegram_keys_in_config_yaml()


def _strip_legacy_telegram_keys_in_config_yaml() -> None:
    if not CONFIG_PATH.is_file():
        return
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        gen = raw.get("general")
        if not isinstance(gen, dict):
            return
        changed = False
        for k in ("telegram_bot_token", "telegram_chat_id"):
            if k in gen:
                del gen[k]
                changed = True
        if changed:
            CONFIG_PATH.write_text(yaml.safe_dump(raw, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    except Exception as e:
        logger.debug("telegram: could not strip legacy keys: %s", e)
