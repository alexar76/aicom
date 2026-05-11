"""
Optional Telegram alerts for pipeline progress and new products.

Credentials: :mod:`web.backend.services.telegram_credentials` (env, ``data/secrets/telegram.yaml``,
legacy keys in config). Notify toggles still live under ``general.*`` in ``config.yaml``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))

AGENT_LABELS: dict[str, str] = {
    "pm": "PM",
    "architect": "Architect",
    "developer": "Developer",
    "dev": "Developer",
    "qa": "QA",
    "security": "Security",
    "devops": "DevOps",
    "marketing": "Marketing",
    "sales": "Sales",
    "analyst": "Analyst",
    "evolution_analyst": "Evolution",
    "design_critic": "Design critic",
    "hardening": "Hardening",
    "methodologist": "Methodologist",
}


def _read_general() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.is_file():
            return {}
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("telegram notify: could not read config: %s", e)
        return {}


def telegram_pipeline_config() -> dict[str, Any]:
    """Flattened settings for notification helpers."""
    from web.backend.services.telegram_credentials import resolve_telegram_token_chat_id

    g = _read_general()
    token, chat_id = resolve_telegram_token_chat_id()
    return {
        "enabled": bool(g.get("telegram_notify_enabled")),
        "notify_pipeline": bool(g.get("telegram_notify_pipeline_stages", True)),
        "notify_new_product": bool(g.get("telegram_notify_new_products", True)),
        "token": token,
        "chat_id": chat_id,
    }


def send_telegram_message_sync(text: str) -> tuple[bool, str]:
    """
    Send plain text using configured bot token and chat id.
    Returns (ok, detail).
    """
    cfg = telegram_pipeline_config()
    token = cfg["token"]
    chat_id = cfg["chat_id"]
    if not token or not chat_id:
        return False, "telegram_bot_token or telegram_chat_id missing in Settings"
    body = text.strip()
    if not body:
        return False, "empty message"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": body[:4000], "disable_web_page_preview": True}
    try:
        import httpx

        with httpx.Client(timeout=25.0) as client:
            r = client.post(url, json=payload)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if not data.get("ok"):
                return False, str(data.get("description") or r.text)[:500]
            return True, "ok"
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False, str(e)[:500]


def notify_telegram_pipeline_stage(
    *,
    agent_type: str,
    product_id: str,
    target_state: str,
    idea_snippet: str = "",
) -> None:
    cfg = telegram_pipeline_config()
    if not cfg["enabled"] or not cfg["notify_pipeline"]:
        return
    if not cfg["token"] or not cfg["chat_id"]:
        return

    at = (agent_type or "").lower()
    label = AGENT_LABELS.get(at, (agent_type or "Agent").title() or "Agent")
    short_id = f"{product_id[:12]}…" if len(product_id) > 12 else product_id
    lines = [
        f"AI-Factory · Pipeline stage",
        f"{label} finished → state `{target_state}`",
        f"Product `{short_id}`",
    ]
    if idea_snippet.strip():
        clip = idea_snippet.strip()[:280]
        if len(idea_snippet.strip()) > 280:
            clip += "…"
        lines.append(f"Idea: {clip}")

    ok, detail = send_telegram_message_sync("\n".join(lines))
    if not ok:
        logger.debug("telegram pipeline notify skipped: %s", detail)


def notify_telegram_new_product(
    *,
    product_id: str,
    idea_snippet: str = "",
    source: str = "pipeline",
) -> None:
    cfg = telegram_pipeline_config()
    if not cfg["enabled"] or not cfg["notify_new_product"]:
        return
    if not cfg["token"] or not cfg["chat_id"]:
        return

    short_id = f"{product_id[:12]}…" if len(product_id) > 12 else product_id
    lines = [
        "AI-Factory · New product",
        f"Source: {source}",
        f"ID `{short_id}`",
    ]
    if idea_snippet.strip():
        clip = idea_snippet.strip()[:400]
        if len(idea_snippet.strip()) > 400:
            clip += "…"
        lines.append(f"Idea: {clip}")

    ok, detail = send_telegram_message_sync("\n".join(lines))
    if not ok:
        logger.debug("telegram new-product notify skipped: %s", detail)
