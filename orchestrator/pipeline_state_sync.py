"""Keep product.state aligned with task queue (and prevent JSON sync downgrades)."""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED"})
_TASK_ACTIVE = frozenset({"pending", "running"})
_TASK_DONE = frozenset({"completed", "failed", "timeout", "cancelled", "blocked"})


@lru_cache(maxsize=1)
def product_state_rank_map() -> dict[str, int]:
    try:
        from orchestrator.pipeline_flow import pipeline_product_states

        states = pipeline_product_states()
    except Exception:
        states = [
            "IDEA_RECEIVED",
            "MARKET_RESEARCHED",
            "SPEC_WRITTEN",
            "MARKET_CONTENT_READY",
            "METHODOLOGY_REVIEWED",
            "ARCH_DESIGNED",
            "DESIGN_CRITIQUED",
            "CODE_COMMITTED",
            "CODE_TESTING",
            "QA_TESTING",
            "BUG_FOUND",
            "DEV_FIXING",
            "SECURITY_SCANNED",
            "HUMAN_REVIEW_PENDING",
            "SALES_ACTIVE",
            "SANDBOX_RUNNING",
            "TELEMETRY_COLLECTING",
            "EVOLUTION_ANALYZING",
            "COMPLETED",
            "DEPLOYED_PRODUCTION",
            "FAILED",
            "CANCELLED",
        ]
    return {str(s).upper(): i for i, s in enumerate(states)}


def normalize_product_state(state: Any) -> str:
    return str(state or "IDEA_RECEIVED").strip().upper() or "IDEA_RECEIVED"


def product_state_rank(state: Any) -> int:
    return product_state_rank_map().get(normalize_product_state(state), -1)


def infer_product_state_from_tasks(
    tasks: list[dict[str, Any]],
    *,
    fallback: str | None = None,
) -> str:
    """Best-effort pipeline state from task rows (target `state` column)."""
    ranks = product_state_rank_map()
    best = normalize_product_state(fallback or "IDEA_RECEIVED")
    best_rank = ranks.get(best, -1)

    for t in tasks:
        agent = str(t.get("agent_type") or "").lower()
        status = str(t.get("status") or "").lower()
        tgt = normalize_product_state(t.get("state"))

        if agent == "__complete__" and status == "completed":
            return "COMPLETED"

        if status not in _TASK_ACTIVE and status not in _TASK_DONE:
            continue
        if status in ("cancelled", "blocked"):
            continue

        r = ranks.get(tgt, -1)
        if r > best_rank:
            best_rank = r
            best = tgt

    return best


def reconcile_product_state(
    product: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> bool:
    """Raise product.state to match tasks when DB/json lag behind. Returns True if changed."""
    if not product:
        return False
    cur = normalize_product_state(product.get("state"))

    if cur == "FAILED":
        try:
            from orchestrator.task_queue_hygiene import (
                is_likely_false_failed_product,
                recovery_state_after_false_failed,
            )

            if is_likely_false_failed_product(product, tasks):
                product["state"] = recovery_state_after_false_failed(product, tasks)
                product["updated_at"] = time.time()
                product.pop("failure_reason", None)
                product.pop("error", None)
                meta = product.get("metadata")
                if isinstance(meta, dict):
                    meta.pop("failure_reason", None)
                    meta.pop("error", None)
                logger.info(
                    "Reconciled false FAILED product %s → %s",
                    product.get("id"),
                    product.get("state"),
                )
                return True
        except Exception as exc:
            logger.debug("false FAILED reconcile skipped: %s", exc)

    if cur in _TERMINAL and cur != "FAILED":
        return False

    inferred = infer_product_state_from_tasks(tasks, fallback=cur)
    if product_state_rank(inferred) <= product_state_rank(cur):
        return False

    product["state"] = inferred
    product["updated_at"] = time.time()
    return True


def reconcile_all_products_from_tasks(
    products: dict[str, Any],
    task_queue: list[dict[str, Any]],
) -> int:
    """Reconcile every product in an in-memory worker snapshot. Returns change count."""
    by_pid: dict[str, list[dict[str, Any]]] = {}
    for t in task_queue:
        pid = t.get("product_id")
        if pid:
            by_pid.setdefault(str(pid), []).append(t)

    n = 0
    for pid, product in products.items():
        if reconcile_product_state(product, by_pid.get(str(pid), [])):
            n += 1
            logger.info("Reconciled product %s state → %s", pid, product.get("state"))
    return n


def sqlite_product_should_keep_over_json(existing: Any, incoming: dict[str, Any]) -> bool:
    """
    During JSON→SQLite migrate, keep SQLite row when it is fresher or more advanced
    than stale pipeline.json (prevents IDEA_RECEIVED clobbering QA/COMPLETED).
    """
    try:
        ex_up = float(existing["updated_at"] or 0)
    except (TypeError, ValueError, KeyError):
        ex_up = 0.0
    try:
        in_up = float(incoming.get("updated_at") or 0)
    except (TypeError, ValueError):
        in_up = 0.0

    if hasattr(existing, "__getitem__"):
        ex_st = normalize_product_state(existing["state"])
    else:
        ex_st = normalize_product_state(getattr(existing, "state", None))
    in_st = normalize_product_state(incoming.get("state"))
    ex_r = product_state_rank(ex_st)
    in_r = product_state_rank(in_st)

    if ex_st in _TERMINAL and in_st not in _TERMINAL:
        return True
    if ex_r > in_r + 1:
        return True
    return ex_up > in_up + 1.0
