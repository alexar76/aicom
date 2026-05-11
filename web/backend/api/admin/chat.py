"""
Corporate Chat API
==================
Endpoints for the admin corporate chat feature.
Supports sending, reading, and deleting chat messages,
Owner display name, Director standup schedule, and manual standup trigger.

See docs/corporate-chat-vs-discussions.md for Corporate Chat vs Brainstorming.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.corporate_standup import run_standup_session

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/chat",
    tags=["admin-chat"],
    dependencies=[Depends(require_admin_with_rbac)],
)

# ── Constants ────────────────────────────────────────────────────────────────

CHAT_FILE = "/app/data/state/chat_messages.json"
ADMIN_CONFIG_FILE = "/app/data/config/admin.json"


# ── Pydantic Models ──────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Message text")


class MessageResponse(BaseModel):
    id: str
    username: str
    text: str
    timestamp: str
    admin_username: str
    role: Optional[str] = None
    agent_type: Optional[str] = None
    kind: Optional[str] = None


class MessagesListResponse(BaseModel):
    messages: list[MessageResponse]


class SingleMessageResponse(BaseModel):
    message: MessageResponse


class DeleteSuccessResponse(BaseModel):
    success: bool


class ChatSettingsResponse(BaseModel):
    """Owner display name + Director standup schedule (stored in admin.json)."""

    chat_username: str = Field(description="Owner display name in Corporate Chat")
    director_standup_enabled: bool = False
    director_standup_time: str = "09:00"
    director_standup_timezone: str = "UTC"


class UpdateChatSettingsRequest(BaseModel):
    chat_username: Optional[str] = Field(None, min_length=1, max_length=50)
    director_standup_enabled: Optional[bool] = None
    director_standup_time: Optional[str] = None
    director_standup_timezone: Optional[str] = None


# ── Helper Functions ─────────────────────────────────────────────────────────


def _load_messages() -> list[dict]:
    """Load messages from the JSON file. Returns empty list if file does not exist."""
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load chat messages: {e}")
            return []
    return []


def _save_messages(messages: list[dict]):
    """Save messages to the JSON file, creating directories if needed."""
    os.makedirs(os.path.dirname(CHAT_FILE), exist_ok=True)
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def _get_admin_config() -> dict:
    """Load admin.json or empty dict."""
    if not os.path.exists(ADMIN_CONFIG_FILE):
        return {}
    try:
        with open(ADMIN_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_admin_config(config: dict):
    os.makedirs(os.path.dirname(ADMIN_CONFIG_FILE), exist_ok=True)
    with open(ADMIN_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _get_chat_settings_model() -> ChatSettingsResponse:
    cfg = _get_admin_config()
    return ChatSettingsResponse(
        chat_username=cfg.get("chat_username") or "Owner",
        director_standup_enabled=bool(cfg.get("director_standup_enabled", False)),
        director_standup_time=(cfg.get("director_standup_time") or "09:00").strip(),
        director_standup_timezone=(cfg.get("director_standup_timezone") or "UTC").strip(),
    )


def _validate_hhmm(s: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}$", (s or "").strip()))


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/messages", response_model=MessagesListResponse)
async def get_messages():
    """All chat messages sorted by time ascending."""
    messages = _load_messages()
    messages.sort(key=lambda m: m.get("timestamp", ""))
    return {"messages": messages}


async def _background_route_owner_message(router: Any, message_id: str) -> None:
    try:
        from web.backend.services.owner_chat_routing import process_owner_message_by_id

        await process_owner_message_by_id(router, message_id)
    except Exception:
        logger.exception("Background Owner message routing failed for %s", message_id)


@router.post("/messages", response_model=SingleMessageResponse, status_code=201)
async def send_message(
    request: Request,
    background_tasks: BackgroundTasks,
    body: SendMessageRequest,
    admin: dict = Depends(require_admin_with_rbac),
):
    """
    Human Owner posts to Corporate Chat (display name from settings).
    """
    cfg = _get_admin_config()
    chat_username = cfg.get("chat_username") or "Owner"
    admin_username = admin.get("sub", "unknown")

    message: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "username": chat_username,
        "text": body.text,
        "timestamp": datetime.utcnow().isoformat(),
        "admin_username": admin_username,
        "role": "owner",
        "kind": "owner_message",
    }

    messages = _load_messages()
    messages.append(message)
    _save_messages(messages)

    logger.info(
        f"Corporate chat (Owner): admin '{admin_username}' as '{chat_username}': {message['id']}"
    )

    router_llm = getattr(request.app.state, "llm_router", None)
    if router_llm is not None:
        background_tasks.add_task(_background_route_owner_message, router_llm, message["id"])

    return {"message": message}


@router.delete("/messages/{message_id}", response_model=DeleteSuccessResponse)
async def delete_message(message_id: str):
    messages = _load_messages()
    initial_count = len(messages)
    messages = [m for m in messages if m.get("id") != message_id]

    if len(messages) == initial_count:
        raise HTTPException(status_code=404, detail=f"Message '{message_id}' not found")

    _save_messages(messages)
    logger.info(f"Chat message deleted: {message_id}")

    return {"success": True}


@router.get("/settings", response_model=ChatSettingsResponse)
async def get_chat_settings():
    """Owner display name + Director standup schedule."""
    return _get_chat_settings_model()


@router.post("/settings", response_model=ChatSettingsResponse)
async def update_chat_settings(body: UpdateChatSettingsRequest):
    """Merge-update chat / standup settings in admin.json."""
    cfg = _get_admin_config()

    if body.chat_username is not None:
        nu = body.chat_username.strip()
        if not nu:
            raise HTTPException(status_code=400, detail="chat_username must be non-empty")
        if len(nu) > 50:
            raise HTTPException(status_code=400, detail="chat_username at most 50 characters")
        cfg["chat_username"] = nu

    if body.director_standup_enabled is not None:
        cfg["director_standup_enabled"] = body.director_standup_enabled

    if body.director_standup_time is not None:
        tt = body.director_standup_time.strip()
        if not _validate_hhmm(tt):
            raise HTTPException(status_code=400, detail="director_standup_time must be HH:MM (24h)")
        parts = tt.split(":")
        h, m = int(parts[0]), int(parts[1])
        cfg["director_standup_time"] = f"{h:02d}:{m:02d}"

    if body.director_standup_timezone is not None:
        tz = body.director_standup_timezone.strip()
        if not tz:
            raise HTTPException(status_code=400, detail="timezone must be non-empty")
        cfg["director_standup_timezone"] = tz

    _save_admin_config(cfg)
    logger.info("Chat / standup settings updated")
    return _get_chat_settings_model()


@router.post("/standup/run")
async def run_standup_now(request: Request):
    """Manually trigger Director standup (does not advance director_standup_last_date)."""
    router_llm = getattr(request.app.state, "llm_router", None)
    if router_llm is None:
        raise HTTPException(status_code=503, detail="LLM router unavailable")

    cfg = _get_admin_config()
    try:
        result = await run_standup_session(router_llm, cfg)
        return result
    except Exception as e:
        logger.exception("Manual standup failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
