"""Domain models and API schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AgentStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    VERIFYING = "verifying"
    ESCROWED = "escrowed"
    INVOKING = "invoking"
    COMPLETED = "completed"
    FAILED = "failed"


class ActivityKind(str, Enum):
    AGENT_REGISTERED = "agent.registered"
    AGENT_VERIFIED = "agent.verified"
    TASK_CREATED = "task.created"
    DISCOVERY = "mesh.discovery"
    VERIFICATION = "mesh.verification"
    ESCROW = "mesh.escrow"
    INVOKE = "mesh.invoke"
    SETTLE = "mesh.settle"
    ERROR = "mesh.error"


class AgentRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    endpoint_url: str
    public_key_pem: str = Field(min_length=32, max_length=4096)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    attestation: str = ""
    product_id: str = Field(default="", max_length=80)
    capability_id: str = Field(default="", max_length=80)
    source_hub: str = Field(default="local", max_length=256)

    @field_validator("endpoint_url")
    @classmethod
    def endpoint_https(cls, v: str) -> str:
        if v.startswith("https://"):
            return v.rstrip("/")
        if v.startswith("http://127.0.0.1") or v.startswith("http://localhost"):
            return v.rstrip("/")
        raise ValueError("endpoint_url must use https:// (or http://127.0.0.1 / localhost for local agents)")


class AgentOut(BaseModel):
    id: str
    name: str
    endpoint_url: str
    status: AgentStatus
    trust_score: float
    capabilities: list[str]
    product_id: str = ""
    capability_id: str = ""
    source_hub: str = "local"
    verified_at: Optional[str] = None
    created_at: str


class TaskCreateRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=2000)
    budget_usd: float = Field(gt=0, le=10_000)
    consumer_agent_id: str = ""
    preferred_capabilities: list[str] = Field(default_factory=list, max_length=16)


class MeshHopOut(BaseModel):
    agent_id: str
    agent_name: str
    phase: str
    price_usd: float
    latency_ms: int
    success: bool
    detail: str = ""


class TaskOut(BaseModel):
    id: str
    intent: str
    budget_usd: float
    status: TaskStatus
    selected_agent_id: Optional[str] = None
    total_spent_usd: float = 0.0
    hops: list[MeshHopOut] = Field(default_factory=list)
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class ActivityEventOut(BaseModel):
    id: str
    kind: ActivityKind
    message: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class MeshStatsOut(BaseModel):
    agents_total: int
    agents_verified: int
    tasks_24h: int
    mesh_hops_24h: int
    success_rate_24h: float
    volume_usd_24h: float


def new_id(prefix: str = "") -> str:
    uid = uuid4().hex[:16]
    return f"{prefix}{uid}" if prefix else uid
