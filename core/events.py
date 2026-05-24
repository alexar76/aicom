"""
Event bus for decoupled agent communication.

Pydantic-typed events with async pub/sub. Each subscriber gets an asyncio.Queue
for backpressure — swappable to Redis/NATS later via the same interface.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Event Models ──────────────────────────────────────────────────────────────


class PipelineEvent(BaseModel):
    """Base for all pipeline events."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TaskCompleted(PipelineEvent):
    """Emitted when a task reaches a terminal status."""

    task_id: str
    product_id: str
    agent_type: str
    status: str  # completed | failed | timeout | cancelled
    state: str | None = None
    output_data: dict[str, Any] | None = None
    error: str | None = None


class ProductStateChanged(PipelineEvent):
    """Emitted when a product transitions to a new pipeline state."""

    product_id: str
    old_state: str | None = None
    new_state: str
    workspace_id: str = "default"


class LLMCallLogged(PipelineEvent):
    """Emitted after each successful LLM generate/stream call."""

    provider: str
    model: str
    task_type: str
    tokens_used: int | None = None
    estimated_cost_usd: float | None = None
    duration_ms: float = 0.0


class BuildArtifactReady(PipelineEvent):
    """Emitted when a developer agent produces buildable output."""

    product_id: str
    artifact_path: str
    artifact_type: str  # frontend | backend | docker | contract
    checksum: str | None = None


class SecurityScanCompleted(PipelineEvent):
    """Emitted after security agent finishes scanning a product."""

    product_id: str
    findings_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    passed: bool = False


# ── Subscriber type ───────────────────────────────────────────────────────────

Subscriber = Callable[[PipelineEvent], Coroutine[Any, Any, None]]


# ── Event Bus ─────────────────────────────────────────────────────────────────


class EventBus:
    """Async pub/sub event bus with per-subscriber queues."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[str, Subscriber]]] = {}
        self._queues: dict[str, asyncio.Queue[PipelineEvent]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    def subscribe(self, event_type: str, callback: Subscriber) -> str:
        """Register a callback for ``event_type``. Returns a subscription id for unsubscribe."""
        sub_id = uuid.uuid4().hex[:8]
        self._subscribers.setdefault(event_type, []).append((sub_id, callback))
        logger.debug("EventBus subscribe: %s → %s (sub_id=%s)", event_type, getattr(callback, "__name__", callback), sub_id)
        return sub_id

    def unsubscribe(self, event_type: str, sub_id: str) -> bool:
        """Remove a subscription. Returns True if found and removed."""
        subs = self._subscribers.get(event_type, [])
        for i, (sid, _) in enumerate(subs):
            if sid == sub_id:
                subs.pop(i)
                logger.debug("EventBus unsubscribe: %s sub_id=%s", event_type, sub_id)
                return True
        return False

    async def publish(self, event: PipelineEvent) -> None:
        """Push an event to all subscribers of its type. Fire-and-forget — errors are logged."""
        event_type = type(event).__name__
        subs = self._subscribers.get(event_type, [])
        if not subs:
            return
        logger.debug("EventBus publish: %s event_id=%s → %d subscribers", event_type, event.event_id, len(subs))
        for _sub_id, callback in subs:
            try:
                await callback(event)
            except Exception:
                logger.exception("EventBus subscriber %s failed for %s", getattr(callback, "__name__", callback), event_type)

    def publish_background(self, event: PipelineEvent) -> None:
        """Schedule publish in the running loop without awaiting. Safe to call from sync code."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(event))


# ── Singleton ─────────────────────────────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus_for_tests(bus: EventBus | None = None) -> None:
    """Test helper — replace the process-wide bus instance."""
    global _event_bus
    _event_bus = bus
