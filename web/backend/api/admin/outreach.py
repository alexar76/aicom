"""
Admin API: outreach channels + announcements (marketing / sales / director broadcasts).

Credentials are never stored here — only env var names on channel rows; values read at send-time.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services import outreach_store
from web.backend.services.outreach_dispatch import dispatch_announcement

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/outreach",
    tags=["admin-outreach"],
    dependencies=[Depends(require_admin_with_rbac)],
)


class ChannelsDoc(BaseModel):
    version: int = 1
    channels: list[dict[str, Any]]


class CreateAnnouncementBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    body_markdown: str = Field(default="", max_length=50000)
    body_plain: Optional[str] = Field(default=None, max_length=50000)
    audience: str = Field(default="all", max_length=64)
    author_role: str = Field(default="marketing", max_length=32)
    channel_ids: list[str] = Field(default_factory=list)


class SuggestCopyBody(BaseModel):
    topic: str = Field(..., min_length=3, max_length=2000)
    tone: str = Field(default="professional, concise", max_length=200)
    audience: str = Field(default="customers and visitors", max_length=200)


@router.get("/channels")
async def get_channels():
    return outreach_store.load_channels()


@router.put("/channels")
async def put_channels(body: ChannelsDoc):
    allowed_types = {"smtp", "webhook", "telegram"}
    ids: set[str] = set()
    for ch in body.channels:
        if not isinstance(ch, dict):
            raise HTTPException(400, detail="Each channel must be an object")
        cid = ch.get("id")
        if not cid or not isinstance(cid, str):
            raise HTTPException(400, detail="Channel id required")
        if cid in ids:
            raise HTTPException(400, detail=f"Duplicate channel id: {cid}")
        ids.add(cid)
        if ch.get("type") not in allowed_types:
            raise HTTPException(400, detail=f"Invalid type for {cid}")
    outreach_store.save_channels(body.model_dump())
    return {"ok": True, "channels": body.channels, "version": body.version}


@router.get("/announcements")
async def list_announcements():
    items = outreach_store.load_announcements()
    return {"items": list(reversed(items))}


@router.post("/announcements", status_code=201)
async def create_announcement(body: CreateAnnouncementBody):
    aid = outreach_store.new_announcement_id()
    now = time.time()
    row = {
        "id": aid,
        "title": body.title.strip(),
        "body_markdown": body.body_markdown.strip(),
        "body_plain": (body.body_plain or "").strip() or None,
        "audience": body.audience.strip() or "all",
        "author_role": body.author_role.strip() or "marketing",
        "channel_ids": body.channel_ids,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "send_log": [],
    }
    outreach_store.upsert_announcement(row)
    return {"announcement": row}


@router.post("/announcements/suggest")
async def suggest_copy(request: Request, body: SuggestCopyBody):
    llm = getattr(request.app.state, "llm_router", None)
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM router not available")

    from llm import GenerationConfig

    prompt = f"""You help an AI software company write a short **audience announcement** (email / blog / Telegram).

Topic / intent:
{body.topic.strip()}

Tone: {body.tone}
Audience: {body.audience}

Return **only** valid JSON:
{{
  "title": "short subject line, max 120 chars",
  "body_plain": "plain text only, 2-6 short paragraphs, no markdown"
}}
"""
    try:
        cfg = GenerationConfig(temperature=0.65, max_tokens=2048, timeout_sec=60.0, json_mode=True)
        text = await llm.generate(prompt, task_type="marketing_copy", config=cfg)
        import json
        import re

        raw = (text or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            raw = m.group(1).strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        title = str(data.get("title") or "").strip()[:500]
        body_plain = str(data.get("body_plain") or "").strip()[:20000]
        if not title or not body_plain:
            raise ValueError("missing fields")
        return {"title": title, "body_plain": body_plain}
    except Exception as e:
        logger.warning("suggest_copy failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not generate copy") from e


@router.post("/announcements/{announcement_id}/send")
async def send_announcement(announcement_id: str):
    ann = outreach_store.get_announcement(announcement_id)
    if ann is None:
        raise HTTPException(404, detail="Announcement not found")
    if ann.get("status") == "sent":
        raise HTTPException(400, detail="Already sent")

    channels_doc = outreach_store.load_channels()
    selected = set(ann.get("channel_ids") or [])
    if selected:
        filtered = [c for c in channels_doc.get("channels") or [] if c.get("id") in selected]
    else:
        filtered = list(channels_doc.get("channels") or [])

    enabled = [c for c in filtered if c.get("enabled")]
    if not enabled:
        raise HTTPException(400, detail="No enabled channels match this announcement")

    logs = await dispatch_announcement(ann, {"version": channels_doc.get("version", 1), "channels": enabled})
    ok_any = any(x.get("ok") for x in logs)
    ann["status"] = "sent" if ok_any else "failed"
    ann["updated_at"] = time.time()
    ann["sent_at"] = time.time()
    ann["send_log"] = logs
    outreach_store.upsert_announcement(ann)
    return {"announcement": ann, "ok": ok_any}
