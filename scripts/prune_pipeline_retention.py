#!/usr/bin/env python3
"""
Trim pipeline SQLite + artifacts: keep the N most recently updated COMPLETED products,
optionally purge IDEA_RECEIVED backlog, keep in-flight pipeline work.

Does not require the /app container layout — works from repo root with default paths.

Examples:
  python3 scripts/prune_pipeline_retention.py --dry-run
  python3 scripts/prune_pipeline_retention.py --completed-keep 10 --purge-idea-received --yes
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path


TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


def _data_root_from_db(db_path: Path) -> Path:
    # .../state/pipeline.db -> data root is parent of state/
    return db_path.parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune pipeline DB to retention policy")
    ap.add_argument(
        "--db",
        default=os.environ.get("SQLITE_PATH", "data/state/pipeline.db"),
        help="SQLite pipeline.db path",
    )
    ap.add_argument(
        "--completed-keep",
        type=int,
        default=10,
        help="Keep this many most recently updated COMPLETED products (default: 10)",
    )
    ap.add_argument(
        "--keep-backlog",
        action="store_true",
        help="Retain IDEA_RECEIVED products (default: delete backlog).",
    )
    ap.add_argument(
        "--keep-in-flight",
        action="store_true",
        default=True,
        help="Keep products actively moving through the pipeline (state not terminal and not IDEA_RECEIVED). Default: on.",
    )
    ap.add_argument(
        "--drop-in-flight",
        action="store_true",
        help="Do not keep in-flight products (dangerous).",
    )
    ap.add_argument("--yes", action="store_true", help="Actually delete (required)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only")
    args = ap.parse_args()

    purge_idea_received = not args.keep_backlog
    if args.drop_in_flight:
        args.keep_in_flight = False

    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        print(f"No database at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, state, updated_at FROM products")
    rows = cur.fetchall()
    conn.close()

    by_id = {r["id"]: dict(r) for r in rows}

    completed = [r for r in rows if str(r["state"]) == "COMPLETED"]
    completed.sort(key=lambda r: float(r["updated_at"] or 0), reverse=True)
    keep_completed = {r["id"] for r in completed[: max(0, args.completed_keep)]}

    keep: set[str] = set(keep_completed)

    if args.keep_in_flight:
        for r in rows:
            st = str(r["state"])
            if st == "IDEA_RECEIVED" and purge_idea_received:
                continue
            if st in TERMINAL:
                continue
            if st == "IDEA_RECEIVED" and not purge_idea_received:
                keep.add(r["id"])
                continue
            if st != "IDEA_RECEIVED":
                keep.add(r["id"])

    if not args.keep_in_flight and not purge_idea_received:
        for r in rows:
            if str(r["state"]) == "IDEA_RECEIVED":
                keep.add(r["id"])

    drop = [pid for pid in by_id if pid not in keep]

    print(f"Products total: {len(by_id)}")
    print(f"Keep set size: {len(keep)} (completed slots kept: {len(keep_completed)})")
    print(f"Will drop:    {len(drop)}")

    if args.dry_run or not args.yes:
        for pid in drop[:50]:
            print(f"  would drop {pid} state={by_id[pid].get('state')}")
        if len(drop) > 50:
            print(f"  … and {len(drop) - 50} more")
        if not args.yes and not args.dry_run:
            print("Refusing to modify (pass --yes).")
        return 0

    data_root = _data_root_from_db(db_path)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    for pid in drop:
        cur.execute("DELETE FROM tasks WHERE product_id = ?", (pid,))
        cur.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()

    pj = data_root / "state" / "pipeline.json"
    if pj.is_file():
        try:
            doc = json.loads(pj.read_text(encoding="utf-8"))
            products = doc.get("products") if isinstance(doc.get("products"), dict) else {}
            drop_set = set(drop)
            for pid in list(products.keys()):
                if pid in drop_set:
                    products.pop(pid, None)
            doc["products"] = products
            tq = doc.get("task_queue") if isinstance(doc.get("task_queue"), list) else []
            doc["task_queue"] = [
                t for t in tq if isinstance(t, dict) and t.get("product_id") not in drop_set
            ]
            pj.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: could not patch pipeline.json: {e}", file=sys.stderr)

    drop_set = set(drop)
    for pid in drop:
        for sub in ("code", "specs", "arch", "bugs"):
            p = data_root / sub / pid
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        for sub in ("telemetry",):
            p = data_root / sub / pid
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        st = data_root / "state" / pid
        if st.exists():
            shutil.rmtree(st, ignore_errors=True)

    print(f"Dropped {len(drop)} products and cleaned artifacts where present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
