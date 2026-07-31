"""
Discussion API
==============
Endpoints for the Corporate Chat (multi-agent discussion) system.

Provides CRUD for sessions, message management, idea tracking,
and discussion lifecycle (start, pause, resume, conclude).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from web.backend.core.admin_roles import require_admin_with_rbac

from ...discussion.models import (
    AgentType,
    AvailableAgent,
    CreateSessionRequest,
    DiscussionStats,
    IdeaResponse,
    MessageResponse,
    MessagesListResponse,
    SendMessageRequest,
    SessionListResponse,
    SessionResponse,
    SessionStatus,
    UpdateSessionRequest,
)
from ...discussion.engine import DiscussionEngine
from ...discussion import session_manager as sm
from ...discussion.brainstorming import BrainstormingSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/discussions",
    tags=["admin-discussions"],
    dependencies=[Depends(require_admin_with_rbac)],
)

# ── Engine instance ──────────────────────────────────────────────────────────
# Initialised lazily when the first request accesses app.state.llm_router

_engine: Optional[DiscussionEngine] = None
_brainstorming: Optional[BrainstormingSessionManager] = None


def _get_engine(request) -> DiscussionEngine:
    """Get or create the DiscussionEngine singleton."""
    global _engine
    if _engine is None:
        llm_router = getattr(request.app.state, "llm_router", None)
        if llm_router is None:
            raise HTTPException(
                status_code=503,
                detail="LLM router not available",
            )
        _engine = DiscussionEngine(llm_router)
    return _engine


def _get_brainstorming() -> BrainstormingSessionManager:
    """Get or create the BrainstormingSessionManager singleton."""
    global _brainstorming
    if _brainstorming is None:
        _brainstorming = BrainstormingSessionManager()
    return _brainstorming


# ── Agent Metadata ───────────────────────────────────────────────────────────


@router.get("/agents", response_model=list[AvailableAgent])
async def get_available_agents():
    """
    Get the list of available agent types with display metadata.
    Used by the frontend to show agent selection UI.
    """
    return sm.get_available_agents()


# ── Session CRUD ─────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(body: CreateSessionRequest, request):
    """
    Create a new discussion session.

    The session is created in 'pending' status and must be started
    explicitly via POST /sessions/{session_id}/start.
    """
    # Persist-only: do not require LLM (listing / opening sessions must work without keys).
    session = sm.create_session(body)
    return {"session": session}


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: Optional[str] = None,
    session_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List discussion sessions with optional filtering.

    Supports filtering by status (pending, active, paused, completed, cancelled)
    and session_type (brainstorming, feature_discussion, strategy_session, product_idea).
    Results are sorted newest-first.
    """
    status_enum = None
    if status:
        try:
            status_enum = SessionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. "
                f"Must be one of: pending, active, paused, completed, cancelled",
            )

    response = sm.list_sessions(
        status=status_enum,
        session_type=session_type,
        limit=limit,
        offset=offset,
    )
    return response


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request):
    """
    Get a single discussion session with all details.
    """
    # Read-only: must not require DiscussionEngine / LLM (browse sessions without provider keys).
    session = sm.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {"session": session}


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: UpdateSessionRequest, request):
    """
    Update session configuration (topic, config, additional instructions).

    Only allowed while session is in 'pending' or 'paused' status.
    """
    session = sm.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    if body.topic is not None:
        session.topic = body.topic
    if body.config is not None:
        session.config = body.config
    if body.additional_instructions is not None and session.context:
        session.context.additional_instructions = body.additional_instructions
    session = sm.update_session(session)
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session and all its associated messages and ideas.

    This is irreversible.
    """
    success = sm.delete_session(session_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {"success": True, "message": f"Session '{session_id}' deleted"}


# ── Discussion Lifecycle ─────────────────────────────────────────────────────


@router.post("/sessions/{session_id}/start", response_model=SessionResponse)
async def start_session(session_id: str, request):
    """
    Start a discussion session.

    Transitions from 'pending' to 'active' and immediately runs
    the first round of discussion.
    """
    engine = _get_engine(request)
    try:
        session = await engine.start_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"session": session}


@router.post("/sessions/{session_id}/run-round", response_model=SessionResponse)
async def run_round(session_id: str, request):
    """
    Manually trigger the next discussion round.

    Only works if session is in 'active' status.
    """
    engine = _get_engine(request)
    try:
        session = await engine.run_round(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"session": session}


@router.post("/sessions/{session_id}/pause", response_model=SessionResponse)
async def pause_session(session_id: str, request):
    """
    Pause an active discussion session.

    Sets status to 'paused'. Can be resumed later.
    """
    engine = _get_engine(request)
    session = await engine.pause_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {"session": session}


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse)
async def resume_session(session_id: str, request):
    """
    Resume a paused discussion session.

    Sets status back to 'active' and runs the next round.
    """
    engine = _get_engine(request)
    session = await engine.resume_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {"session": session}


@router.post("/sessions/{session_id}/conclude", response_model=SessionResponse)
async def conclude_session(session_id: str, request):
    """
    Manually conclude a discussion session.

    Generates summary, extracts ideas, and saves results.
    """
    engine = _get_engine(request)
    session = await engine.conclude_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )
    return {"session": session}


# ── Messages ─────────────────────────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessagesListResponse,
)
async def get_messages(
    session_id: str,
    limit: int = 200,
    offset: int = 0,
):
    """
    Get messages for a session, paginated.

    Messages are returned newest-first.
    """
    messages, total = sm.get_session_messages(
        session_id, limit=limit, offset=offset
    )
    return {"messages": messages, "total_count": total}


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
async def send_message(session_id: str, body: SendMessageRequest, request):
    """
    Send a human message to a discussion session.

    If the session is 'pending', it will be auto-started.
    If 'active', the message is added and a new round may be triggered
    by calling run-round separately.
    """
    engine = _get_engine(request)
    try:
        message = await engine.add_human_input(
            session_id, body.text, username="Admin"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": message}


@router.delete(
    "/sessions/{session_id}/messages/{message_id}",
)
async def delete_message(session_id: str, message_id: str):
    """
    Delete a single message from a session.
    """
    success = sm.delete_message(session_id, message_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Message '{message_id}' not found in session '{session_id}'",
        )
    return {"success": True}


# ── Ideas ────────────────────────────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/ideas",
    response_model=list[IdeaResponse],
)
async def get_session_ideas(session_id: str):
    """
    Get all ideas extracted from a session.
    """
    ideas = sm.get_session_ideas(session_id)
    return [{"idea": idea} for idea in ideas]


@router.post(
    "/sessions/{session_id}/extract-ideas",
    response_model=list[IdeaResponse],
)
async def extract_ideas(session_id: str, request):
    """
    Extract structured ideas from a session's messages.

    Works best on brainstorming and product_idea sessions.
    """
    engine = _get_engine(request)
    session = await engine.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )

    brainstorming = _get_brainstorming()
    ideas = await brainstorming.extract_ideas_from_session(session)
    return [{"idea": idea} for idea in ideas]


@router.post(
    "/sessions/{session_id}/ideas/{idea_id}/promote",
)
async def promote_idea_to_product(
    session_id: str, idea_id: str, request
):
    """
    Promote a brainstorming idea to a pipeline product.

    Creates a new product entry in the pipeline and marks the idea
    as converted.
    """
    engine = _get_engine(request)
    session = await engine.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found",
        )

    # Find the idea
    ideas = sm.get_session_ideas(session_id)
    idea = None
    for i in ideas:
        if i.idea_id == idea_id:
            idea = i
            break

    if idea is None:
        raise HTTPException(
            status_code=404,
            detail=f"Idea '{idea_id}' not found in session '{session_id}'",
        )

    brainstorming = _get_brainstorming()
    product_id = await brainstorming.promote_idea_to_product(idea, session)

    if product_id is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to promote idea to product",
        )

    return {
        "success": True,
        "product_id": product_id,
        "message": f"Idea promoted to product '{product_id}'",
    }


# ── Statistics ───────────────────────────────────────────────────────────────


@router.get("/stats", response_model=DiscussionStats)
async def get_discussion_stats():
    """
    Get aggregate statistics across all discussion sessions.
    """
    return sm.get_discussion_stats()
