#!/usr/bin/env python3
"""Delete pipeline products + tasks + on-disk artifacts (SQLite + pipeline.json)."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("product_ids", nargs="+", help="Product ids to delete")
    ap.add_argument("--yes", action="store_true", help="Confirm destructive delete")
    args = ap.parse_args()

    if not args.yes:
        print("Pass --yes to delete:", ", ".join(args.product_ids))
        sys.exit(1)

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from core.paths import data_root, pipeline_db_path

    drop = [p.strip() for p in args.product_ids if p.strip()]
    db_path = pipeline_db_path()
    conn = sqlite3.connect(str(db_path))
    try:
        for pid in drop:
            conn.execute("DELETE FROM tasks WHERE product_id = ?", (pid,))
            conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
    finally:
        conn.close()

    dr = data_root()
    pj = dr / "state" / "pipeline.json"
    if pj.is_file():
        try:
            doc = json.loads(pj.read_text(encoding="utf-8"))
            products = doc.get("products") if isinstance(doc.get("products"), dict) else {}
            drop_set = set(drop)
            for pid in drop:
                products.pop(pid, None)
            doc["products"] = products
            tq = doc.get("task_queue") if isinstance(doc.get("task_queue"), list) else []
            doc["task_queue"] = [t for t in tq if isinstance(t, dict) and t.get("product_id") not in drop_set]
            pj.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: pipeline.json patch failed: {exc}", file=sys.stderr)

    for pid in drop:
        for sub in ("code", "specs", "arch", "bugs", "telemetry", "state"):
            p = dr / sub / pid
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)

    print(f"Deleted {len(drop)} products: {', '.join(drop)}")


if __name__ == "__main__":
    main()
