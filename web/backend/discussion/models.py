"""
Discussion Models
=================
Pydantic models for the Corporate Chat (multi-agent discussion) system.
Covers sessions, messages, ideas, and API request/response schemas.
"""

from __future__ import annotations

import uuid
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────


class SessionType(str, Enum):
    brainstorming = "brainstorming"
    feature_discussion = "feature_discussion"
    strategy_session = "strategy_session"
    product_idea = "product_idea"


class SessionStatus(str, Enum):
    pending = "pending"
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class AgentType(str, Enum):
    pm = "pm"
    analyst = "analyst"
    architect = "architect"
    dev = "dev"
    qa = "qa"
    devops = "devops"
    security = "security"
    marketing = "marketing"
    sales = "sales"
    evolution_analyst = "evolution_analyst"
    methodologist = "methodologist"
    human = "human"
    system = "system"


# ── Config ─────────────────────────────────────────────────────────────────────


class SessionConfig(BaseModel):
    """Configuration for a discussion session."""

    max_rounds: int = Field(default=5, ge=1, le=20, description="Maximum discussion rounds")
    max_tokens_per_agent: int = Field(default=4000, ge=500, le=16000)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    model_role: str = Field(default="heavy", pattern="^(heavy|light)$")
    allow_human_interrupt: bool = True
    consensus_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    auto_conclude: bool = True
    inactivity_timeout_minutes: int = Field(default=30, ge=5, le=120)


# ── Context ────────────────────────────────────────────────────────────────────


class SessionContext(BaseModel):
    """Contextual information attached to a session."""

    product_id: Optional[str] = None
    product_context: Optional[str] = None
    additional_instructions: Optional[str] = None
    history_summary: Optional[str] = None


# ── Attachment ─────────────────────────────────────────────────────────────────


class Attachment(BaseModel):
    """Structured attachment to a message (idea, proposal, code snippet, etc.)."""

    type: str = Field(..., description="idea | proposal | code_snippet | architecture_diagram | analysis")
    title: str
    data: dict = Field(default_factory=dict)


# ── Message ────────────────────────────────────────────────────────────────────


class MessageMetadata(BaseModel):
    """Metadata about an LLM-generated message."""

    tokens_used: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    parent_message_id: Optional[str] = None


class Message(BaseModel):
    """A single message in a discussion session."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    round_number: int = 1
    agent_type: str = "system"
    sender_name: str = "System"
    content: str
    timestamp: float = Field(default_factory=time.time)
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    attachments: list[Attachment] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**data)


# ── Round ──────────────────────────────────────────────────────────────────────


class Round(BaseModel):
    """A single round of discussion containing multiple agent messages."""

    round_number: int
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    message_ids: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Round":
        return cls(**data)


# ── Results ────────────────────────────────────────────────────────────────────


class IdeaScore(BaseModel):
    """Scoring for a single idea."""

    overall: float = 0.0
    feasibility: float = 0.0
    innovation: float = 0.0
    market_potential: float = 0.0
    effort_estimate: Optional[str] = None  # S, M, L, XL


class Idea(BaseModel):
    """A structured idea generated during brainstorming."""

    idea_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    title: str
    description: str
    author_agent: str
    supporters: list[str] = Field(default_factory=list)
    opposers: list[str] = Field(default_factory=list)
    score: Optional[IdeaScore] = None
    tags: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    converted_to_product: bool = False
    product_id: Optional[str] = None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Idea":
        return cls(**data)


class SessionResults(BaseModel):
    """Aggregated results of a completed session."""

    summary: str = ""
    ideas: list[Idea] = Field(default_factory=list)
    consensus_topics: list[str] = Field(default_factory=list)
    divergence_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    aggregated_rating: Optional[float] = None


# ── Session ────────────────────────────────────────────────────────────────────


class Session(BaseModel):
    """A complete discussion session."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    session_type: SessionType = SessionType.brainstorming
    status: SessionStatus = SessionStatus.pending
    created_by: str = "admin"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    participants: list[str] = Field(default_factory=list)
    context: SessionContext = Field(default_factory=SessionContext)
    config: SessionConfig = Field(default_factory=SessionConfig)
    rounds: list[Round] = Field(default_factory=list)
    results: Optional[SessionResults] = None

    @property
    def message_count(self) -> int:
        """Total number of messages across all rounds."""
        return sum(len(r.message_ids) for r in self.rounds)

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(**data)


# ── API Request / Response Models ──────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    session_type: SessionType = SessionType.brainstorming
    participants: list[str] = Field(..., min_length=1)
    product_id: Optional[str] = None
    additional_instructions: Optional[str] = None
    config: Optional[SessionConfig] = None


class UpdateSessionRequest(BaseModel):
    topic: Optional[str] = None
    config: Optional[SessionConfig] = None
    additional_instructions: Optional[str] = None


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class SessionSummary(BaseModel):
    """Lightweight summary of a session for list views."""

    session_id: str
    topic: str
    session_type: str
    status: str
    participants: list[str]
    message_count: int = 0
    idea_count: int = 0
    created_at: float
    completed_at: Optional[float] = None
    summary_preview: Optional[str] = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total_count: int


class SessionResponse(BaseModel):
    session: Session


class MessageResponse(BaseModel):
    message: Message


class MessagesListResponse(BaseModel):
    messages: list[Message]
    total_count: int


class IdeaResponse(BaseModel):
    idea: Idea


class AvailableAgent(BaseModel):
    agent_type: str
    display_name: str
    description: str
    icon: str
    color: str
    is_available: bool = True


class DiscussionStats(BaseModel):
    total_sessions: int = 0
    active_sessions: int = 0
    completed_sessions: int = 0
    total_messages: int = 0
    total_ideas: int = 0
    sessions_by_type: dict[str, int] = Field(default_factory=dict)
