#!/usr/bin/env python3
"""Clear false FAILED state and queue sensible recovery (PM if no code, else keep repair task)."""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from core.paths import pipeline_db_path
    from orchestrator.sqlite_manager import SQLiteManager
    from orchestrator.task_queue_hygiene import is_likely_false_failed_product, recovery_state_after_false_failed
    from web.backend.services.pipeline_reopen import reopen_failed_product

    pids = [
        p.strip()
        for p in sys.argv[1:]
        if p.strip()
    ]
    if not pids:
        pids = [
            "prod-569805b083b1",
            "prod-9388c62f0666",
            "prod-765a5a26f83c",
            "prod-46e66fe613f7",
        ]

    notes = (
        "Unstick false FAILED: regenerate marketing landing from spec (code missing on disk). "
        "Deliver root index.html, hero, pricing, CTA, and pass QA gates."
    )

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        for pid in pids:
            product = sm.get_product(pid)
            if not product:
                print(pid, "not found")
                continue
            tasks = sm.get_tasks_by_product(pid)
            active = [t for t in tasks if str(t.get("status")).lower() in ("pending", "running", "failed")]
            if not is_likely_false_failed_product(product, active):
                print(pid, "not a false-FAILED candidate, state=", product.get("state"))
                continue
            from web.backend.api.products import _product_has_code

            if _product_has_code(pid):
                st = recovery_state_after_false_failed(product, active)
                product["state"] = st
                for k in ("failure_reason", "error", "last_error"):
                    product.pop(k, None)
                product["updated_at"] = time.time()
                sm.upsert_product(product)
                print(pid, "recovered in place →", st)
                continue
            # No code: cancel orphan dev tasks and reopen via PM
            for t in tasks:
                if str(t.get("status")).lower() in ("pending", "running"):
                    t["status"] = "cancelled"
                    t["completed_at"] = time.time()
                    sm.upsert_task(t)
            product["state"] = "FAILED"
            sm.upsert_product(product)
            res = reopen_failed_product(pid, notes, agent_type="pm", target_state="SPEC_WRITTEN")
            print(pid, res)
    finally:
        sm.close()


if __name__ == "__main__":
    main()
