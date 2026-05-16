"""
Migration Utility: JSON → SQLite
=================================
CLI utility to migrate pipeline state from the existing JSON file to a SQLite
database. Can be run as a standalone script or called programmatically.

Usage:
    python -m orchestrator.migrate                     # default paths
    python -m orchestrator.migrate --json path/to/pipeline.json --db path/to/pipeline.db
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from .sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)


def migrate(
    json_path: str = "/app/data/state/pipeline.json",
    db_path: str = "/app/data/state/pipeline.db",
) -> dict:
    """Read JSON state file and bulk-insert into SQLite.

    Args:
        json_path: Path to the JSON state file.
        db_path: Path to the target SQLite database.

    Returns:
        dict with keys: products_migrated, tasks_migrated
    """
    # Validate JSON file exists
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON state file not found: {json_path}")

    # Read JSON
    with open(path, "r") as f:
        data = json.load(f)

    product_dicts = list(data.get("products", {}).values())
    task_dicts = data.get("task_queue", [])

    def _json_latest_ts() -> float:
        latest = 0.0
        for p in product_dicts:
            try:
                latest = max(latest, float(p.get("updated_at") or 0))
            except (TypeError, ValueError):
                pass
            try:
                latest = max(latest, float(p.get("created_at") or 0))
            except (TypeError, ValueError):
                pass
        for t in task_dicts:
            for key in ("created_at", "started_at", "completed_at"):
                try:
                    latest = max(latest, float(t.get(key) or 0))
                except (TypeError, ValueError):
                    pass
        return latest

    # Connect to SQLite — bulk upsert products; tasks merge when SQLite has fresher rows
    manager = SQLiteManager(db_path)
    manager.connect()
    try:
        # Keep JSON→SQLite sync monotonic and non-destructive:
        # bulk upsert JSON rows without clearing existing DB rows.
        json_latest = _json_latest_ts()
        if json_latest:
            logger.debug("Migration JSON latest timestamp: %s", json_latest)

        # Do not wipe DB snapshot here — repeated migrations are used as sync points
        # and may run while workers add fresher SQLite-only records.
        product_count = manager.bulk_insert_products(product_dicts, merge_from_json=True)
        task_count = manager.bulk_insert_tasks(task_dicts, merge_from_json=True)

        result = {
            "products_migrated": product_count,
            "tasks_migrated": task_count,
            "source": json_path,
            "destination": db_path,
        }
        logger.info(
            f"Migration complete: {product_count} products, {task_count} tasks "
            f"from {json_path} to {db_path}"
        )
        return result
    except Exception:
        logger.exception("Migration failed")
        raise
    finally:
        manager.close()


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Migrate pipeline state from JSON to SQLite"
    )
    parser.add_argument(
        "--json",
        default="/app/data/state/pipeline.json",
        help="Path to the JSON state file (default: /app/data/state/pipeline.json)",
    )
    parser.add_argument(
        "--db",
        default="/app/data/state/pipeline.db",
        help="Path to the target SQLite database (default: /app/data/state/pipeline.db)",
    )
    args = parser.parse_args()

    try:
        result = migrate(json_path=args.json, db_path=args.db)
        print(f"Migration successful!")
        print(f"  Products migrated: {result['products_migrated']}")
        print(f"  Tasks migrated:    {result['tasks_migrated']}")
        print(f"  Source:            {result['source']}")
        print(f"  Destination:       {result['destination']}")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
