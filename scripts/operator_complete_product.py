#!/usr/bin/env python3
"""Operator recovery: mark one marketplace-eligible product COMPLETED, then pause factory."""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.factory_hold import is_factory_on_hold
from core.paths import pipeline_db_path
from core.pipeline_worker_notify import notify_pipeline_worker_wake
from orchestrator.sqlite_manager import SQLiteManager
from orchestrator.worker_utils import delivery_profile_from_product_dict
from web.backend.core.config import AppConfig
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.pipeline_focus import apply_pipeline_focus_mode


def complete_product(pid: str, *, force: bool = False) -> int:
    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            print(f"ERROR: product not found: {pid}", file=sys.stderr)
            return 1

        mq = evaluate_marketplace_quality(
            pid,
            specification=None,
            delivery_profile=delivery_profile_from_product_dict(product),
        )
        print("mq_eligible", mq.get("eligible"), "reasons", mq.get("reasons"))
        if not mq.get("eligible") and not force:
            print("ERROR: product not storefront-eligible (use --force for operator recovery)", file=sys.stderr)
            return 1
        if force and not mq.get("eligible"):
            print("WARN: --force operator recovery; skipping storefront eligibility gate")

        try:
            from web.backend.services.product_followup import (
                set_product_improvement_on_hold,
                set_product_pipeline_on_hold,
            )

            set_product_improvement_on_hold(pid, True)
            set_product_pipeline_on_hold(pid, True)
        except Exception as exc:
            print("operator hold warn (pre):", exc)

        tasks = sm.get_tasks_by_product(pid)
        now = time.time()

        cancelled = 0
        for t in tasks:
            status = str(t.get("status") or "").lower()
            if status in ("pending", "running") and t.get("agent_type") != "__complete__":
                t["status"] = "cancelled"
                t["completed_at"] = now
                t["output_summary"] = "cancelled: operator locked product COMPLETED"
                sm.upsert_task(t)
                cancelled += 1
        if cancelled:
            print("cancelled_active_tasks", cancelled)

        complete_task = next((t for t in sm.get_tasks_by_product(pid) if t.get("agent_type") == "__complete__"), None)
        if not complete_task:
            complete_task = {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": "__complete__",
                "state": "COMPLETED",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {"product_id": pid, "operator_recovery": True},
                "created_at": now,
                "priority": 0,
            }
            sm.upsert_task(complete_task)
            print("created __complete__ task", complete_task["id"])

        complete_task["status"] = "completed"
        complete_task["completed_at"] = now
        complete_task["output_data"] = {"completed": True, "product_id": pid}
        complete_task["output_summary"] = f"Product {pid} pipeline completed (operator recovery)"
        sm.upsert_task(complete_task)

        for key in ("failure_reason", "last_error", "error"):
            product.pop(key, None)
        meta = product.get("metadata")
        if isinstance(meta, dict):
            for key in ("failure_reason", "last_error", "error"):
                meta.pop(key, None)

        product["state"] = "COMPLETED"
        product["updated_at"] = now
        product["completed_at"] = product.get("completed_at") or now
        product["operator_locked"] = True
        product["operator_locked_at"] = now
        product["policy_audit_eligible"] = True
        product["last_policy_audit_at"] = now
        if not isinstance(meta, dict):
            meta = {}
        meta["operator_locked"] = True
        meta["operator_locked_at"] = now
        product["metadata"] = meta
        sm.upsert_product(product)

        try:
            from web.backend.services.product_followup import (
                set_product_improvement_on_hold,
                set_product_pipeline_on_hold,
            )

            set_product_improvement_on_hold(pid, True)
            set_product_pipeline_on_hold(pid, True)
            print("operator_locked pipeline+improvement holds set")
        except Exception as exc:
            print("operator hold warn:", exc)

        try:
            from web.backend.services.funnel_distribute import on_product_completed

            on_product_completed(pid, product)
        except Exception as exc:
            print("funnel_distribute warn:", exc)
        try:
            from web.backend.services.funnel_leads import on_product_state_change

            on_product_state_change(pid, product)
        except Exception as exc:
            print("funnel_leads warn:", exc)
        try:
            from web.backend.services.product_followup import merge_mark_storefront_established_listing

            merge_mark_storefront_established_listing(pid)
        except Exception as exc:
            print("storefront mark warn:", exc)

        # Re-assert terminal state after sidecars (worker may race if factory was running).
        product["state"] = "COMPLETED"
        product["operator_locked"] = True
        product["operator_locked_at"] = product.get("operator_locked_at") or now
        product["updated_at"] = time.time()
        product.pop("failure_reason", None)
        sm.upsert_product(product)

        final = sm.get_product(pid)
        print("FINAL state:", final.get("state") if final else None)
        return 0 if final and str(final.get("state")).upper() == "COMPLETED" else 2
    finally:
        sm.close()


def pause_factory() -> None:
    cfg = AppConfig()
    apply_pipeline_focus_mode(cfg, focus_product_id=None, resume_factory=False)
    cfg.set("general.factory_on_hold", True)
    notify_pipeline_worker_wake()
    print("factory_on_hold", is_factory_on_hold())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-id", required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip storefront eligibility gate (operator recovery only)",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Do not pause factory after completion",
    )
    args = parser.parse_args()
    pid = args.product_id.strip()
    if not args.no_pause:
        pause_factory()
    rc = complete_product(pid, force=bool(args.force))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
