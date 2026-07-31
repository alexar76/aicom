"""
Post pipeline progress into Corporate Chat (chat_messages.json) so production
updates are visible without running a full Director standup.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

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
    "methodologist": "Methodologist",
}


def notify_pipeline_task_done(
    agent_type: str,
    product_id: str,
    target_state: str,
    idea_snippet: str = "",
) -> None:
    if os.environ.get("CORPORATE_CHAT_PIPELINE_EVENTS", "1").lower() in (
        "0",
        "false",
        "no",
    ):
        return
    try:
        from web.backend.services.corporate_standup import append_chat_message
    except Exception as e:
        logger.debug("Corporate chat import skipped: %s", e)
        return

    at = (agent_type or "").lower()
    label = AGENT_LABELS.get(at, (agent_type or "Agent").title() or "Agent")
    short_id = f"{product_id[:12]}…" if len(product_id) > 12 else product_id
    body = f"**Pipeline:** `{target_state}`\nProduct `{short_id}`"
    if idea_snippet and idea_snippet.strip():
        clip = idea_snippet.strip()[:220]
        if len(idea_snippet.strip()) > 220:
            clip += "…"
        body += f"\n_Idea:_ {clip}"
    try:
        append_chat_message(
            username=f"{label} (agent)",
            text=body,
            admin_username="system",
            role="agent",
            agent_type=at or None,
            kind="pipeline_stage",
        )
    except Exception as e:
        logger.warning("Failed to post pipeline update to corporate chat: %s", e)

    try:
        from web.backend.services.telegram_pipeline_notify import notify_telegram_pipeline_stage

        notify_telegram_pipeline_stage(
            agent_type=agent_type,
            product_id=product_id,
            target_state=target_state,
            idea_snippet=idea_snippet,
        )
    except Exception as e:
        logger.debug("Telegram pipeline notify skipped: %s", e)
