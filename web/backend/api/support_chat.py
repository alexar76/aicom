"""
Public support chat API — **Lumen** floating assistant + triage → pipeline / Director queue.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from core.paths import support_sessions_dir
from web.backend.schemas.api_requests import SupportCreateSessionRequest, SupportPostMessageRequest
from web.backend.services import prompt_safety, support_agent
from web.backend.services.support_agent import SupportTurnResult
from web.backend.services.support_pipeline import (
    append_director_escalation,
    inject_user_support_bug,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support", tags=["support"])

_SESSIONS_DIR = support_sessions_dir()

_RATE: dict[str, list[float]] = {}
_RATE_WINDOW_SEC = 3600.0
_RATE_MAX_MESSAGES = 40
_RATE_MAX_SESSIONS = 8


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _support_token_required() -> bool:
    """When true, session reads/writes require X-AIF-Support-Token from create_session (production default)."""
    return _truthy("AIFACTORY_SUPPORT_REQUIRE_TOKEN", "1")


def _verify_session_token(sess: dict[str, Any], token: Optional[str]) -> None:
    if not _support_token_required():
        return
    expected = sess.get("access_token")
    if not expected or not isinstance(expected, str):
        raise HTTPException(
            status_code=410,
            detail="Session expired. Open the chat again.",
        )
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid session token. Open the chat again.",
        )


def _client_ip(request: Request) -> str:
    from web.backend.http.client_ip import client_ip as resolve_client_ip

    return resolve_client_ip(request)


def _rate_check(ip: str, bucket: str, max_hits: int) -> None:
    now = time.time()
    key = f"{ip}:{bucket}"
    hits = _RATE.setdefault(key, [])
    while hits and hits[0] < now - _RATE_WINDOW_SEC:
        hits.pop(0)
    if len(hits) >= max_hits:
        raise HTTPException(
            status_code=429,
            detail="Too many requests from this network. Try again later.",
        )
    hits.append(now)


def _session_path(sid: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", sid)
    if not safe.startswith("spt-"):
        raise HTTPException(status_code=400, detail="Invalid session")
    return _SESSIONS_DIR / f"{safe}.json"


def _load_session(sid: str) -> dict[str, Any]:
    p = _session_path(sid)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Corrupt session")


def _save_session(data: dict[str, Any]) -> None:
    sid = data.get("id") or ""
    p = _session_path(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _ui_context_dict(ctx: Optional[Any]) -> dict[str, str]:
    if ctx is None:
        return {}
    if hasattr(ctx, "model_dump"):
        raw = ctx.model_dump(exclude_none=True)
    elif isinstance(ctx, dict):
        raw = ctx
    else:
        return {}
    out: dict[str, str] = {}
    for k in ("current_page", "active_tab", "selected_product_id"):
        v = raw.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[k] = s[:200]
    return out


@router.get("/status")
async def support_status():
    """Public: whether chat is enabled (for storefront widget)."""
    return {
        "enabled": _truthy("AIFACTORY_SUPPORT_CHAT_ENABLED", "1"),
        "require_token": _support_token_required(),
        "bot_name": support_agent.SUPPORT_BOT_NAME,
        "bot_slug": support_agent.SUPPORT_BOT_SLUG,
    }


@router.post("/sessions")
async def create_session(request: Request, body: SupportCreateSessionRequest):
    if not _truthy("AIFACTORY_SUPPORT_CHAT_ENABLED", "1"):
        raise HTTPException(status_code=503, detail="Support chat disabled")
    ip = _client_ip(request)
    _rate_check(ip, "sessions", _RATE_MAX_SESSIONS)

    pid = body.product_id

    sid = f"spt-{uuid.uuid4().hex[:16]}"
    now = time.time()
    access_token = secrets.token_urlsafe(32)
    sess = {
        "id": sid,
        "product_id": pid,
        "created_at": now,
        "updated_at": now,
        "client_ip_hash": str(hash(ip))[-8:],
        "messages": [],
        "access_token": access_token,
        "meta": {
            "bot": support_agent.SUPPORT_BOT_NAME,
            "bot_slug": support_agent.SUPPORT_BOT_SLUG,
            "ui_context": _ui_context_dict(body.ui_context),
        },
    }
    _save_session(sess)
    return {
        "session_id": sid,
        "access_token": access_token,
        "product_id": pid,
        "bot_name": support_agent.SUPPORT_BOT_NAME,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    x_aif_support_token: Optional[str] = Header(None, alias="X-AIF-Support-Token"),
):
    if not _truthy("AIFACTORY_SUPPORT_CHAT_ENABLED", "1"):
        raise HTTPException(status_code=503, detail="Support chat disabled")
    s = _load_session(session_id)
    _verify_session_token(s, x_aif_support_token)
    return {
        "session_id": s["id"],
        "product_id": s.get("product_id"),
        "messages": s.get("messages", []),
        "bot_name": support_agent.SUPPORT_BOT_NAME,
    }


@router.post("/sessions/{session_id}/message")
async def post_message(
    request: Request,
    session_id: str,
    body: SupportPostMessageRequest,
    x_aif_support_token: Optional[str] = Header(None, alias="X-AIF-Support-Token"),
):
    if not _truthy("AIFACTORY_SUPPORT_CHAT_ENABLED", "1"):
        raise HTTPException(status_code=503, detail="Support chat disabled")
    ip = _client_ip(request)
    _rate_check(ip, "messages", _RATE_MAX_MESSAGES)

    sess = _load_session(session_id)
    _verify_session_token(sess, x_aif_support_token)
    now = time.time()
    ui_context = _ui_context_dict(body.ui_context)
    if ui_context:
        meta = sess.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        base_ctx = meta.get("ui_context")
        if not isinstance(base_ctx, dict):
            base_ctx = {}
        meta["ui_context"] = {**base_ctx, **ui_context}
        sess["meta"] = meta
    user_text_raw = body.message.strip()
    inj = prompt_safety.rejection_reason_if_blocked(user_text_raw, context="support")
    user_text = prompt_safety.prepare_untrusted_plain_text(user_text_raw, max_len=4000)

    hist = sess.get("messages") or []
    llm_router = getattr(request.app.state, "llm_router", None)

    snippets = [{"role": m["role"], "content": m["content"]} for m in hist[-20:]]
    if inj:
        turn = SupportTurnResult(
            reply=(
                f"Hi — I'm **{support_agent.SUPPORT_BOT_NAME}**. {inj}\n\n"
                "Please describe in plain language what broke or what you need, without trying to issue model commands."
            ),
            classification="spam",
            confidence=0.99,
            file_pipeline_bug=False,
            escalate_to_director=False,
            product_id=(sess.get("product_id") if str(sess.get("product_id") or "").startswith("prod-") else None),
        )
    else:
        turn = await support_agent.run_support_turn(
            user_message=user_text,
            product_id=sess.get("product_id"),
            history_snippets=snippets,
            llm_router=llm_router,
            ui_context=((sess.get("meta") or {}).get("ui_context") if isinstance(sess.get("meta"), dict) else None),
        )

    hist.append({"role": "user", "content": user_text, "ts": now})
    assistant_meta: dict[str, Any] = {
        "classification": turn.classification,
        "confidence": turn.confidence,
    }
    if inj:
        assistant_meta["prompt_injection_blocked"] = True

    pipeline_result: Optional[dict[str, Any]] = None
    escalation_id: Optional[str] = None

    if turn.file_pipeline_bug and turn.product_id and not inj:
        pipeline_result = inject_user_support_bug(
            turn.product_id,
            user_text,
            sess["id"],
            classification=turn.classification,
        )
        assistant_meta["pipeline"] = pipeline_result
        if pipeline_result.get("ok"):
            turn.reply += (
                "\n\n---\nThanks — I've logged this as a **confirmed defect** for the dev team; "
                "the pipeline queued a fix and a follow-up QA pass."
            )
        elif pipeline_result.get("reason") == "product_not_shipped":
            turn.reply += (
                "\n\n---\nThis product is not storefront-final yet, so I'm not opening a bug ticket; "
                "when the build finishes, please report again from the preview page."
            )
        elif pipeline_result.get("reason") == "dev_fix_already_pending":
            turn.reply += "\n\n---\nA fix task for this product is already pending — I won't duplicate it."

    if turn.escalate_to_director and not inj:
        escalation_id = append_director_escalation(
            thread_id=sess["id"],
            summary=user_text,
            classification=turn.classification,
            product_id=turn.product_id or sess.get("product_id"),
        )
        assistant_meta["director_escalation_id"] = escalation_id
        turn.reply += (
            "\n\n---\nYour business request was sent to the **platform director** — they will decide whether to reply here or spin up a separate initiative."
        )

    hist.append(
        {
            "role": "assistant",
            "content": turn.reply,
            "ts": time.time(),
            "meta": assistant_meta,
        }
    )
    sess["messages"] = hist
    sess["updated_at"] = time.time()
    _save_session(sess)

    return {
        "reply": turn.reply,
        "classification": turn.classification,
        "confidence": turn.confidence,
        "file_pipeline_bug": turn.file_pipeline_bug,
        "escalate_to_director": turn.escalate_to_director,
        "pipeline": pipeline_result,
        "director_escalation_id": escalation_id,
        "bot_name": support_agent.SUPPORT_BOT_NAME,
    }
