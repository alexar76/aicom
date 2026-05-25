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

# Per-subscriber queue depth. Drops + warns when a slow subscriber falls behind
# instead of blocking the publisher. Override via env if a subscriber legitimately
# needs more headroom (e.g. batched DB writer).
_DEFAULT_QUEUE_MAXSIZE = 1024


# ── Event Bus ─────────────────────────────────────────────────────────────────


class EventBus:
    """Async pub/sub event bus with per-subscriber queues + worker tasks.

    Design:
        - subscribe() creates an asyncio.Queue and a background worker that
          drains it into the user callback. Workers are lazy: created on
          first publish in a running event loop.
        - publish() enqueues into each subscriber's queue with put_nowait
          (non-blocking). If a queue is full (slow subscriber), the event is
          DROPPED and a warning is logged — better than blocking the
          publisher and stalling the whole pipeline.
        - One slow subscriber cannot block others (workers run independently).
        - Swappable to Redis/NATS later: the put_nowait+worker pattern maps
          cleanly to LPUSH+consumer-group / NATS subject+JetStream.
    """

    def __init__(self, queue_maxsize: int = _DEFAULT_QUEUE_MAXSIZE) -> None:
        self._subscribers: dict[str, list[tuple[str, Subscriber]]] = {}
        # Keyed by sub_id (unique across event types).
        self._queues: dict[str, asyncio.Queue[PipelineEvent]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._queue_maxsize = max(1, int(queue_maxsize))
        self._drop_counts: dict[str, int] = {}

    def subscribe(self, event_type: str, callback: Subscriber) -> str:
        """Register a callback for ``event_type``. Returns a subscription id for unsubscribe."""
        sub_id = uuid.uuid4().hex[:8]
        self._subscribers.setdefault(event_type, []).append((sub_id, callback))
        # The queue and worker task are created lazily on the first publish
        # inside a running event loop — `subscribe` is often called from sync
        # init code where no loop is yet running.
        logger.debug(
            "EventBus subscribe: %s → %s (sub_id=%s)",
            event_type, getattr(callback, "__name__", callback), sub_id,
        )
        return sub_id

    def unsubscribe(self, event_type: str, sub_id: str) -> bool:
        """Remove a subscription and tear down its queue + worker. Returns True if found."""
        subs = self._subscribers.get(event_type, [])
        for i, (sid, _) in enumerate(subs):
            if sid == sub_id:
                subs.pop(i)
                task = self._tasks.pop(sid, None)
                if task and not task.done():
                    task.cancel()
                self._queues.pop(sid, None)
                self._drop_counts.pop(sid, None)
                logger.debug("EventBus unsubscribe: %s sub_id=%s", event_type, sub_id)
                return True
        return False

    def _ensure_worker(self, sub_id: str, callback: Subscriber) -> asyncio.Queue[PipelineEvent] | None:
        """Lazily create a queue + worker for sub_id. Returns the queue, or None if no loop."""
        existing = self._queues.get(sub_id)
        if existing is not None:
            return existing
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues[sub_id] = queue
        self._tasks[sub_id] = loop.create_task(self._worker(sub_id, callback, queue))
        return queue

    async def _worker(
        self,
        sub_id: str,
        callback: Subscriber,
        queue: asyncio.Queue[PipelineEvent],
    ) -> None:
        """Drain `queue` into `callback`. One slow callback cannot stall publish."""
        while True:
            event = await queue.get()
            try:
                await callback(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "EventBus subscriber %s (sub_id=%s) failed for %s",
                    getattr(callback, "__name__", callback), sub_id, type(event).__name__,
                )
            finally:
                queue.task_done()

    async def publish(self, event: PipelineEvent) -> None:
        """Enqueue an event for all subscribers of its type.

        Non-blocking per subscriber: full queue → DROP with warning (the
        slow consumer is the failure, not the publisher). One subscriber
        cannot stall others. Awaiting this coroutine only schedules the
        delivery; the user callback may still be running.
        """
        event_type = type(event).__name__
        subs = self._subscribers.get(event_type, [])
        if not subs:
            return
        logger.debug(
            "EventBus publish: %s event_id=%s → %d subscribers",
            event_type, event.event_id, len(subs),
        )
        for sub_id, callback in subs:
            queue = self._ensure_worker(sub_id, callback)
            if queue is None:
                # No running event loop — best-effort direct await (sync path).
                try:
                    await callback(event)
                except Exception:
                    logger.exception(
                        "EventBus direct-dispatch %s failed for %s",
                        getattr(callback, "__name__", callback), event_type,
                    )
                continue
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._drop_counts[sub_id] = self._drop_counts.get(sub_id, 0) + 1
                drops = self._drop_counts[sub_id]
                # Log every drop at WARNING, but throttle the noisy ones to
                # only powers of two after the first 10 (1,2,...,10,16,32,64,...).
                if drops <= 10 or (drops & (drops - 1)) == 0:
                    logger.warning(
                        "EventBus DROP %s for slow subscriber %s (sub_id=%s, total drops=%d)",
                        event_type, getattr(callback, "__name__", callback), sub_id, drops,
                    )

    def publish_background(self, event: PipelineEvent) -> None:
        """Schedule publish in the running loop without awaiting. Safe to call from sync code."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.publish(event))

    # ── Diagnostics ───────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return queue depths + drop counts per subscriber for /admin diagnostics."""
        return {
            "subscriber_count": sum(len(v) for v in self._subscribers.values()),
            "queue_maxsize": self._queue_maxsize,
            "queues": {
                sub_id: {
                    "depth": q.qsize(),
                    "maxsize": q.maxsize,
                    "drops": self._drop_counts.get(sub_id, 0),
                }
                for sub_id, q in self._queues.items()
            },
        }

    async def shutdown(self) -> None:
        """Cancel all worker tasks. Idempotent. Call on process shutdown."""
        for sub_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._tasks.clear()
        self._queues.clear()
        self._drop_counts.clear()


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
