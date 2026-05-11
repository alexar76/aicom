"""
Persistent outreach configuration and announcements (file-backed, production-safe).

Secrets live only in environment variables; channels.json stores channel ids, types,
enabled flags, and **names of env vars** that hold URLs/tokens — never the secrets themselves.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_ANNOUNCEMENTS = 500


def outreach_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_OUTREACH_DIR", "/app/data/outreach"))


def channels_path() -> Path:
    return outreach_dir() / "channels.json"


def announcements_path() -> Path:
    return outreach_dir() / "announcements.json"


def default_channels_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "channels": [
            {
                "id": "smtp-newsletter",
                "type": "smtp",
                "name": "SMTP newsletter",
                "enabled": False,
                "env_profile": "OUTREACH_SMTP",
                "help": "Set OUTREACH_SMTP_HOST, OUTREACH_SMTP_PORT (587), OUTREACH_SMTP_USER, OUTREACH_SMTP_PASSWORD, OUTREACH_SMTP_FROM, OUTREACH_SMTP_TO (comma recipients or BCC test list).",
            },
            {
                "id": "webhook-automation",
                "type": "webhook",
                "name": "Automation webhook",
                "enabled": False,
                "url_env": "OUTREACH_WEBHOOK_URL",
                "help": "POST JSON: event, announcement_id, title, body_plain, audience, author_role. Use for Slack incoming webhooks, Zapier, Make.",
            },
            {
                "id": "telegram-broadcast",
                "type": "telegram",
                "name": "Telegram",
                "enabled": False,
                "token_env": "OUTREACH_TELEGRAM_BOT_TOKEN",
                "chat_id_env": "OUTREACH_TELEGRAM_CHAT_ID",
                "help": "Bot posts HTML-disabled plain text to the configured chat or channel.",
            },
        ],
    }


def load_channels() -> dict[str, Any]:
    outreach_dir().mkdir(parents=True, exist_ok=True)
    p = channels_path()
    if not p.is_file():
        data = default_channels_payload()
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("outreach channels.json unreadable; using defaults")
        return default_channels_payload()
    if not isinstance(raw, dict) or "channels" not in raw:
        return default_channels_payload()
    return raw


def save_channels(data: dict[str, Any]) -> None:
    outreach_dir().mkdir(parents=True, exist_ok=True)
    channels_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_announcements() -> list[dict[str, Any]]:
    outreach_dir().mkdir(parents=True, exist_ok=True)
    p = announcements_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return raw


def save_announcements(items: list[dict[str, Any]]) -> None:
    outreach_dir().mkdir(parents=True, exist_ok=True)
    trimmed = items[-MAX_ANNOUNCEMENTS:]
    announcements_path().write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")


def get_announcement(aid: str) -> Optional[dict[str, Any]]:
    for a in load_announcements():
        if a.get("id") == aid:
            return a
    return None


def upsert_announcement(row: dict[str, Any]) -> None:
    items = load_announcements()
    found = False
    out: list[dict[str, Any]] = []
    for a in items:
        if a.get("id") == row.get("id"):
            out.append(row)
            found = True
        else:
            out.append(a)
    if not found:
        out.append(row)
    save_announcements(out)


def new_announcement_id() -> str:
    return f"ann-{uuid.uuid4().hex[:12]}"
