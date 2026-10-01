#!/usr/bin/env python3
"""
Wipe pipeline products + per-product artifacts so autonomous/Director can start fresh
with landing-focused builds.

Usage (inside app container):
  docker compose exec app python3 /app/scripts/reset_pipeline_landings.py

From repo root (paths default to ./data):
  python3 scripts/reset_pipeline_landings.py [--dry-run]

Afterwards: restart the stack (or at least `app`) so workers reload empty state.
Director will invent the next phrase when auto_pipeline runs (or shorten interval in config).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _rmtree_product_dirs(data_root: Path, dry: bool) -> list[str]:
    removed: list[str] = []
    globs = [
        data_root / "code",
        data_root / "specs",
        data_root / "arch",
        data_root / "bugs",
        data_root / "security",
        data_root / "telemetry",
        data_root / "state",
    ]
    for base in globs:
        if not base.is_dir():
            continue
        for p in sorted(base.glob("prod-*")):
            if p.is_dir():
                removed.append(str(p.relative_to(data_root)))
                if not dry:
                    shutil.rmtree(p, ignore_errors=True)
    return removed


def _sqlite_clear_products_tasks(db_path: Path) -> None:
    """Empty pipeline tables without importing orchestrator (avoids prometheus deps on host)."""
    import sqlite3

    if not db_path.exists():
        print(f"[reset] SQLite missing at {db_path}, skipping DB wipe", file=sys.stderr)
        return
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM products")
            conn.commit()
            print(f"[reset] cleared products + tasks in {db_path}", file=sys.stderr)
        except sqlite3.OperationalError as e:
            print(f"[reset] WARN SQLite clear: {e}", file=sys.stderr)
        finally:
            conn.close()
    except OSError as e:
        print(f"[reset] WARN SQLite: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset pipeline + prod-* artifact trees")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()

    data_root = Path(os.environ.get("AIFACTORY_DATA_ROOT", ROOT / "data"))
    json_path = Path(os.environ.get("PIPELINE_JSON", data_root / "state" / "pipeline.json"))
    db_path = Path(os.environ.get("SQLITE_PATH", data_root / "state" / "pipeline.db"))

    print(f"[reset] data_root={data_root}", file=sys.stderr)

    dirs = _rmtree_product_dirs(data_root, args.dry_run)
    print(f"[reset] removed {len(dirs)} product dirs under data/", file=sys.stderr)
    if args.dry_run:
        for d in dirs[:40]:
            print(f"  would delete: {d}", file=sys.stderr)
        if len(dirs) > 40:
            print(f"  ... and {len(dirs) - 40} more", file=sys.stderr)
        print("[reset] dry-run: would empty pipeline.json + optionally SQLite", file=sys.stderr)
    else:
        empty_state = {"products": {}, "task_queue": []}
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(empty_state, indent=2), encoding="utf-8")
        print(f"[reset] wrote empty {json_path}", file=sys.stderr)

        if os.environ.get("USE_SQLITE", "").strip().lower() in ("1", "true", "yes"):
            _sqlite_clear_products_tasks(db_path)

    print(
        "[reset] Done. Restart services: docker compose restart app\n"
        "[reset] Director phrase: enable general.auto_pipeline in config; next cycle creates a NEW landing idea.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
