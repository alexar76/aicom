"""
Migration Utility: JSON → SQLite
=================================
CLI utility to migrate pipeline state from the existing JSON file to a SQLite
database. Can be run as a standalone script or called programmatically.

Usage:
    python -m orchestrator.migrate                     # default paths
    python -m orchestrator.migrate --json path/to/pipeline.json --db path/to/pipeline.db
    python -m orchestrator.migrate --rollback          # restore latest .bak next to --db
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from core.paths import pipeline_db_path, pipeline_json_path

from .sqlite_manager import SQLiteManager
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


def _backup_db(db_path: str) -> Optional[str]:
    """Copy existing SQLite DB to ``<db>.bak.<timestamp>``. Returns backup path or None."""
    src = Path(db_path)
    if not src.exists():
        return None
    stamp = int(time.time())
    dest = src.with_name(f"{src.name}.bak.{stamp}")
    shutil.copy2(src, dest)
    logger.info("SQLite backup created: %s", dest)
    return str(dest)


def _latest_backup(db_path: str) -> Optional[Path]:
    parent = Path(db_path).parent
    stem = Path(db_path).name
    candidates = sorted(parent.glob(f"{stem}.bak.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def rollback_db(db_path: str, *, backup_path: str | None = None) -> str:
    """Restore SQLite from a ``.bak.<timestamp>`` file. Returns path restored from."""
    target = Path(db_path)
    src = Path(backup_path) if backup_path else _latest_backup(db_path)
    if src is None or not src.exists():
        raise FileNotFoundError(f"No backup found for {db_path}")
    shutil.copy2(src, target)
    logger.info("Restored %s from %s", target, src)
    return str(src)


def migrate(
    json_path: str | None = None,
    db_path: str | None = None,
    *,
    backup: bool = True,
    rollback_on_failure: bool | None = None,
) -> dict:
    if json_path is None:
        json_path = str(pipeline_json_path())
    if db_path is None:
        db_path = str(pipeline_db_path())
    """Read JSON state file and bulk-insert into SQLite.

    Args:
        json_path: Path to the JSON state file.
        db_path: Path to the target SQLite database.
        backup: When True, copy existing DB before migration.
        rollback_on_failure: Restore backup if migration raises. Defaults from
            ``AIFACTORY_MIGRATE_AUTO_ROLLBACK`` env (off unless ``1``).

    Returns:
        dict with keys: products_migrated, tasks_migrated
    """
    if rollback_on_failure is None:
        rollback_on_failure = os.environ.get("AIFACTORY_MIGRATE_AUTO_ROLLBACK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    backup_path: Optional[str] = None
    if backup:
        backup_path = _backup_db(db_path)

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
            except (TypeError, ValueError) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/migrate.py)", exc_info=_suppressed_exc)
            try:
                latest = max(latest, float(p.get("created_at") or 0))
            except (TypeError, ValueError) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (orchestrator/migrate.py)", exc_info=_suppressed_exc)
        for t in task_dicts:
            for key in ("created_at", "started_at", "completed_at"):
                try:
                    latest = max(latest, float(t.get(key) or 0))
                except (TypeError, ValueError) as _suppressed_exc:
                    log_suppressed(logger, "non-fatal (orchestrator/migrate.py)", exc_info=_suppressed_exc)
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
            "backup": backup_path,
        }
        logger.info(
            f"Migration complete: {product_count} products, {task_count} tasks "
            f"from {json_path} to {db_path}"
        )
        return result
    except Exception:
        logger.exception("Migration failed")
        if rollback_on_failure and backup_path:
            try:
                rollback_db(db_path, backup_path=backup_path)
                logger.info("Auto-rollback restored database from %s", backup_path)
            except Exception as rb_exc:
                logger.error("Auto-rollback failed: %s", rb_exc)
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
        default=str(pipeline_json_path()),
        help="Path to the JSON state file",
    )
    parser.add_argument(
        "--db",
        default=str(pipeline_db_path()),
        help="Path to the target SQLite database",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip pre-migration SQLite backup",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Restore latest .bak backup for --db and exit",
    )
    parser.add_argument(
        "--rollback-from",
        metavar="PATH",
        help="Restore --db from a specific backup file",
    )
    args = parser.parse_args()

    if args.rollback or args.rollback_from:
        try:
            restored = rollback_db(args.db, backup_path=args.rollback_from)
            print(f"Rollback successful from {restored}")
        except Exception as e:
            print(f"Rollback failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    try:
        result = migrate(
            json_path=args.json,
            db_path=args.db,
            backup=not args.no_backup,
        )
        print(f"Migration successful!")
        print(f"  Products migrated: {result['products_migrated']}")
        print(f"  Tasks migrated:    {result['tasks_migrated']}")
        print(f"  Source:            {result['source']}")
        print(f"  Destination:       {result['destination']}")
        if result.get("backup"):
            print(f"  Backup:            {result['backup']}")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
