#!/usr/bin/env python3
"""
Destructive: delete ALL products and tasks from the pipeline SQLite DB.

Also resets ``state/pipeline.json`` to an empty catalog so the next JSON→SQLite
sync cannot resurrect stale rows.

Use when you want a clean slate before enqueueing one serious full_software build.

Does NOT delete files under data/code/, data/specs/, etc. unless --also-artifacts.

Examples:
  python3 scripts/wipe_pipeline_products.py --dry-run
  python3 scripts/wipe_pipeline_products.py --yes
  python3 scripts/wipe_pipeline_products.py --yes --also-artifacts
  python3 scripts/wipe_pipeline_products.py --yes --clear-logs
  python3 scripts/wipe_pipeline_products.py --yes --zero-dashboard   # logs + benchmark JSON + orders/pending
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from pathlib import Path


def _clear_logs_dir(data_root: Path) -> int:
    log_dir = data_root / "logs"
    removed = 0
    if log_dir.is_dir():
        for pat in ("*.jsonl", "*.log"):
            for f in log_dir.glob(pat):
                try:
                    f.unlink()
                    removed += 1
                except OSError as e:
                    print(f"skip {f}: {e}")
    if removed:
        print(f"Cleared {removed} file(s) under {log_dir}")
    return removed


def _zero_dashboard_files(data_root: Path, *, clear_logs: bool) -> None:
    if clear_logs:
        _clear_logs_dir(data_root)
    rd = data_root / "reports"
    for fn in ("benchmark_scorecard.json", "benchmark_alerts.json"):
        p = rd / fn
        if p.is_file():
            try:
                p.unlink()
                print(f"Removed {p}")
            except OSError as e:
                print(f"skip {p}: {e}")
    for rel in ("store/orders.json", "state/pending_payments.json"):
        p = data_root / rel
        if p.is_file():
            try:
                p.unlink()
                print(f"Removed {p}")
            except OSError as e:
                print(f"skip {p}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Wipe pipeline products/tasks from SQLite")
    ap.add_argument(
        "--db",
        default=os.environ.get("SQLITE_PATH", "data/state/pipeline.db"),
        help="Path to pipeline.db (default: SQLITE_PATH or data/state/pipeline.db)",
    )
    ap.add_argument("--yes", action="store_true", help="Required to actually delete")
    ap.add_argument(
        "--also-artifacts",
        action="store_true",
        help="Also remove data/code/*, data/specs/*, data/arch/* per-product trees (destructive)",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--clear-logs",
        action="store_true",
        help="Remove *.jsonl and common log files under <data>/logs (LLM logs, metrics history, etc.)",
    )
    ap.add_argument(
        "--zero-dashboard",
        action="store_true",
        help="Clear logs + benchmark scorecard/alerts JSON + store/orders.json + state/pending_payments.json (admin zeros)",
    )
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    data_root = db_path.parent.parent

    if not db_path.is_file():
        print(f"No database at {db_path} — nothing to wipe.")
        return 0

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks")
    (tc,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM products")
    (pc,) = cur.fetchone()
    conn.close()

    print(f"Found {pc} products, {tc} tasks in {db_path}")
    if args.dry_run or not args.yes:
        print("Refusing to modify (use --yes, omit --dry-run).")
        return 0

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks")
    cur.execute("DELETE FROM products")
    conn.commit()
    conn.close()
    print("Deleted all rows from tasks and products.")

    # Reset pipeline.json — migrate() upserts from JSON without clearing SQLite first;
    # leaving a fat JSON after a DB wipe would repopulate thousands of rows on the next sync.
    pipeline_json = db_path.parent / "pipeline.json"
    empty_state = {"products": {}, "task_queue": [], "current_task_id": None}
    pipeline_json.parent.mkdir(parents=True, exist_ok=True)
    pipeline_json.write_text(json.dumps(empty_state, indent=2), encoding="utf-8")
    print(f"Reset {pipeline_json} to empty products + task_queue.")

    if args.clear_logs and not args.zero_dashboard:
        _clear_logs_dir(data_root)

    if args.zero_dashboard:
        _zero_dashboard_files(data_root, clear_logs=True)

    if args.also_artifacts:
        # pipeline.db lives at <data_root>/state/pipeline.db
        root = data_root
        if (root / "code").is_dir():
            for p in (root / "code").iterdir():
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    print(f"removed tree {p}")
        for sub in ("specs", "arch", "state"):
            d = root / sub
            if d.is_dir():
                for p in d.iterdir():
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                        print(f"removed tree {p}")
        print("Artifact dirs under data/code, data/specs, data/arch, data/state cleared per product folder.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
