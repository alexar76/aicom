#!/usr/bin/env python3
"""Apply visual gate autofix to in-flight pipeline products and wake the worker."""

from __future__ import annotations

import sys

from core.paths import code_dir
from orchestrator.sqlite_manager import SQLiteManager
from web.backend.services.visual_gate_autofix import apply_visual_gate_autofix


def main() -> int:
    sm = SQLiteManager()
    sm.connect()
    rows = sm.conn.execute(
        "SELECT id, state FROM products WHERE state NOT IN ('COMPLETED', 'FAILED', 'HUMAN_REVIEW_PENDING')"
    ).fetchall()
    healed = 0
    for product_id, state in rows:
        root = code_dir(product_id)
        if not root.is_dir():
            continue
        actions = apply_visual_gate_autofix(root)
        if actions:
            print(f"{product_id} ({state}): {len(actions)} autofix actions")
            healed += 1
    try:
        from core.pipeline_state_writer import notify_pipeline_worker_wake

        notify_pipeline_worker_wake()
        print("pipeline worker wake sent")
    except Exception as exc:
        print(f"wake skipped: {exc}", file=sys.stderr)
    print(f"healed {healed}/{len(rows)} active products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
