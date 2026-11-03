"""Spot Auction Mode (#4)

Consumer posts a task to the bus: "need perf audit of landing, budget $5, deadline 60s".
Multiple providers return bids ($2.10, 18s, success_rate 96%). Consumer picks one.

Uber-vibes for AI: split screen — left "task pool", right bids arrive as bubbles with animation.
One demo video = 500 RT.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuctionTask:
    """A task posted to the auction bus by a consumer."""

    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    consumer_hub: str = "local"
    description: str = ""  # NL task description
    budget_usd: float = 5.0
    deadline_s: int = 60  # Max seconds to wait for bids
    constraints: dict[str, Any] = field(default_factory=dict)
    status: str = "open"  # open, bidding, awarded, expired
    created_at: float = field(default_factory=time.time)
    awarded_to: str | None = None  # provider_hub that won


@dataclass
class Bid:
    """A provider's bid for an auction task."""

    bid_id: str = field(default_factory=lambda: f"bid_{uuid.uuid4().hex[:12]}")
    task_id: str = ""
    provider_hub: str = ""
    capability_id: str = ""
    price_usd: float = 0.0
    estimated_latency_ms: int = 0
    success_rate_30d: float = 0.97
    quality_score: float = 0.0
    bond_usd: float = 0.0  # Provider's stake
    created_at: float = field(default_factory=time.time)


class AuctionBus:
    """Real-time auction bus for AI capability tasks.

    In production, this would use WebSocket/SSE for live bid streaming.
    Here we use in-memory with polling support.
    """

    def __init__(self):
        self._tasks: dict[str, AuctionTask] = {}
        self._bids: dict[str, list[Bid]] = {}  # task_id → bids

    # ── Consumer side ─────────────────────────────────────────

    def post_task(
        self,
        description: str,
        budget_usd: float = 5.0,
        deadline_s: int = 60,
        consumer_hub: str = "local",
        constraints: dict[str, Any] | None = None,
    ) -> AuctionTask:
        """Post a task to the auction bus."""
        task = AuctionTask(
            consumer_hub=consumer_hub,
            description=description,
            budget_usd=budget_usd,
            deadline_s=deadline_s,
            constraints=constraints or {},
        )
        self._tasks[task.task_id] = task
        self._bids[task.task_id] = []
        return task

    def get_open_tasks(self) -> list[AuctionTask]:
        """Get all open tasks (for providers to bid on)."""
        now = time.time()
        return [
            t for t in self._tasks.values()
            if t.status == "open" and (now - t.created_at) < t.deadline_s
        ]

    def pick_bid(self, task_id: str, bid_id: str) -> dict[str, Any]:
        """Consumer selects a winning bid."""
        task = self._tasks.get(task_id)
        if not task:
            return {"error": "task not found"}
        if task.status != "open":
            return {"error": f"task is {task.status}"}

        bids = self._bids.get(task_id, [])
        bid = next((b for b in bids if b.bid_id == bid_id), None)
        if not bid:
            return {"error": "bid not found"}

        task.status = "awarded"
        task.awarded_to = bid.provider_hub

        return {
            "task_id": task_id,
            "awarded_to": bid.provider_hub,
            "capability_id": bid.capability_id,
            "price_usd": bid.price_usd,
            "estimated_latency_ms": bid.estimated_latency_ms,
            "consumer_hub": task.consumer_hub,
            "status": "awarded",
        }

    # ── Provider side ──────────────────────────────────────────

    def place_bid(
        self,
        task_id: str,
        provider_hub: str,
        capability_id: str,
        price_usd: float,
        estimated_latency_ms: int,
        success_rate_30d: float = 0.97,
        quality_score: float = 0.9,
        bond_usd: float = 0.0,
    ) -> Bid:
        """Place a bid on an open task."""
        task = self._tasks.get(task_id)
        if not task or task.status != "open":
            raise ValueError("Task not available")

        if price_usd > task.budget_usd:
            raise ValueError(f"Bid ${price_usd} exceeds budget ${task.budget_usd}")

        bid = Bid(
            task_id=task_id,
            provider_hub=provider_hub,
            capability_id=capability_id,
            price_usd=price_usd,
            estimated_latency_ms=estimated_latency_ms,
            success_rate_30d=success_rate_30d,
            quality_score=quality_score,
            bond_usd=bond_usd,
        )
        self._bids.setdefault(task_id, []).append(bid)
        return bid

    def get_bids_for_task(self, task_id: str) -> list[Bid]:
        """Get all bids for a task, ranked by value (quality/price)."""
        bids = self._bids.get(task_id, [])
        # Rank by composite score: quality * success_rate / price
        return sorted(
            bids,
            key=lambda b: (b.quality_score * b.success_rate_30d) / max(b.price_usd, 0.01),
            reverse=True,
        )

    def get_my_bids(self, provider_hub: str) -> list[Bid]:
        """Get all bids placed by a provider."""
        result: list[Bid] = []
        for bids in self._bids.values():
            for b in bids:
                if b.provider_hub == provider_hub:
                    result.append(b)
        return result

    # ── Housekeeping ──────────────────────────────────────────

    def expire_old_tasks(self) -> int:
        """Mark expired tasks and return count."""
        now = time.time()
        count = 0
        for task in self._tasks.values():
            if task.status == "open" and (now - task.created_at) > task.deadline_s:
                task.status = "expired"
                count += 1
        return count

    def stats(self) -> dict[str, Any]:
        return {
            "open_tasks": sum(1 for t in self._tasks.values() if t.status == "open"),
            "awarded_tasks": sum(1 for t in self._tasks.values() if t.status == "awarded"),
            "expired_tasks": sum(1 for t in self._tasks.values() if t.status == "expired"),
            "total_bids": sum(len(bids) for bids in self._bids.values()),
        }
