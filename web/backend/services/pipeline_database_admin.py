"""Admin helpers: pipeline DB status, Postgres connection test, SQLite→Postgres migration."""

from __future__ import annotations

import logging
import os
from typing import Any

from core.paths import pipeline_db_path, pipeline_json_path
from core.pipeline_database import (
    apply_pipeline_db_config_from_app_config,
    mask_database_url,
    pipeline_database_url,
    pipeline_db_backend,
)

logger = logging.getLogger(__name__)


def pipeline_db_status(config: Any) -> dict[str, Any]:
    apply_pipeline_db_config_from_app_config(config)
    backend = pipeline_db_backend()
    sqlite_path = pipeline_db_path()
    url = pipeline_database_url() or str(config.get("general.pipeline_database_url", "") or "")
    status: dict[str, Any] = {
        "configured_backend": str(config.get("general.pipeline_db_backend", "sqlite") or "sqlite"),
        "effective_backend": backend,
        "sqlite_path": str(sqlite_path),
        "sqlite_exists": sqlite_path.is_file(),
        "pipeline_json_exists": pipeline_json_path().is_file(),
        "database_url_configured": bool(url),
        "database_url_masked": mask_database_url(url),
        "requires_restart": False,
    }
    if backend == "sqlite" and sqlite_path.is_file():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(sqlite_path))
            sm.connect()
            status["sqlite_products"] = sm.conn.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]
            status["sqlite_tasks"] = sm.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            sm.close()
        except Exception as exc:
            status["sqlite_error"] = str(exc)
    if backend == "postgres" and url:
        try:
            from orchestrator.postgres_manager import PostgresManager

            pg = PostgresManager(url)
            pg.connect()
            status["postgres_products"] = pg.count_products()
            status["postgres_tasks"] = pg.count_tasks()
            pg.close()
        except Exception as exc:
            status["postgres_error"] = str(exc)
    return status


def test_postgres_connection(database_url: str) -> dict[str, Any]:
    url = (database_url or "").strip()
    if not url:
        url = pipeline_database_url()
    if not url:
        return {"ok": False, "detail": "No database URL provided."}
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=8) as conn:
            row = conn.execute("SELECT version()").fetchone()
        version = row[0] if row else "unknown"
        return {"ok": True, "detail": f"Connected. {version[:120]}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def migrate_sqlite_to_postgres(
    database_url: str,
    *,
    sqlite_path: str | None = None,
    clear_target: bool = False,
) -> dict[str, Any]:
    """
    Copy all products/tasks from SQLite into PostgreSQL (upsert by id).
    Does not switch runtime backend — restart container after setting postgres in Settings.
    """
    url = (database_url or "").strip()
    if not url:
        raise ValueError("database_url is required")

    spath = sqlite_path or str(pipeline_db_path())
    if not os.path.isfile(spath):
        raise FileNotFoundError(f"SQLite database not found: {spath}")

    from orchestrator.postgres_manager import PostgresManager
    from orchestrator.sqlite_manager import SQLiteManager

    sqlite = SQLiteManager(spath)
    pg = PostgresManager(url)
    sqlite.connect()
    pg.connect()
    try:
        if clear_target:
            wid = pg.workspace_id
            with pg.pool.connection() as conn:
                conn.execute("DELETE FROM tasks WHERE workspace_id = %s", (wid,))
                conn.execute("DELETE FROM products WHERE workspace_id = %s", (wid,))
                conn.commit()

        products = sqlite.get_all_products()
        tasks = sqlite.get_all_tasks()
        pc = pg.bulk_insert_products(products)
        tc = pg.bulk_insert_tasks(tasks, merge_from_json=False)
        return {
            "ok": True,
            "products_migrated": pc,
            "tasks_migrated": tc,
            "source": spath,
            "destination": mask_database_url(url),
        }
    finally:
        sqlite.close()
        pg.close()
