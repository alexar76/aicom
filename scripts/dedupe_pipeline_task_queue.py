#!/usr/bin/env python3
"""One-shot: dedupe active tasks and enqueue next step for idle mid-pipeline products."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dedupe-pipeline-queue")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dedupe pipeline task queue and heal idle products")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("USE_SQLITE", "1")
    from orchestrator.sqlite_manager import SQLiteManager
    from orchestrator.task_queue_hygiene import append_product_task, enforce_task_queue_hygiene, unstick_blocked_tasks
    from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW

    db = os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db")
    sm = SQLiteManager(db)
    sm.connect()
    products_list = sm.get_all_products()
    products = {p["id"]: p for p in products_list}
    task_queue: list = []
    for p in products_list:
        task_queue.extend(sm.get_tasks_by_product(p["id"]))

    now = time.time()
    before_active = sum(
        1 for t in task_queue if str(t.get("status") or "").lower() in ("pending", "running")
    )

    if not args.dry_run:
        if unstick_blocked_tasks(products, task_queue, now):
            for t in task_queue:
                if str(t.get("status") or "").lower() in ("cancelled", "pending"):
                    sm.upsert_task(t)
        if enforce_task_queue_hygiene(products, task_queue, now):
            for t in task_queue:
                if str(t.get("status") or "").lower() == "cancelled":
                    sm.upsert_task(t)
        healed = 0
        for pid, product in products.items():
            st = str(product.get("state") or "").upper()
            if st in ("COMPLETED", "FAILED", "CANCELLED", "IDEA_RECEIVED"):
                continue
            has_active = any(
                t.get("product_id") == pid
                and str(t.get("status") or "").lower() in ("pending", "running")
                for t in task_queue
            )
            if has_active:
                continue
            flow = PIPELINE_AGENT_FLOW.get(st)
            if not flow:
                continue
            agent_type, next_state = flow
            import uuid

            next_task = {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": agent_type,
                "state": next_state,
                "status": "pending",
                "retry_count": 0,
                "max_retries": 7,
                "input_data": {"product_id": pid, "idea": product.get("idea", "")},
                "created_at": now,
                "priority": 5,
            }
            if append_product_task(task_queue, next_task, products):
                sm.upsert_task(next_task)
                sm.upsert_product(product)
                healed += 1
                logger.info("Healed %s (%s) -> %s/%s", pid, st, agent_type, next_state)
        logger.info("Healed %s idle products", healed)
    else:
        logger.info("[dry-run] would run hygiene on %s active tasks", before_active)

    after_active = sum(
        1 for t in task_queue if str(t.get("status") or "").lower() in ("pending", "running")
    )
    logger.info("Active tasks: %s -> %s", before_active, after_active)
    sm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
