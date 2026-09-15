"""
Session Manager
===============
CRUD operations and JSON-file persistence for the Corporate Chat
(multi-agent discussion) system.

Data layout:
  /app/data/discussions/
    sessions/       — individual session JSON files
    messages/       — individual message JSON files
    ideas/          — individual idea JSON files
    summary_index.json  — lightweight index for fast list queries
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from .models import (
    AgentType,
    AvailableAgent,
    CreateSessionRequest,
    DiscussionStats,
    Idea,
    Message,
    Round,
    Session,
    SessionListResponse,
    SessionStatus,
    SessionSummary,
    UpdateSessionRequest,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

from core.paths import discussions_dir

BASE_DIR = str(discussions_dir())
SESSIONS_DIR = f"{BASE_DIR}/sessions"
MESSAGES_DIR = f"{BASE_DIR}/messages"
IDEAS_DIR = f"{BASE_DIR}/ideas"
SUMMARY_INDEX_PATH = f"{BASE_DIR}/summary_index.json"

# ── Agent metadata ───────────────────────────────────────────────────────────

AGENT_METADATA: list[dict] = [
    {
        "agent_type": "pm",
        "display_name": "PM Agent",
        "description": "Product Manager — defines requirements, prioritises tasks, manages scope",
        "icon": "Briefcase",
        "color": "#6366f1",
    },
    {
        "agent_type": "analyst",
        "display_name": "Market Analyst",
        "description": "Market research, competitor analysis, trend identification",
        "icon": "TrendingUp",
        "color": "#f59e0b",
    },
    {
        "agent_type": "architect",
        "display_name": "Architect Agent",
        "description": "System architecture design, technology choices, scalability planning",
        "icon": "Building2",
        "color": "#8b5cf6",
    },
    {
        "agent_type": "dev",
        "display_name": "Developer Agent",
        "description": "Software development, implementation, code review",
        "icon": "Code2",
        "color": "#06b6d4",
    },
    {
        "agent_type": "qa",
        "display_name": "QA Agent",
        "description": "Quality assurance, testing strategy, bug detection",
        "icon": "Bug",
        "color": "#10b981",
    },
    {
        "agent_type": "devops",
        "display_name": "DevOps Agent",
        "description": "Infrastructure, deployment, CI/CD, monitoring",
        "icon": "Server",
        "color": "#3b82f6",
    },
    {
        "agent_type": "security",
        "display_name": "Security Agent",
        "description": "Security analysis, threat modelling, vulnerability assessment",
        "icon": "Shield",
        "color": "#ef4444",
    },
    {
        "agent_type": "marketing",
        "display_name": "Marketing Agent",
        "description": "Marketing strategy, content creation, audience analysis",
        "icon": "Megaphone",
        "color": "#ec4899",
    },
    {
        "agent_type": "sales",
        "display_name": "Sales Agent",
        "description": "Sales strategy, pricing, business development",
        "icon": "Handshake",
        "color": "#14b8a6",
    },
    {
        "agent_type": "evolution_analyst",
        "display_name": "Evolution Analyst",
        "description": "Product evolution analysis, growth opportunities, data-driven insights",
        "icon": "LineChart",
        "color": "#a855f7",
    },
    {
        "agent_type": "methodologist",
        "display_name": "Methodologist",
        "description": "Validates the product follows the accepted process for its domain (CRM, helpdesk, LMS, e-commerce, finance, healthcare, ...).",
        "icon": "ClipboardCheck",
        "color": "#0ea5e9",
    },
]


def get_available_agents() -> list[AvailableAgent]:
    """Return metadata for all available agent types."""
    return [AvailableAgent(**m) for m in AGENT_METADATA]


# ── Helper Functions ─────────────────────────────────────────────────────────


def _ensure_dirs():
    """Create data directories if they do not exist."""
    for d in (SESSIONS_DIR, MESSAGES_DIR, IDEAS_DIR, BASE_DIR):
        os.makedirs(d, exist_ok=True)


def _read_json(path: str) -> Optional[dict]:
    """Read and parse a JSON file. Returns None if not found or corrupt."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read JSON {path}: {e}")
        return None


def _write_json(path: str, data: dict):
    """Write a dict to a JSON file, creating directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _delete_file(path: str) -> bool:
    """Delete a file if it exists. Returns True if deleted."""
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError as e:
            logger.warning(f"Failed to delete {path}: {e}")
    return False


# ── Summary Index ────────────────────────────────────────────────────────────

_index_lock = threading.Lock()


def _load_summary_index() -> dict:
    """Load the summary index. Returns dict with 'sessions' list."""
    data = _read_json(SUMMARY_INDEX_PATH)
    if data is None:
        return {"sessions": []}
    return data


def _save_summary_index(index: dict):
    """Save the summary index."""
    with _index_lock:
        _write_json(SUMMARY_INDEX_PATH, index)


def _update_summary_index(session: Session):
    """Add or update an entry in the summary index."""
    index = _load_summary_index()
    sessions = index["sessions"]

    # Remove existing entry for this session
    sessions = [s for s in sessions if s["session_id"] != session.session_id]

    # Build summary entry
    idea_count = 0
    if session.results and session.results.ideas:
        idea_count = len(session.results.ideas)

    summary_entry = SessionSummary(
        session_id=session.session_id,
        topic=session.topic,
        session_type=session.session_type.value,
        status=session.status.value,
        participants=session.participants,
        message_count=session.message_count,
        idea_count=idea_count,
        created_at=session.created_at,
        completed_at=session.completed_at,
        summary_preview=session.results.summary if session.results else None,
    )

    sessions.append(summary_entry.model_dump())
    index["sessions"] = sessions
    index["total_count"] = len(sessions)
    _save_summary_index(index)


def _remove_from_summary_index(session_id: str):
    """Remove an entry from the summary index."""
    index = _load_summary_index()
    sessions = [s for s in index["sessions"] if s["session_id"] != session_id]
    index["sessions"] = sessions
    index["total_count"] = len(sessions)
    _save_summary_index(index)


# ── Session CRUD ─────────────────────────────────────────────────────────────


def create_session(request: CreateSessionRequest) -> Session:
    """Create a new discussion session and persist it."""
    _ensure_dirs()

    session = Session(
        topic=request.topic,
        session_type=request.session_type,
        created_by="admin",
        participants=request.participants,
        context={
            "product_id": request.product_id,
            "additional_instructions": request.additional_instructions,
        },
    )
    if request.config:
        session.config = request.config

    # Persist
    _write_json(f"{SESSIONS_DIR}/{session.session_id}.json", session.to_dict())
    _update_summary_index(session)

    logger.info(
        f"Created discussion session {session.session_id} "
        f"type={session.session_type.value} topic='{session.topic[:60]}'"
    )
    return session


def get_session(session_id: str) -> Optional[Session]:
    """Load a session by ID. Returns None if not found."""
    data = _read_json(f"{SESSIONS_DIR}/{session_id}.json")
    if data is None:
        return None
    return Session.from_dict(data)


def update_session(session: Session) -> Session:
    """Save updated session data back to disk."""
    session.updated_at = __import__("time").time()
    _write_json(f"{SESSIONS_DIR}/{session.session_id}.json", session.to_dict())
    _update_summary_index(session)
    return session


def delete_session(session_id: str) -> bool:
    """Delete a session and its associated messages and ideas."""
    session = get_session(session_id)
    if session is None:
        return False

    # Delete all messages
    for round_obj in session.rounds:
        for msg_id in round_obj.message_ids:
            _delete_file(f"{MESSAGES_DIR}/{msg_id}.json")

    # Delete all ideas
    if session.results and session.results.ideas:
        for idea in session.results.ideas:
            _delete_file(f"{IDEAS_DIR}/{idea.idea_id}.json")

    # Delete session file
    _delete_file(f"{SESSIONS_DIR}/{session_id}.json")
    _remove_from_summary_index(session_id)

    logger.info(f"Deleted discussion session {session_id}")
    return True


def list_sessions(
    status: Optional[SessionStatus] = None,
    session_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> SessionListResponse:
    """List sessions with optional filtering, using the summary index."""
    index = _load_summary_index()
    sessions = index.get("sessions", [])
    total = len(sessions)

    # Sort by created_at descending (newest first)
    sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)

    # Filter
    filtered = []
    for s in sessions:
        if status and s.get("status") != status.value:
            continue
        if session_type and s.get("session_type") != session_type:
            continue
        filtered.append(s)

    # Paginate
    paginated = filtered[offset : offset + limit]

    return SessionListResponse(
        sessions=[SessionSummary(**s) for s in paginated],
        total_count=len(filtered),
    )


def get_discussion_stats() -> DiscussionStats:
    """Compute aggregate statistics across all sessions."""
    index = _load_summary_index()
    sessions = index.get("sessions", [])

    total = len(sessions)
    active = sum(1 for s in sessions if s.get("status") == SessionStatus.active.value)
    completed = sum(1 for s in sessions if s.get("status") == SessionStatus.completed.value)
    total_messages = sum(s.get("message_count", 0) for s in sessions)
    total_ideas = sum(s.get("idea_count", 0) for s in sessions)

    # Count by type
    by_type: dict[str, int] = {}
    for s in sessions:
        t = s.get("session_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return DiscussionStats(
        total_sessions=total,
        active_sessions=active,
        completed_sessions=completed,
        total_messages=total_messages,
        total_ideas=total_ideas,
        sessions_by_type=by_type,
    )


# ── Message Management ───────────────────────────────────────────────────────


def save_message(message: Message) -> Message:
    """Persist a single message."""
    _ensure_dirs()
    _write_json(f"{MESSAGES_DIR}/{message.message_id}.json", message.to_dict())
    return message


def get_message(message_id: str) -> Optional[Message]:
    """Load a message by ID."""
    data = _read_json(f"{MESSAGES_DIR}/{message_id}.json")
    if data is None:
        return None
    return Message.from_dict(data)


def get_session_messages(
    session_id: str,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[Message], int]:
    """Load all messages for a session, paginated, newest first."""
    session = get_session(session_id)
    if session is None:
        return [], 0

    # Collect all message IDs from all rounds
    all_msg_ids: list[str] = []
    for round_obj in session.rounds:
        all_msg_ids.extend(round_obj.message_ids)

    total = len(all_msg_ids)
    # Reverse so newest first
    all_msg_ids.reverse()
    paginated_ids = all_msg_ids[offset : offset + limit]

    messages = []
    for mid in paginated_ids:
        msg = get_message(mid)
        if msg:
            messages.append(msg)

    return messages, total


def delete_message(session_id: str, message_id: str) -> bool:
    """Delete a message and remove its ID from the session's rounds."""
    session = get_session(session_id)
    if session is None:
        return False

    # Remove message ID from rounds
    found = False
    for round_obj in session.rounds:
        if message_id in round_obj.message_ids:
            round_obj.message_ids.remove(message_id)
            found = True
            break

    if not found:
        return False

    # Delete file
    _delete_file(f"{MESSAGES_DIR}/{message_id}.json")
    update_session(session)
    return True


# ── Idea Management ──────────────────────────────────────────────────────────


def save_idea(idea: Idea) -> Idea:
    """Persist an idea."""
    _ensure_dirs()
    _write_json(f"{IDEAS_DIR}/{idea.idea_id}.json", idea.to_dict())
    return idea


def get_session_ideas(session_id: str) -> list[Idea]:
    """Load all ideas for a session."""
    session = get_session(session_id)
    if session is None or session.results is None:
        return []
    return session.results.ideas


def update_idea(idea: Idea) -> Idea:
    """Update an idea in the session's results and persist both."""
    # The idea is stored as part of session.results.ideas
    # We need to find the session and update the idea in-place
    session = get_session(idea.session_id)
    if session is None or session.results is None:
        return idea

    for i, existing in enumerate(session.results.ideas):
        if existing.idea_id == idea.idea_id:
            session.results.ideas[i] = idea
            break

    update_session(session)
    _write_json(f"{IDEAS_DIR}/{idea.idea_id}.json", idea.to_dict())
    return idea
