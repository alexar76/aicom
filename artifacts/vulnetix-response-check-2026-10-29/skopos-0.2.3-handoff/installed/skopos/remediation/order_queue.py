"""The deploy-order queue — how a PUSH-ONLY node agent gets a redeploy order.

The installed SKOPOS node agents have no HTTP server. They enrol, collect, and *push* reports; the
fleet hosts expose no inbound port, which is a property worth protecting rather than breaking. So
the conductor does not call the agent. It **publishes** a signed DeployOrder here, and the agent
picks it up on its next poll, verifies it locally, executes, and reports back.

    conductor ──publish(order)──▶ [queue] ◀──poll──── node agent (outbound only)
                                     │                      │
                                     └──result◀─────────────┘

Why pull is the right shape here:

* **no new attack surface** — nothing on a fleet host starts listening;
* **the agent stays the constrained party** — it verifies the chain (MOMUS-fixed verdict +
  conductor signature + its OWN local service allowlist) before touching anything, so a queue
  compromise cannot make it deploy something it was never authorised to touch;
* **authority stays central** — the agent cannot invent an order, and the conductor cannot execute
  one. Neither side alone can ship code.

Orders are single-use and expire: an order that is claimed is marked taken, and one that is never
claimed becomes stale rather than lingering as a replayable instruction.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# An unclaimed order is worthless after this long — a redeploy instruction should not sit around
# waiting to be replayed against a host whose state has since moved on.
DEFAULT_TTL_S = 900


@dataclass
class QueuedOrder:
    order_id: str
    host: str                       # which node agent it is addressed to
    service: str
    finding_id: str
    order: dict[str, Any]           # the conductor-signed DeployOrder (embeds MOMUS's verdict)
    published_at: float = field(default_factory=time.time)
    claimed_at: float | None = None
    claimed_by: str = ""
    result: dict[str, Any] | None = None

    @property
    def state(self) -> str:
        if self.result is not None:
            return "reported"
        if self.claimed_at is not None:
            return "claimed"
        return "pending"

    @property
    def kind(self) -> str:
        """"deploy" or "rollback" — read from the SIGNED order, never stored separately, so the
        queue's view of what an order is cannot drift from what the agent will verify."""
        return str((self.order or {}).get("kind") or "deploy")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state
        d["kind"] = self.kind
        return d


class OrderQueue:
    """Append-only journal of published orders, their claims, and their results."""

    def __init__(self, path: str, ttl_s: int = DEFAULT_TTL_S):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_s
        self._orders: dict[str, QueuedOrder] = {}
        self._replay()

    def _replay(self) -> None:
        if not self._path.is_file():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind, oid = rec.get("kind"), rec.get("order_id")
            if kind == "publish":
                self._orders[oid] = QueuedOrder(
                    order_id=oid, host=rec.get("host", ""), service=rec.get("service", ""),
                    finding_id=rec.get("finding_id", ""), order=rec.get("order") or {},
                    published_at=float(rec.get("published_at") or time.time()))
            elif kind == "claim" and oid in self._orders:
                self._orders[oid].claimed_at = float(rec.get("claimed_at") or time.time())
                self._orders[oid].claimed_by = rec.get("claimed_by", "")
            elif kind == "result" and oid in self._orders:
                self._orders[oid].result = rec.get("result")

    def _append(self, rec: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    # ── conductor side ──────────────────────────────────────────────────────
    def publish(self, *, host: str, service: str, finding_id: str,
                order: dict[str, Any]) -> QueuedOrder:
        oid = str(order.get("order_id") or f"deploy-{finding_id}-{int(time.time())}")
        q = QueuedOrder(order_id=oid, host=host, service=service, finding_id=finding_id, order=order)
        self._orders[oid] = q
        self._append({"kind": "publish", "order_id": oid, "host": host, "service": service,
                      "finding_id": finding_id, "order": order, "published_at": q.published_at})
        return q

    # ── agent side ──────────────────────────────────────────────────────────
    def claim_for(self, host: str, *, agent_id: str = "") -> QueuedOrder | None:
        """Hand the oldest unexpired, unclaimed order for this host to the agent, ONCE.

        Single-use: a claimed order is never handed out again, so a replayed poll cannot re-run a
        deploy. Stale orders are skipped rather than served.

        Rollbacks jump the queue. A pending undo means a host is currently serving something we have
        decided is wrong; making it wait behind unclaimed forward deploys would extend exactly the
        window the rollback exists to close."""
        now = time.time()
        for q in sorted(self._orders.values(),
                        key=lambda x: (0 if x.kind == "rollback" else 1, x.published_at)):
            if q.host != host or q.state != "pending":
                continue
            if now - q.published_at > self._ttl:
                continue        # expired: an old instruction is not safe to execute now
            q.claimed_at = now
            q.claimed_by = agent_id or host
            self._append({"kind": "claim", "order_id": q.order_id, "claimed_at": now,
                          "claimed_by": q.claimed_by})
            return q
        return None

    def report(self, order_id: str, result: dict[str, Any]) -> bool:
        q = self._orders.get(order_id)
        if q is None or q.claimed_at is None:
            return False        # never report on an order that was not claimed
        q.result = result
        self._append({"kind": "result", "order_id": order_id, "result": result})
        return True

    # ── conductor side, again: waiting for the hand to actually move ─────────
    async def await_result(self, order_id: str, *, timeout_s: float,
                           poll_s: float = 1.0) -> dict[str, Any] | None:
        """Block until the addressed agent reports on this order, or give up.

        The conductor used to publish an order and immediately re-test "after the deploy". The agent
        polls on an interval, so that re-test hit the OLD container: outside dry-run every job would
        read as "regressed after deploy", burn its attempts and escalate, while the patch it was
        judging had not been applied yet. The fix is to wait for the agent's own report.

        Returns the result dict, or ``None`` on timeout — which is NOT a deploy failure and must not
        be reported as one. It means the agent never picked the order up (not installed, stopped,
        wrong host label, expired TTL), and no amount of re-patching addresses that."""
        import asyncio
        deadline = time.time() + max(0.0, timeout_s)
        while True:
            q = self._orders.get(order_id)
            if q is not None and q.result is not None:
                return q.result
            if time.time() >= deadline:
                return None
            await asyncio.sleep(min(poll_s, max(0.05, deadline - time.time())))

    # ── reporting ───────────────────────────────────────────────────────────
    def get(self, order_id: str) -> QueuedOrder | None:
        return self._orders.get(order_id)

    def all(self, limit: int = 50) -> list[dict[str, Any]]:
        return [q.to_dict() for q in sorted(self._orders.values(),
                                            key=lambda x: x.published_at, reverse=True)[:limit]]

    def stats(self) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for q in self._orders.values():
            by_state[q.state] = by_state.get(q.state, 0) + 1
            by_kind[q.kind] = by_kind.get(q.kind, 0) + 1
        results = [(q, q.result or {}) for q in self._orders.values()]
        deployed = sum(1 for _, r in results if r.get("deployed"))
        refused = sum(1 for _, r in results if r.get("refused"))
        # Degradation signals. A loop that ships patches which then have to be undone is failing even
        # while every individual job reports a signed, verified success, so these are counted here
        # rather than derived in a dashboard that might not be looking.
        rolled_back = sum(1 for _, r in results
                          if r.get("rolled_back") or (r.get("rollback") or {}).get("rolled_back"))
        health_failed = sum(1 for _, r in results if r.get("health_gate_failed"))
        needs_human = sum(1 for _, r in results
                          if (r.get("rollback") or {}).get("needs_human") or r.get("needs_human"))
        unclaimed = sum(1 for q, _ in results if q.state == "pending")
        return {"total": len(self._orders), "by_state": by_state, "by_kind": by_kind,
                "deployed": deployed, "refused_by_agent": refused,
                "rolled_back": rolled_back, "health_gate_failed": health_failed,
                "rollback_left_unhealthy": needs_human, "unclaimed": unclaimed,
                "ttl_s": self._ttl}


def queue_from_env(data_dir: str = "") -> OrderQueue:
    d = data_dir or os.environ.get("SKOPOS_REMEDIATION_DIR", "data/remediation")
    return OrderQueue(os.path.join(d, "deploy_orders.jsonl"),
                      ttl_s=int(os.environ.get("SKOPOS_ORDER_TTL_S", str(DEFAULT_TTL_S))))
