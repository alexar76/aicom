"""
Scheduled AI Director standup for Corporate Chat.
Posts agenda, agent-style reports, and follow-up Q&A into chat_messages.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from llm import GenerationConfig, LLMRouter

from web.backend.services.owner_chat_routing import format_standup_owner_context

logger = logging.getLogger(__name__)

from core.paths import chat_messages_path, legacy_admin_path, pipeline_json_path

ADMIN_CONFIG_FILE = legacy_admin_path()
CHAT_FILE = chat_messages_path()
PIPELINE_FILE = pipeline_json_path()

AGENT_ROLES = ("pm", "developer", "qa", "marketing", "devops")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load %s: %s", path, e)
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_admin_config() -> dict:
    return _load_json(ADMIN_CONFIG_FILE, {})


def save_admin_config(cfg: dict) -> None:
    _save_json(ADMIN_CONFIG_FILE, cfg)


def append_chat_message(
    *,
    username: str,
    text: str,
    admin_username: str = "system",
    role: str = "system",
    agent_type: Optional[str] = None,
    kind: str = "normal",
) -> dict:
    messages = _load_json(CHAT_FILE, [])
    msg = {
        "id": str(uuid.uuid4()),
        "username": username,
        "text": text,
        "timestamp": datetime.utcnow().isoformat(),
        "admin_username": admin_username,
        "role": role,
        "kind": kind,
    }
    if agent_type:
        msg["agent_type"] = agent_type
    messages.append(msg)
    _save_json(CHAT_FILE, messages)
    return msg


def _pipeline_digest() -> str:
    data = _load_json(PIPELINE_FILE, {})
    products = data.get("products") or {}
    lines = []
    for pid, p in list(products.items())[:15]:
        idea = (p.get("idea") or "")[:80]
        st = p.get("state") or "?"
        lines.append(f"- {pid}: state={st}, idea={idea}")
    if not lines:
        return "No products in pipeline yet."
    return "\n".join(lines)


def _extract_json_block(text: str) -> Optional[dict]:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def run_standup_session(router: LLMRouter, admin_cfg: Optional[dict] = None) -> dict:
    """
    Full standup: plan → agent reports → Director follow-ups (LLM-orchestrated).
    Returns summary dict with success flag.
    """
    cfg = admin_cfg if admin_cfg is not None else load_admin_config()
    owner_label = cfg.get("chat_username") or cfg.get("owner_display_name") or "Owner"

    append_chat_message(
        username="System",
        text=f"— Standup started (Owner: {owner_label}). —",
        admin_username="system",
        role="system",
        kind="standup_start",
    )

    digest = _pipeline_digest()
    owner_ctx = format_standup_owner_context()

    plan_prompt = f"""You are the AI Director facilitating a daily standup in a software company chat.

Pipeline snapshot:
{digest}

Owner priorities from Corporate Chat (directives & open product feedback):
{owner_ctx}

Produce a concise standup PLAN for today (max 6 bullet lines): priorities, risks to surface, what you want each role to address.
Reflect Owner directives and open feedback where relevant.
Respond with JSON only: {{"plan_lines": ["...", "..."]}}"""

    plan_cfg = GenerationConfig(temperature=0.4, max_tokens=1024, timeout_sec=90.0)
    plan_raw = await router.generate(plan_prompt, task_type="pm_analysis", config=plan_cfg)
    plan_obj = _extract_json_block(plan_raw) or {}
    plan_lines = plan_obj.get("plan_lines") or ["Review pipeline status", "Surface blockers", "Align priorities"]
    plan_text = "**Standup plan (Director)**\n" + "\n".join(f"• {ln}" for ln in plan_lines[:8])

    append_chat_message(
        username="Director AI",
        text=plan_text,
        admin_username="system",
        role="director",
        kind="standup_plan",
    )

    reports_prompt = f"""You simulate brief standup spoken reports from AI agents (first person, one short paragraph each).

Context — pipeline:
{digest}

Owner context (same as Director used for planning):
{owner_ctx}

Today's agenda bullets:
{chr(10).join(plan_lines[:6])}

JSON only format:
{{
  "reports": [
    {{"agent_type":"pm","text":"..."}},
    {{"agent_type":"developer","text":"..."}},
    {{"agent_type":"qa","text":"..."}},
    {{"agent_type":"marketing","text":"..."}},
    {{"agent_type":"devops","text":"..."}}
  ]
}}
Keep each text under 120 words, realistic status / blockers / asks."""

    rep_cfg = GenerationConfig(temperature=0.55, max_tokens=2048, timeout_sec=120.0)
    rep_raw = await router.generate(reports_prompt, task_type="pm_analysis", config=rep_cfg)
    rep_obj = _extract_json_block(rep_raw) or {}
    reports = rep_obj.get("reports") or []

    role_labels = {
        "pm": "PM",
        "developer": "Developer",
        "qa": "QA",
        "marketing": "Marketing",
        "devops": "DevOps",
    }

    for r in reports:
        at = (r.get("agent_type") or "").lower()
        if at not in role_labels:
            continue
        txt = (r.get("text") or "").strip()
        if not txt:
            continue
        append_chat_message(
            username=f"{role_labels.get(at, at)} (agent)",
            text=txt,
            admin_username="system",
            role="agent",
            agent_type=at,
            kind="standup_report",
        )

    fu_prompt = f"""You are the AI Director. Below are agenda lines and agent reports (summarized).

Agenda:
{plan_text}

Your job: identify unclear points and ask 1–3 specific clarifying questions to the right roles. If everything is clear, say so briefly.

JSON only:
{{
  "followups": [
    {{"to_role":"pm","question":"..."}},
    ...
  ],
  "closure": "One-line closing for the standup."
}}
If no followups needed, use empty followups array."""

    fu_cfg = GenerationConfig(temperature=0.35, max_tokens=1536, timeout_sec=90.0)
    fu_raw = await router.generate(fu_prompt, task_type="pm_analysis", config=fu_cfg)
    fu_obj = _extract_json_block(fu_raw) or {}
    followups = fu_obj.get("followups") or []
    closure = (fu_obj.get("closure") or "").strip() or "Standup complete."

    if followups:
        fq_lines = []
        for fu in followups[:5]:
            role = fu.get("to_role") or "team"
            q = fu.get("question") or ""
            fq_lines.append(f"@{role}: {q}")
        append_chat_message(
            username="Director AI",
            text="**Follow-ups**\n" + "\n".join(fq_lines),
            admin_username="system",
            role="director",
            kind="standup_followup",
        )

        clar_prompt = f"""Director asked:
{json.dumps(followups, ensure_ascii=False)}

Agents respond briefly (JSON):
{{"replies":[{{"agent_type":"pm","text":"..."}}, ...]}}"""

        cr_cfg = GenerationConfig(temperature=0.45, max_tokens=1024, timeout_sec=90.0)
        cr_raw = await router.generate(clar_prompt, task_type="pm_analysis", config=cr_cfg)
        cr_obj = _extract_json_block(cr_raw) or {}
        for rep in cr_obj.get("replies") or []:
            at = (rep.get("agent_type") or "").lower()
            txt = (rep.get("text") or "").strip()
            if at in role_labels and txt:
                append_chat_message(
                    username=f"{role_labels[at]} (agent)",
                    text=txt,
                    admin_username="system",
                    role="agent",
                    agent_type=at,
                    kind="standup_clarification",
                )

    append_chat_message(
        username="Director AI",
        text=closure,
        admin_username="system",
        role="director",
        kind="standup_close",
    )

    return {"success": True, "closure": closure}


async def maybe_run_scheduled_standup(app_state: Any) -> None:
    router = getattr(app_state, "llm_router", None)
    if router is None:
        return

    cfg = load_admin_config()
    if not cfg.get("director_standup_enabled", False):
        return

    tz_name = (cfg.get("director_standup_timezone") or "UTC").strip()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    target_hm = (cfg.get("director_standup_time") or "09:00").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", target_hm):
        target_hm = "09:00"
    parts = target_hm.split(":")
    h, m = int(parts[0]), int(parts[1])
    target_hm_norm = f"{h:02d}:{m:02d}"

    if now.strftime("%H:%M") != target_hm_norm:
        return

    today = now.strftime("%Y-%m-%d")
    if cfg.get("director_standup_last_date") == today:
        return

    logger.info("Running scheduled Director standup for %s", today)
    try:
        await run_standup_session(router, cfg)
        cfg = load_admin_config()
        cfg["director_standup_last_date"] = today
        save_admin_config(cfg)
    except Exception as e:
        logger.exception("Standup failed: %s", e)
        append_chat_message(
            username="System",
            text=f"Standup error: {e}",
            admin_username="system",
            role="system",
            kind="standup_error",
        )


async def standup_scheduler_loop(app: Any) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await maybe_run_scheduled_standup(app.state)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Standup scheduler tick failed")
