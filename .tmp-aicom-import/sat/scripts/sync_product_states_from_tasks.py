#!/usr/bin/env python3
"""One-shot repair: align products.state with task queue in SQLite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "1")
    from orchestrator.sqlite_manager import SQLiteManager
    from orchestrator.pipeline_state_sync import (
        infer_product_state_from_tasks,
        normalize_product_state,
        reconcile_product_state,
    )

    db = os.environ.get("SQLITE_PATH", str(ROOT / "data/state/pipeline.db"))
    sm = SQLiteManager(db)
    sm.connect()
    try:
        products = {p["id"]: p for p in sm.get_all_products()}
        tasks = sm.get_all_tasks()
        by_pid: dict[str, list] = {}
        for t in tasks:
            by_pid.setdefault(str(t["product_id"]), []).append(t)

        fixed = 0
        for pid, product in products.items():
            ptasks = by_pid.get(pid, [])
            before = normalize_product_state(product.get("state"))
            inferred = infer_product_state_from_tasks(ptasks, fallback=before)
            if reconcile_product_state(product, ptasks):
                sm.upsert_product(product)
                fixed += 1
                print(f"{pid}: {before} → {product.get('state')} (inferred {inferred})")
        print(f"Repaired {fixed} product(s)")
    finally:
        sm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
