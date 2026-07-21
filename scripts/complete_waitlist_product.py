#!/usr/bin/env python3
"""Operator recovery: complete prod-demo-landing-waitlist when marketplace quality passes."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_overlay import patch_primary_overlay
from core.factory_hold import is_factory_on_hold
from core.paths import pipeline_db_path
from orchestrator.sqlite_manager import SQLiteManager
from orchestrator.worker_utils import delivery_profile_from_product_dict
from web.backend.services.marketplace_quality import evaluate_marketplace_quality

PID = "prod-demo-landing-waitlist"


def main() -> int:
    patch_primary_overlay({"general.factory_on_hold": False})
    print("factory_on_hold:", is_factory_on_hold())

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        product = sm.get_product(PID)
        if not product:
            print("ERROR: product not found")
            return 1

        mq = evaluate_marketplace_quality(
            PID,
            specification=None,
            delivery_profile=delivery_profile_from_product_dict(product),
        )
        print("marketplace eligible:", mq.get("eligible"))
        if not mq.get("eligible"):
            print("ERROR: product not storefront-eligible")
            return 1

        tasks = sm.get_tasks_by_product(PID)
        now = time.time()
        complete_task = next(
            (
                t
                for t in tasks
                if t.get("agent_type") == "__complete__"
                and str(t.get("status") or "").lower() == "pending"
            ),
            None,
        )
        if complete_task:
            complete_task["status"] = "completed"
            complete_task["completed_at"] = now
            complete_task["output_data"] = {"completed": True, "product_id": PID}
            complete_task["output_summary"] = f"Product {PID} pipeline completed (operator recovery)"
            sm.upsert_task(complete_task)
            print("completed task:", complete_task.get("id"))

        for key in ("failure_reason", "last_error", "error"):
            product.pop(key, None)
        meta = product.get("metadata")
        if isinstance(meta, dict):
            for key in ("failure_reason", "last_error", "error"):
                meta.pop(key, None)

        product["state"] = "COMPLETED"
        product["updated_at"] = now
        product["completed_at"] = product.get("completed_at") or now
        sm.upsert_product(product)

        try:
            from web.backend.services.funnel_distribute import on_product_completed

            on_product_completed(PID, product)
        except Exception as exc:
            print("funnel_distribute warn:", exc)
        try:
            from web.backend.services.funnel_leads import on_product_state_change

            on_product_state_change(PID, product)
        except Exception as exc:
            print("funnel_leads warn:", exc)
        try:
            from web.backend.services.product_followup import merge_mark_storefront_established_listing

            merge_mark_storefront_established_listing(PID)
        except Exception as exc:
            print("storefront mark warn:", exc)

        final = sm.get_product(PID)
        print("FINAL state:", final.get("state") if final else None)
        return 0 if final and str(final.get("state")).upper() == "COMPLETED" else 2
    finally:
        sm.close()


if __name__ == "__main__":
    raise SystemExit(main())
