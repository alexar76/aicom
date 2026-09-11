#!/usr/bin/env python3
"""Park a product whose QA↔developer loop is not converging.

HUMAN_REVIEW_PENDING + pipeline hold + cancel active tasks. Operator resume is the
existing reopen / human-gate approve path (grants a fresh repair cycle).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PID = "prod-bdb1634806de"
DEFAULT_REASON = (
    "Operator park: QA↔developer loop is not converging (severity-weighted score plateau "
    "while findings climb). More rounds will keep burning budget without a better tree."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product_id", nargs="?", default=DEFAULT_PID)
    parser.add_argument("--reason", default=DEFAULT_REASON)
    args = parser.parse_args()
    pid = str(args.product_id).strip()

    from core.paths import pipeline_db_path
    from core.pipeline_worker_notify import notify_pipeline_worker_wake
    from orchestrator.sqlite_manager import SQLiteManager
    from web.backend.services.product_followup import (
        is_product_pipeline_on_hold,
        set_product_pipeline_on_hold,
    )

    set_product_pipeline_on_hold(pid, True)

    sm = SQLiteManager(str(pipeline_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            print(json.dumps({"ok": False, "error": "product_not_found", "id": pid}, indent=2))
            return 1

        now = time.time()
        product["state"] = "HUMAN_REVIEW_PENDING"
        product["human_review_kind"] = "qa_repair_stuck"
        product["human_review_reason"] = args.reason
        product["pipeline_stuck_reason"] = args.reason
        product["pipeline_stuck_at"] = now
        product["operator_locked"] = True
        product["operator_locked_at"] = now
        meta = dict(product.get("metadata") or {})
        meta["operator_locked"] = True
        meta["operator_locked_at"] = now
        product["metadata"] = meta
        product["updated_at"] = now
        sm.upsert_product(product)

        cancelled = 0
        for t in sm.get_tasks_by_product(pid):
            status = str(t.get("status") or "").lower()
            if status in ("pending", "running"):
                t["status"] = "cancelled"
                t["completed_at"] = now
                t["output_summary"] = "cancelled: repair loop parked (qa_repair_stuck)"
                sm.upsert_task(t)
                cancelled += 1
    finally:
        sm.close()

    notify_pipeline_worker_wake()

    print(
        json.dumps(
            {
                "ok": True,
                "id": pid,
                "state": "HUMAN_REVIEW_PENDING",
                "human_review_kind": "qa_repair_stuck",
                "pipeline_on_hold": is_product_pipeline_on_hold(pid),
                "cancelled_active_tasks": cancelled,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
