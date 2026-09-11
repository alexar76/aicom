#!/usr/bin/env python3
"""
Undo mistaken CANCELLED on prod-demo-* products: restore in-flight state and ensure
one pending/running task exists. Never cancels demos — only re-activates them.

  docker compose exec -T app python3 /app/scripts/restore_demo_products_active.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Last known good states before erroneous CANCELLED (operator snapshot May 2026)
DEMO_FALLBACK_STATE = {
    "prod-demo-market-01": "DEV_FIXING",
    "prod-demo-landing-waitlist": "BUG_FOUND",
    "prod-demo-landing-studio": "DEV_FIXING",
    "prod-demo-full-saas-01": "DEV_FIXING",
    "prod-demo-full-iot-01": "COMPLETED",
}

AGENT_FOR_STATE = {
    "IDEA_RECEIVED": ("analyst", "MARKET_RESEARCHED"),
    "MARKET_RESEARCHED": ("pm", "SPEC_WRITTEN"),
    "BUG_FOUND": ("developer", "DEV_FIXING"),
    "DEV_FIXING": ("developer", "DEV_FIXING"),
    "QA_TESTING": ("qa", "QA_TESTING"),
    "SECURITY_SCANNED": ("security", "SECURITY_SCANNED"),
    "EVOLUTION_ANALYZING": ("analyst", "EVOLUTION_ANALYZING"),
}


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "1")
    from orchestrator.sqlite_manager import SQLiteManager

    sm = SQLiteManager(os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db"))
    sm.connect()
    now = time.time()
    try:
        for p in sm.get_all_products():
            pid = str(p.get("id") or "")
            if not pid.startswith("prod-demo-"):
                continue
            st = str(p.get("state") or "").upper()
            if st in ("COMPLETED", "DEPLOYED_PRODUCTION"):
                print(f"SKIP {pid} (already shipped: {st})")
                continue
            if st == "CANCELLED" or st == "FAILED":
                want = DEMO_FALLBACK_STATE.get(pid, "DEV_FIXING")
                p["state"] = want
                p.pop("failure_reason", None)
                p["updated_at"] = now
                sm.upsert_product(p)
                print(f"RESTORE state {pid} -> {want}")
                st = want

            tasks = sm.get_tasks_by_product(pid)
            active = [
                t
                for t in tasks
                if str(t.get("status") or "").lower() in ("pending", "running")
            ]
            if active:
                print(f"OK {pid} {st} ({len(active)} active tasks)")
                continue

            pair = AGENT_FOR_STATE.get(st, ("developer", "DEV_FIXING"))
            agent, task_state = pair
            task = {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": agent,
                "state": task_state,
                "status": "pending",
                "retry_count": 0,
                "max_retries": 7,
                "input_data": {
                    "product_id": pid,
                    "idea": p.get("idea", ""),
                    "admin_instructions": p.get("admin_instructions", ""),
                    "operator_restore": True,
                },
                "created_at": now,
                "priority": 3,
            }
            sm.upsert_task(task)
            print(f"QUEUE {pid} {agent} -> {task_state} ({task['id']})")
    finally:
        sm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
