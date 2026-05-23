"""Copy mesh data from SQLite to PostgreSQL (upsert by primary key)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai_service_mesh.db_backend import PostgresBackend, SQLiteBackend, sqlite_to_pg
from ai_service_mesh.schema import MESH_SCHEMA_SQL, MESH_TABLES


def mask_database_url(url: str) -> str:
    return re.sub(r":([^@/]+)@", ":****@", url, count=1)


def migrate_sqlite_to_postgres(
    database_url: str,
    *,
    sqlite_path: str | Path,
    clear_target: bool = False,
) -> dict[str, Any]:
    """Migrate mesh tables from SQLite file into PostgreSQL.

    Does not change the running API process — set MESH_DATABASE_URL and restart.
    """
    url = (database_url or "").strip()
    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("database_url must be a PostgreSQL connection string")

    spath = Path(sqlite_path)
    if not spath.is_file():
        raise FileNotFoundError(f"SQLite database not found: {spath}")

    src = SQLiteBackend(spath)
    dst = PostgresBackend(url)
    counts: dict[str, int] = {}

    try:
        dst.executescript(MESH_SCHEMA_SQL)
        dst.commit()

        if clear_target:
            for table in MESH_TABLES:
                dst.execute(f"DELETE FROM {table}")
            dst.commit()

        for table in MESH_TABLES:
            src.execute(f"SELECT * FROM {table}")
            rows = src.fetchall()
            if not rows:
                counts[table] = 0
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(cols)
            sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
            pg_sql = sqlite_to_pg(sql, table_name_for_upsert=table, unique_cols=["id"])
            params_list = [tuple(row[c] for c in cols) for row in rows]
            dst.executemany(pg_sql, params_list)
            dst.commit()
            counts[table] = len(rows)

        return {
            "ok": True,
            "tables": counts,
            "source": str(spath),
            "destination": mask_database_url(url),
        }
    finally:
        src.close()
        dst.close()
