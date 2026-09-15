#!/usr/bin/env python3
"""
Drop SQLite pipeline rows (and on-disk artifacts) for products that are NOT
eligible for the public storefront — same rules as ``public_storefront_listing_eligible``.

Run inside the app container (paths default to /app/data):

  docker compose exec -T app /app/venv/bin/python3 /app/scripts/prune_pipeline_keep_storefront.py

Options:
  --dry-run   Print counts only, no deletes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path


def _ensure_app_paths() -> None:
    if not Path("/app/web/backend").exists():
        print("Run this script inside the AI-Factory container (expected /app layout).", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    _ensure_app_paths()
    os.chdir("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from core.paths import data_root
    from web.backend.api.products import _get_products_map, public_storefront_listing_eligible

    root = data_root()
    db_path = Path(os.environ.get("SQLITE_PATH", str(root / "state" / "pipeline.db")))

    pmap = _get_products_map()
    keep: set[str] = set()
    reasons: dict[str, list[str]] = {}
    for pid, prod in pmap.items():
        ok, rs = public_storefront_listing_eligible(pid, prod)
        if ok:
            keep.add(pid)
        else:
            reasons[pid] = rs

    all_ids = set(pmap.keys())
    drop = sorted(all_ids - keep)
    print(f"Storefront-eligible (keep): {len(keep)}")
    print(f"Prune candidates:          {len(drop)}")

    if args.dry_run:
        for pid in drop[:40]:
            print(f"  would drop {pid} ({reasons.get(pid, [])[:3]})")
        if len(drop) > 40:
            print(f"  … and {len(drop) - 40} more")
        return

    conn = sqlite3.connect(str(db_path))
    try:
        for pid in drop:
            conn.execute("DELETE FROM tasks WHERE product_id = ?", (pid,))
            conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
    finally:
        conn.close()

    pj = root / "state" / "pipeline.json"
    if pj.is_file():
        try:
            doc = json.loads(pj.read_text(encoding="utf-8"))
            products = doc.get("products") if isinstance(doc.get("products"), dict) else {}
            for pid in drop:
                products.pop(pid, None)
            doc["products"] = products
            tq = doc.get("task_queue") if isinstance(doc.get("task_queue"), list) else []
            doc["task_queue"] = [t for t in tq if isinstance(t, dict) and t.get("product_id") not in set(drop)]
            pj.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: could not patch pipeline.json: {e}", file=sys.stderr)

    drop_set = set(drop)
    for pid in drop:
        for sub in ("code", "specs", "arch", "bugs"):
            p = root / sub / pid
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        for globs in (
            root / "telemetry" / pid,
            root / "state" / pid,
        ):
            if globs.exists():
                shutil.rmtree(globs, ignore_errors=True)

    print(f"Dropped {len(drop)} products (+ tasks, artifacts where present).")


if __name__ == "__main__":
    main()
