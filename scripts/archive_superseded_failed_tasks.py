#!/usr/bin/env python3
"""One-shot: cancel failed tasks superseded by product progress (bulk SQLite update)."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from core.paths import pipeline_db_path
    from orchestrator.task_queue_hygiene import is_superseded_failed_task
    from web.backend.api.products import _get_products_map

    pmap = _get_products_map()
    db_path = pipeline_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = time.time()
    archived = 0
    try:
        rows = conn.execute(
            "SELECT id, product_id, agent_type, status, state, error, created_at, started_at, completed_at, "
            "retry_count, priority FROM tasks WHERE LOWER(status) = 'failed'"
        ).fetchall()
        for row in rows:
            pid = row["product_id"]
            product = pmap.get(pid)
            if not product:
                continue
            task = dict(row)
            task["status"] = "failed"
            if not is_superseded_failed_task(task, product):
                continue
            prev = (row["error"] or "").strip()
            err = f"{prev}; archive_superseded_failed" if prev else "archive_superseded_failed"
            conn.execute(
                "UPDATE tasks SET status = 'cancelled', error = ?, completed_at = COALESCE(completed_at, ?) WHERE id = ?",
                (err[:8000], now, row["id"]),
            )
            archived += 1
        conn.commit()
    finally:
        conn.close()

    print(f"Archived {archived} superseded failed tasks (of {len(rows)} failed rows scanned).")


if __name__ == "__main__":
    main()
