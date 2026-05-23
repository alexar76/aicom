#!/usr/bin/env python3
"""CLI: migrate AI Service Mesh data from SQLite to PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ai_service_mesh.migrate import migrate_sqlite_to_postgres  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate mesh.db (SQLite) → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("MESH_SQLITE_PATH", str(ROOT / "backend" / ".mesh_data" / "mesh.db")),
        help="Path to mesh.db",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("MESH_DATABASE_URL", os.environ.get("DATABASE_URL", "")),
        help="PostgreSQL URL (postgresql://...)",
    )
    parser.add_argument(
        "--clear-target",
        action="store_true",
        help="DELETE existing rows in target tables before copy",
    )
    args = parser.parse_args()
    if not args.database_url:
        print("Set --database-url or MESH_DATABASE_URL / DATABASE_URL", file=sys.stderr)
        return 1
    result = migrate_sqlite_to_postgres(
        args.database_url,
        sqlite_path=args.sqlite,
        clear_target=args.clear_target,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
