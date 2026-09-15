"""Mark a product COMPLETED and operator-locked (shared by operator scripts and auto-recovery)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def apply_product_completed_locked(
    product: dict[str, Any],
    task_queue: list[dict[str, Any]],
    *,
    now: float | None = None,
    reason: str = "auto_recovery",
) -> None:
    """Update in-memory product + task queue; does not pause the whole factory."""
    pid = str(product.get("id") or "").strip()
    if not pid:
        return
    ts = now if now is not None else time.time()

    for t in task_queue:
        if t.get("product_id") != pid:
            continue
        status = str(t.get("status") or "").lower()
        if status in ("pending", "running") and t.get("agent_type") != "__complete__":
            t["status"] = "cancelled"
            t["completed_at"] = ts
            t["output_summary"] = f"cancelled: {reason} COMPLETED"

    complete_task = next(
        (t for t in task_queue if t.get("product_id") == pid and t.get("agent_type") == "__complete__"),
        None,
    )
    if not complete_task:
        complete_task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "product_id": pid,
            "agent_type": "__complete__",
            "state": "COMPLETED",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {"product_id": pid, reason: True},
            "created_at": ts,
            "priority": 0,
        }
        task_queue.append(complete_task)

    complete_task["status"] = "completed"
    complete_task["completed_at"] = ts
    complete_task["output_data"] = {"completed": True, "product_id": pid, "reason": reason}
    complete_task["output_summary"] = f"Product {pid} pipeline completed ({reason})"

    for key in ("failure_reason", "last_error", "error", "human_review_kind", "human_review_reason"):
        product.pop(key, None)
    meta = product.get("metadata")
    if isinstance(meta, dict):
        for key in ("failure_reason", "last_error", "error"):
            meta.pop(key, None)
    else:
        meta = {}

    product["state"] = "COMPLETED"
    product["updated_at"] = ts
    product["completed_at"] = product.get("completed_at") or ts
    product["operator_locked"] = True
    product["operator_locked_at"] = ts
    product["policy_audit_eligible"] = True
    product["last_policy_audit_at"] = ts
    product["quality_repair_round"] = 0
    meta["operator_locked"] = True
    meta["operator_locked_at"] = ts
    meta["auto_recovery_reason"] = reason
    product["metadata"] = meta
    product["auto_recovery_at"] = ts

    try:
        from web.backend.services.product_followup import (
            merge_mark_storefront_established_listing,
            set_product_improvement_on_hold,
            set_product_pipeline_on_hold,
        )

        # Storefront polish hold is fine. pipeline_on_hold freezes repair: if sharper
        # detectors later reopen COMPLETED → BUG_FOUND, a held product never gets a
        # developer task (Sentinel stranded after auto-recovery round 42).
        set_product_improvement_on_hold(pid, True)
        if reason == "auto_recovery":
            set_product_pipeline_on_hold(pid, False)
        else:
            set_product_pipeline_on_hold(pid, True)
        merge_mark_storefront_established_listing(pid)
    except Exception:
        logger.debug("product followup sidecars failed for %s", pid, exc_info=True)

    try:
        from web.backend.services.funnel_distribute import on_product_completed

        on_product_completed(pid, product)
    except Exception:
        logger.debug("funnel_distribute failed for %s", pid, exc_info=True)
    try:
        from web.backend.services.funnel_leads import on_product_state_change

        on_product_state_change(pid, product)
    except Exception:
        logger.debug("funnel_leads failed for %s", pid, exc_info=True)
