"""
PostgreSQL Manager
==================
Pipeline state persistence for PostgreSQL (optional alternative to SQLite).
API mirrors :class:`SQLiteManager` for migration and admin tooling.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .schema import POSTGRES_SCHEMA
from .sqlite_manager import METADATA_SQL_COLUMNS, SQLiteManager

logger = logging.getLogger(__name__)

_PRODUCT_UPSERT = """
INSERT INTO products (
    id, workspace_id, idea, state, created_at, updated_at,
    spec, architecture, tags, category, monetization_scheme,
    evolution_history, error, current_task_id
) VALUES (
    %(id)s, %(workspace_id)s, %(idea)s, %(state)s, %(created_at)s, %(updated_at)s,
    %(spec)s, %(architecture)s, %(tags)s, %(category)s, %(monetization_scheme)s,
    %(evolution_history)s, %(error)s, %(current_task_id)s
)
ON CONFLICT (id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    idea = EXCLUDED.idea,
    state = EXCLUDED.state,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at,
    spec = EXCLUDED.spec,
    architecture = EXCLUDED.architecture,
    tags = EXCLUDED.tags,
    category = EXCLUDED.category,
    monetization_scheme = EXCLUDED.monetization_scheme,
    evolution_history = EXCLUDED.evolution_history,
    error = EXCLUDED.error,
    current_task_id = EXCLUDED.current_task_id
"""

_TASK_UPSERT = """
INSERT INTO tasks (
    id, workspace_id, product_id, agent_type, status, state, assigned_to,
    created_at, started_at, completed_at, input, output, error, priority, retry_count
) VALUES (
    %(id)s, %(workspace_id)s, %(product_id)s, %(agent_type)s, %(status)s, %(state)s,
    %(assigned_to)s, %(created_at)s, %(started_at)s, %(completed_at)s,
    %(input)s, %(output)s, %(error)s, %(priority)s, %(retry_count)s
)
ON CONFLICT (id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    product_id = EXCLUDED.product_id,
    agent_type = EXCLUDED.agent_type,
    status = EXCLUDED.status,
    state = EXCLUDED.state,
    assigned_to = EXCLUDED.assigned_to,
    created_at = EXCLUDED.created_at,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    input = EXCLUDED.input,
    output = EXCLUDED.output,
    error = EXCLUDED.error,
    priority = EXCLUDED.priority,
    retry_count = EXCLUDED.retry_count
"""


class PostgresManager:
    """Sync PostgreSQL access for pipeline products/tasks."""

    def __init__(self, database_url: str, workspace_id: str | None = None):
        self.database_url = database_url.strip()
        self.workspace_id = (
            workspace_id or os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"
        )
        self._pool: ConnectionPool | None = None

    def connect(self) -> None:
        if self._pool is not None:
            return
        self._pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
        )
        with self._pool.connection() as conn:
            conn.execute(POSTGRES_SCHEMA)
            conn.commit()
        logger.debug("Connected to PostgreSQL pipeline store")

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            self.connect()
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool is not available")
        return self._pool

    def get_all_products(self) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM products WHERE workspace_id = %s",
                (self.workspace_id,),
            ).fetchall()
        return [self._row_to_product_dict(r) for r in rows]

    def get_worker_tasks(self) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE workspace_id = %s "
                "AND LOWER(status) IN ('pending', 'running', 'failed') "
                "ORDER BY created_at ASC",
                (self.workspace_id,),
            ).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def get_all_tasks(self) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE workspace_id = %s ORDER BY created_at ASC",
                (self.workspace_id,),
            ).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = %s AND workspace_id = %s",
                (product_id, self.workspace_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_product_dict(row)

    def get_state_distribution(self) -> dict[str, int]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT state, COUNT(*) AS cnt
                FROM products
                WHERE workspace_id = %s
                GROUP BY state
                """,
                (self.workspace_id,),
            ).fetchall()
        out: dict[str, int] = {}
        for row in rows:
            out[str(row["state"] or "UNKNOWN")] = int(row["cnt"] or 0)
        return out

    def get_metrics(self) -> dict[str, Any]:
        """Aggregate pipeline counts (mirrors SQLiteManager.get_metrics)."""
        with self.pool.connection() as conn:
            ws = self.workspace_id
            total_products = conn.execute(
                "SELECT COUNT(*) AS cnt FROM products WHERE workspace_id = %s",
                (ws,),
            ).fetchone()["cnt"]
            active_products = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM products
                WHERE upper(state) NOT IN ('COMPLETED', 'DEPLOYED_PRODUCTION', 'FAILED', 'CANCELLED')
                  AND workspace_id = %s
                """,
                (ws,),
            ).fetchone()["cnt"]
            completed_products = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM products
                WHERE upper(state) IN ('COMPLETED', 'DEPLOYED_PRODUCTION')
                  AND workspace_id = %s
                """,
                (ws,),
            ).fetchone()["cnt"]
            failed_products = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM products
                WHERE upper(state) = 'FAILED' AND workspace_id = %s
                """,
                (ws,),
            ).fetchone()["cnt"]
            pending_tasks = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE upper(status) = 'PENDING' AND workspace_id = %s",
                (ws,),
            ).fetchone()["cnt"]
            running_tasks = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE upper(status) = 'RUNNING' AND workspace_id = %s",
                (ws,),
            ).fetchone()["cnt"]
            failed_tasks = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE upper(status) = 'FAILED' AND workspace_id = %s",
                (ws,),
            ).fetchone()["cnt"]
            timeout_tasks = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM tasks
                WHERE upper(status) IN ('TIMEOUT', 'TIMED_OUT') AND workspace_id = %s
                """,
                (ws,),
            ).fetchone()["cnt"]
        return {
            "total_products": int(total_products or 0),
            "active_products": int(active_products or 0),
            "completed_products": int(completed_products or 0),
            "failed_products": int(failed_products or 0),
            "pending_tasks": int(pending_tasks or 0),
            "running_tasks": int(running_tasks or 0),
            "failed_tasks": int(failed_tasks or 0),
            "timeout_tasks": int(timeout_tasks or 0),
        }

    def count_products(self) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM products WHERE workspace_id = %s",
                (self.workspace_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_tasks(self) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM tasks WHERE workspace_id = %s",
                (self.workspace_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def bulk_insert_products(self, products: list[dict], merge_from_json: bool = False) -> int:
        if not products:
            return 0
        from orchestrator.pipeline_state_sync import sqlite_product_should_keep_over_json

        applied = 0
        with self.pool.connection() as conn:
            existing_map: dict[str, dict] = {}
            if merge_from_json:
                ids = [str(p["id"]) for p in products if p.get("id")]
                if ids:
                    rows = conn.execute(
                        "SELECT id, state, updated_at FROM products "
                        "WHERE workspace_id = %s AND id = ANY(%s)",
                        (self.workspace_id, ids),
                    ).fetchall()
                    existing_map = {str(r["id"]): r for r in rows}

            for product in products:
                values = SQLiteManager._product_dict_to_sql_values(product)
                pid = str(values["id"])
                row = existing_map.get(pid)
                if row is not None and sqlite_product_should_keep_over_json(row, values):
                    continue
                conn.execute(_PRODUCT_UPSERT, values)
                applied += 1
            conn.commit()
        return applied

    def bulk_insert_tasks(self, tasks: list[dict], merge_from_json: bool = False) -> int:
        if not tasks:
            return 0
        applied = 0
        with self.pool.connection() as conn:
            existing_map: dict[str, dict] = {}
            if merge_from_json:
                ids = [str(t["id"]) for t in tasks if t.get("id")]
                if ids:
                    rows = conn.execute(
                        "SELECT id, status, completed_at FROM tasks "
                        "WHERE workspace_id = %s AND id = ANY(%s)",
                        (self.workspace_id, ids),
                    ).fetchall()
                    existing_map = {str(r["id"]): r for r in rows}

            for task in tasks:
                values = SQLiteManager._task_dict_to_sql_values(task)
                tid = str(values["id"])
                row = existing_map.get(tid)
                if row is not None and SQLiteManager._sqlite_task_should_win_over_json(row, values):
                    continue
                conn.execute(_TASK_UPSERT, values)
                applied += 1
            conn.commit()
        return applied

    @staticmethod
    def _row_to_product_dict(row: dict[str, Any]) -> dict[str, Any]:
        d = dict(row)
        metadata: dict[str, Any] = {}
        for meta_key, col in METADATA_SQL_COLUMNS.items():
            val = d.pop(col, None)
            if val is not None:
                if meta_key in ("spec", "architecture", "monetization_scheme"):
                    metadata[meta_key] = json.loads(val) if isinstance(val, str) and val else val
                elif meta_key in ("tags", "evolution_history"):
                    metadata[meta_key] = json.loads(val) if isinstance(val, str) and val else []
                else:
                    metadata[meta_key] = val
        d["metadata"] = metadata
        return d

    @staticmethod
    def _row_to_task_dict(row: dict[str, Any]) -> dict[str, Any]:
        d = dict(row)
        output_raw = d.pop("output", None)
        input_raw = d.pop("input", None)
        d["output_data"] = json.loads(output_raw) if isinstance(output_raw, str) and output_raw else {}
        d["input_data"] = json.loads(input_raw) if isinstance(input_raw, str) and input_raw else {}
        d.pop("assigned_to", None)
        d["timeout_sec"] = 30
        if d.get("retry_count") is None:
            d["retry_count"] = 0
        d["max_retries"] = 3
        return d
