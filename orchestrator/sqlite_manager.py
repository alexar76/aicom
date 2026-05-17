"""
SQLite Manager
==============
Thin wrapper around sqlite3 (stdlib) for pipeline state persistence.
Accepts and returns plain dicts — not ORM objects. Handles serialization
of nested fields (spec, architecture, output_data, etc.) via json.dumps/loads.

Used as an alternative backend for PipelineStateMachine.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any, Optional

from core.paths import pipeline_db_path

from .schema import SQLITE_SCHEMA

logger = logging.getLogger(__name__)

# Keys stored in Product.metadata that have dedicated SQL columns
METADATA_SQL_COLUMNS = {
    "spec": "spec",
    "architecture": "architecture",
    "tags": "tags",
    "category": "category",
    "monetization_scheme": "monetization_scheme",
    "evolution_history": "evolution_history",
    "error": "error",
    "current_task_id": "current_task_id",
}


class SQLiteManager:
    """Manages SQLite connection and CRUD for pipeline state."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(pipeline_db_path())
        self.db_path = db_path
        self.workspace_id = os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self):
        """Create connection, ensure directory exists, apply schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        try:
            self._conn.executescript(SQLITE_SCHEMA)
        except sqlite3.OperationalError as e:
            # Legacy DBs may miss workspace_id, while schema script already tries
            # to create indexes on workspace_id. Backfill columns first, then retry.
            if "workspace_id" not in str(e):
                raise
            logger.warning("Schema apply hit workspace_id issue, running compatibility migration: %s", e)
            try:
                self._conn.execute("ALTER TABLE products ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            except sqlite3.OperationalError:
                pass
            self._conn.executescript(SQLITE_SCHEMA)
        # Migrate existing tables: add retry_count column if missing
        try:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0")
            logger.info("Added retry_count column to existing tasks table (schema migration)")
        except sqlite3.OperationalError:
            # Column already exists — this is fine
            pass
        try:
            self._conn.execute("ALTER TABLE products ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN input TEXT")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
        logger.debug("Connected to SQLite at %s", self.db_path)

    def close(self):
        """Close the connection if open."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy-accessor that auto-connects on first use."""
        if self._conn is None:
            self.connect()
        return self._conn

    # ------------------------------------------------------------------
    # Helpers — dict <-> Row conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_product_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite Row to a product dict (as would be returned
        by Product.to_dict(), minus the nested tasks list)."""
        d = dict(row)
        # Reconstruct metadata from SQL columns
        metadata: dict[str, Any] = {}
        for meta_key, col in METADATA_SQL_COLUMNS.items():
            val = d.pop(col, None)
            if val is not None:
                # Try to parse JSON strings back to Python objects
                if meta_key in ("spec", "architecture", "monetization_scheme"):
                    metadata[meta_key] = json.loads(val) if val else None
                elif meta_key in ("tags", "evolution_history"):
                    metadata[meta_key] = json.loads(val) if val else []
                else:
                    metadata[meta_key] = val
        d["metadata"] = metadata
        return d

    @staticmethod
    def _row_to_task_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite Row to a task dict (as would be returned
        by Task.to_dict())."""
        d = dict(row)
        # Reconstruct output_data from JSON string
        output_raw = d.pop("output", None)
        input_raw = d.pop("input", None)
        d["output_data"] = json.loads(output_raw) if output_raw else {}
        d["input_data"] = json.loads(input_raw) if input_raw else {}
        # assigned_to is not in Task dataclass; keep it if present but
        # the Task dataclass won't use it.
        d.pop("assigned_to", None)
        # Add fields that don't have dedicated SQL columns
        d["timeout_sec"] = 30
        # retry_count is now read from the SQL column (defaults to 0)
        if "retry_count" not in d or d["retry_count"] is None:
            d["retry_count"] = 0
        try:
            from core.pipeline_retry_limits import task_max_retries

            d["max_retries"] = task_max_retries()
        except Exception:
            d["max_retries"] = 7
        # state may be None if column didn't exist before migration
        if d.get("state") is None:
            # Infer state from agent_type as fallback
            from .state_machine import PipelineState
            agent_map = {
                "analyst": "market_researched",
                "pm": "spec_written",
                "marketing": "market_content_ready",
                "methodologist": "methodology_reviewed",
                "architect": "arch_designed",
                "developer": "code_committed",
                "qa": "qa_testing",
                "security": "security_scanned",
                "devops": "sales_active",
                "sales": "sandbox_running",
            }
            fallback = agent_map.get(d.get("agent_type", ""), "idea_received")
            d["state"] = fallback
        return d

    @staticmethod
    def _product_dict_to_sql_values(product: dict) -> dict[str, Any]:
        """Extract SQL column values from a product dict (from Product.to_dict())."""
        metadata = product.get("metadata", {}) or {}
        values: dict[str, Any] = {
            "id": product["id"],
            "workspace_id": product.get("workspace_id") or os.environ.get("AIFACTORY_WORKSPACE_ID", "default"),
            "idea": product["idea"],
            "state": product.get("state", "IDEA"),
            "created_at": product.get("created_at", time.time()),
            "updated_at": product.get("updated_at", time.time()),
            "spec": json.dumps(metadata.get("spec")) if metadata.get("spec") is not None else None,
            "architecture": json.dumps(metadata.get("architecture")) if metadata.get("architecture") is not None else None,
            "tags": json.dumps(metadata.get("tags")) if metadata.get("tags") is not None else None,
            "category": metadata.get("category"),
            "monetization_scheme": json.dumps(metadata.get("monetization_scheme")) if metadata.get("monetization_scheme") is not None else None,
            "evolution_history": json.dumps(metadata.get("evolution_history")) if metadata.get("evolution_history") is not None else None,
            "error": metadata.get("error"),
            "current_task_id": metadata.get("current_task_id"),
        }
        return values

    @staticmethod
    def _task_dict_to_sql_values(task: dict) -> dict[str, Any]:
        """Extract SQL column values from a task dict (from Task.to_dict())."""
        output_data = task.get("output_data", {}) or {}
        input_data = task.get("input_data", {}) or {}
        return {
            "id": task["id"],
            "workspace_id": task.get("workspace_id") or os.environ.get("AIFACTORY_WORKSPACE_ID", "default"),
            "product_id": task["product_id"],
            "agent_type": task.get("agent_type", ""),
            "status": task.get("status", "PENDING"),
            "state": task.get("state"),  # PipelineState.value string, e.g. "idea_received"
            "assigned_to": task.get("assigned_to"),
            "created_at": task.get("created_at", time.time()),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "input": json.dumps(input_data) if input_data else None,
            "output": json.dumps(output_data) if output_data else None,
            "error": task.get("error"),
            "priority": task.get("priority", 0),
            "retry_count": task.get("retry_count", 0),
        }

    # ------------------------------------------------------------------
    # Product CRUD
    # ------------------------------------------------------------------

    def upsert_product(self, product: dict) -> None:
        """Insert or replace a product in the database.

        Args:
            product: A dict matching the Product.to_dict() structure.
        """
        values = self._product_dict_to_sql_values(product)
        self.conn.execute(
            """INSERT OR REPLACE INTO products
               (id, workspace_id, idea, state, created_at, updated_at,
                spec, architecture, tags, category,
                monetization_scheme, evolution_history,
                error, current_task_id)
               VALUES
               (:id, :workspace_id, :idea, :state, :created_at, :updated_at,
                :spec, :architecture, :tags, :category,
                :monetization_scheme, :evolution_history,
                :error, :current_task_id)""",
            values,
        )
        self.conn.commit()

    def get_product(self, product_id: str) -> Optional[dict]:
        """Retrieve a single product by ID.

        Returns:
            A product dict (as from Product.to_dict(), without the tasks list),
            or None if not found.
        """
        row = self.conn.execute(
            "SELECT * FROM products WHERE id = ? AND workspace_id = ?", (product_id, self.workspace_id)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_product_dict(row)

    def get_all_products(self) -> list[dict]:
        """Retrieve all products."""
        rows = self.conn.execute("SELECT * FROM products WHERE workspace_id = ?", (self.workspace_id,)).fetchall()
        return [self._row_to_product_dict(r) for r in rows]

    def get_catalog_summary_counts(self) -> dict[str, int]:
        """Single-query totals for admin pipeline catalog (full workspace, not a page)."""
        row = self.conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              COALESCE(SUM(CASE
                WHEN upper(trim(state)) IN ('COMPLETED', 'DEPLOYED_PRODUCTION') THEN 1 ELSE 0
              END), 0) AS shipped,
              COALESCE(SUM(CASE
                WHEN upper(trim(state)) = 'FAILED' THEN 1 ELSE 0
              END), 0) AS failed
            FROM products
            WHERE workspace_id = ?
            """,
            (self.workspace_id,),
        ).fetchone()
        if row is None:
            return {"total": 0, "shipped": 0, "failed": 0}
        return {
            "total": int(row["total"] or 0),
            "shipped": int(row["shipped"] or 0),
            "failed": int(row["failed"] or 0),
        }

    def list_products_catalog_page(self, sort: str, offset: int, limit: int) -> list[dict]:
        """List one catalog page with server-side sort (matches admin pipeline monitor)."""
        off = max(0, int(offset))
        lim = max(1, min(int(limit), 5000))
        ws = self.workspace_id
        if sort == "shipped_first":
            rows = self.conn.execute(
                """
                SELECT * FROM products
                WHERE workspace_id = ?
                ORDER BY
                  CASE WHEN upper(trim(state)) IN ('COMPLETED', 'DEPLOYED_PRODUCTION') THEN 0 ELSE 1 END ASC,
                  created_at DESC
                LIMIT ? OFFSET ?
                """,
                (ws, lim, off),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM products
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (ws, lim, off),
            ).fetchall()
        return [self._row_to_product_dict(r) for r in rows]

    def get_tasks_for_product_ids(
        self,
        product_ids: list[str],
        *,
        omit_blob_columns: bool = False,
    ) -> list[dict]:
        """Tasks for the given products only (avoids loading the full task table for catalog pages).

        When ``omit_blob_columns`` is true, ``input`` / ``output`` JSON blobs are not read from SQLite
        (Pipeline Monitor ``light=true`` — large agent payloads are not needed for status columns).
        """
        if not product_ids:
            return []
        placeholders = ",".join("?" * len(product_ids))
        cols = (
            "id, workspace_id, product_id, agent_type, status, state, assigned_to, "
            "created_at, started_at, completed_at, error, priority, retry_count"
            if omit_blob_columns
            else "*"
        )
        q = f"""
            SELECT {cols} FROM tasks
            WHERE workspace_id = ? AND product_id IN ({placeholders})
            ORDER BY product_id ASC, created_at ASC
        """
        rows = self.conn.execute(q, (self.workspace_id, *product_ids)).fetchall()
        if omit_blob_columns:
            return [self._row_to_task_dict_catalog_light(r) for r in rows]
        return [self._row_to_task_dict(r) for r in rows]

    @staticmethod
    def _row_to_task_dict_catalog_light(row: sqlite3.Row) -> dict[str, Any]:
        """Task row without ``input``/``output`` blobs (matches keys expected by admin pipeline UI)."""
        d: dict[str, Any] = {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "product_id": row["product_id"],
            "agent_type": row["agent_type"],
            "status": row["status"],
            "state": row["state"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error": row["error"],
            "priority": row["priority"] if row["priority"] is not None else 0,
            "retry_count": row["retry_count"] if row["retry_count"] is not None else 0,
            "input_data": {},
            "output_data": {},
            "timeout_sec": 30,
            "max_retries": 3,
        }
        if d.get("state") is None:
            agent_map = {
                "analyst": "market_researched",
                "pm": "spec_written",
                "marketing": "market_content_ready",
                "methodologist": "methodology_reviewed",
                "architect": "arch_designed",
                "developer": "code_committed",
                "qa": "qa_testing",
                "security": "security_scanned",
                "devops": "sales_active",
                "sales": "sandbox_running",
            }
            d["state"] = agent_map.get(str(d.get("agent_type") or ""), "idea_received")
        return d

    def get_task_counts_for_product_ids(self, product_ids: list[str]) -> dict[str, dict[str, int]]:
        """Aggregate task status counts per product (no task row payloads)."""
        if not product_ids:
            return {}
        placeholders = ",".join("?" * len(product_ids))
        q = f"""
            SELECT
              product_id,
              COUNT(*) AS total,
              SUM(CASE WHEN lower(trim(status)) = 'completed' THEN 1 ELSE 0 END) AS completed,
              SUM(CASE WHEN lower(trim(status)) = 'failed' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN lower(trim(status)) = 'running' THEN 1 ELSE 0 END) AS running,
              SUM(CASE WHEN lower(trim(status)) = 'pending' THEN 1 ELSE 0 END) AS pending
            FROM tasks
            WHERE workspace_id = ? AND product_id IN ({placeholders})
            GROUP BY product_id
        """
        rows = self.conn.execute(q, (self.workspace_id, *product_ids)).fetchall()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            pid = str(r["product_id"])
            out[pid] = {
                "total": int(r["total"] or 0),
                "completed": int(r["completed"] or 0),
                "failed": int(r["failed"] or 0),
                "running": int(r["running"] or 0),
                "pending": int(r["pending"] or 0),
            }
        return out

    def get_latest_stage_tasks_for_product_ids(
        self,
        product_ids: list[str],
        *,
        agent_types: tuple[str, ...],
    ) -> list[dict]:
        """Latest task per (product_id, agent_type) for pipeline stage UI — no input/output blobs."""
        if not product_ids or not agent_types:
            return []
        pid_ph = ",".join("?" * len(product_ids))
        at_ph = ",".join("?" * len(agent_types))
        q = f"""
            SELECT
              t.id, t.workspace_id, t.product_id, t.agent_type, t.status, t.state, t.assigned_to,
              t.created_at, t.started_at, t.completed_at, t.error, t.priority, t.retry_count
            FROM tasks t
            INNER JOIN (
              SELECT product_id, agent_type, MAX(created_at) AS max_created
              FROM tasks
              WHERE workspace_id = ? AND product_id IN ({pid_ph})
                AND agent_type IN ({at_ph})
              GROUP BY product_id, agent_type
            ) latest
              ON t.workspace_id = ?
              AND t.product_id = latest.product_id
              AND t.agent_type = latest.agent_type
              AND t.created_at = latest.max_created
            ORDER BY t.product_id ASC, t.created_at ASC
        """
        params: tuple[Any, ...] = (self.workspace_id, *product_ids, *agent_types, self.workspace_id)
        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_task_dict_catalog_light(r) for r in rows]

    def delete_product(self, product_id: str) -> None:
        """Delete a product and its associated tasks."""
        self.conn.execute("DELETE FROM tasks WHERE product_id = ? AND workspace_id = ?", (product_id, self.workspace_id))
        self.conn.execute("DELETE FROM products WHERE id = ? AND workspace_id = ?", (product_id, self.workspace_id))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def upsert_task(self, task: dict) -> None:
        """Insert or replace a task in the database.

        Args:
            task: A dict matching the Task.to_dict() structure.
        """
        values = self._task_dict_to_sql_values(task)
        self.conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, workspace_id, product_id, agent_type, status, state, assigned_to,
                created_at, started_at, completed_at, input, output,
                error, priority, retry_count)
               VALUES
               (:id, :workspace_id, :product_id, :agent_type, :status, :state, :assigned_to,
                :created_at, :started_at, :completed_at, :input, :output,
                :error, :priority, :retry_count)""",
            values,
        )
        self.conn.commit()

    def get_task(self, task_id: str) -> Optional[dict]:
        """Retrieve a single task by ID."""
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND workspace_id = ?", (task_id, self.workspace_id)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_task_dict(row)

    def get_tasks_by_product(self, product_id: str) -> list[dict]:
        """Retrieve all tasks for a given product."""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE product_id = ? AND workspace_id = ? ORDER BY created_at ASC",
            (product_id, self.workspace_id),
        ).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def get_worker_tasks(self) -> list[dict]:
        """Active queue rows only (pending/running/failed) for the pipeline worker hot path."""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE workspace_id = ? AND LOWER(status) IN ('pending', 'running', 'failed') "
            "ORDER BY created_at ASC",
            (self.workspace_id,),
        ).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def get_all_tasks(self) -> list[dict]:
        """Retrieve all tasks."""
        rows = self.conn.execute("SELECT * FROM tasks WHERE workspace_id = ? ORDER BY created_at ASC", (self.workspace_id,)).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def get_pending_tasks(self) -> list[dict]:
        """Retrieve all tasks with status 'PENDING'."""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE status = 'PENDING' AND workspace_id = ? ORDER BY priority ASC, created_at ASC",
            (self.workspace_id,),
        ).fetchall()
        return [self._row_to_task_dict(r) for r in rows]

    def delete_task(self, task_id: str) -> None:
        """Delete a single task by ID."""
        self.conn.execute("DELETE FROM tasks WHERE id = ? AND workspace_id = ?", (task_id, self.workspace_id))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_state_distribution(self) -> dict[str, int]:
        """Product counts by state (single GROUP BY — no full table load)."""
        rows = self.conn.execute(
            """
            SELECT state, COUNT(*) AS cnt
            FROM products
            WHERE workspace_id = ?
            GROUP BY state
            """,
            (self.workspace_id,),
        ).fetchall()
        out: dict[str, int] = {}
        for row in rows:
            key = str(row["state"] or "UNKNOWN")
            out[key] = int(row["cnt"] or 0)
        return out

    def get_metrics(self) -> dict[str, Any]:
        """Return pipeline metrics computed from SQLite data."""
        total_products = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM products"
            " WHERE workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        active_products = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE upper(state) NOT IN "
            "('COMPLETED', 'DEPLOYED_PRODUCTION', 'FAILED', 'CANCELLED')"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        completed_products = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE upper(state) IN ('COMPLETED', 'DEPLOYED_PRODUCTION')"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        failed_products = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE upper(state) = 'FAILED'"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        total_tasks = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks"
            " WHERE workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        pending_tasks = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'PENDING'"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        running_tasks = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'RUNNING'"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        failed_tasks = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'FAILED'"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        timeout_tasks = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE status = 'TIMEOUT'"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()["cnt"]

        # Average completion time for completed products
        avg_row = self.conn.execute(
            "SELECT AVG(updated_at - created_at) as avg_time FROM products WHERE upper(state) IN "
            "('COMPLETED', 'DEPLOYED_PRODUCTION')"
            " AND workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()
        avg_seconds = avg_row["avg_time"] if avg_row and avg_row["avg_time"] else 0
        avg_hours = avg_seconds / 3600 if avg_seconds else 0

        return {
            "total_products": total_products,
            "active_products": active_products,
            "completed_products": completed_products,
            "failed_products": failed_products,
            "avg_completion_time_hours": round(avg_hours, 4),
            "pending_tasks": pending_tasks,
            "running_tasks": running_tasks,
            "failed_tasks": failed_tasks,
            "timeout_tasks": timeout_tasks,
            "total_tasks": total_tasks,
        }

    def clear_all(self) -> None:
        """Delete all rows from both tables (for testing)."""
        self.conn.execute("DELETE FROM tasks WHERE workspace_id = ?", (self.workspace_id,))
        self.conn.execute("DELETE FROM products WHERE workspace_id = ?", (self.workspace_id,))
        self.conn.commit()

    def _products_existing_snapshot(
        self, cursor: sqlite3.Cursor, product_ids: list[str]
    ) -> dict[str, sqlite3.Row]:
        out: dict[str, sqlite3.Row] = {}
        if not product_ids:
            return out
        chunk_size = 400
        wid = self.workspace_id
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            rows = cursor.execute(
                f"SELECT id, state, updated_at FROM products "
                f"WHERE workspace_id = ? AND id IN ({placeholders})",
                (wid, *chunk),
            ).fetchall()
            for r in rows:
                out[str(r["id"])] = r
        return out

    def bulk_insert_products(self, products: list[dict], merge_from_json: bool = False) -> int:
        """Insert multiple products in a transaction.

        Args:
            products: List of product dicts (from Product.to_dict()).
            merge_from_json: When True, do not let stale pipeline.json downgrade SQLite.

        Returns:
            Number of rows written.
        """
        from orchestrator.pipeline_state_sync import sqlite_product_should_keep_over_json

        cursor = self.conn.cursor()
        existing_map: dict[str, sqlite3.Row] = {}
        if merge_from_json and products:
            ids = [str(p["id"]) for p in products if p.get("id")]
            existing_map = self._products_existing_snapshot(cursor, ids)

        applied = 0
        for product in products:
            values = self._product_dict_to_sql_values(product)
            pid = str(values["id"])
            row = existing_map.get(pid)
            if row is not None and sqlite_product_should_keep_over_json(row, values):
                continue
            cursor.execute(
                """INSERT OR REPLACE INTO products
                   (id, workspace_id, idea, state, created_at, updated_at,
                    spec, architecture, tags, category,
                    monetization_scheme, evolution_history,
                    error, current_task_id)
                   VALUES
                   (:id, :workspace_id, :idea, :state, :created_at, :updated_at,
                    :spec, :architecture, :tags, :category,
                    :monetization_scheme, :evolution_history,
                    :error, :current_task_id)""",
                values,
            )
            applied += 1
        self.conn.commit()
        return applied

    _TASK_TERMINAL_STATUSES = frozenset(
        {"completed", "failed", "timeout", "cancelled", "blocked"}
    )

    @classmethod
    def _sqlite_task_should_win_over_json(
        cls, existing: sqlite3.Row, incoming: dict[str, Any]
    ) -> bool:
        """True → skip upsert; keep SQLite row (worker-fresher than stale JSON)."""
        ex_st = (existing["status"] or "").strip().lower()
        js_st = (incoming["status"] or "").strip().lower()
        ex_term = ex_st in cls._TASK_TERMINAL_STATUSES
        js_term = js_st in cls._TASK_TERMINAL_STATUSES
        if ex_term and not js_term:
            return True
        ex_ca = existing["completed_at"]
        js_ca = incoming.get("completed_at")
        if ex_ca is not None and js_ca is None:
            return True
        if ex_term and js_term:
            try:
                ex_t = float(ex_ca or 0)
                js_t = float(js_ca or 0)
            except (TypeError, ValueError):
                return True
            return ex_t >= js_t
        return False

    def _tasks_existing_snapshot(
        self, cursor: sqlite3.Cursor, task_ids: list[str]
    ) -> dict[str, sqlite3.Row]:
        """Fetch minimal rows for JSON→SQLite merge (batched IN queries)."""
        out: dict[str, sqlite3.Row] = {}
        if not task_ids:
            return out
        chunk_size = 400
        wid = self.workspace_id
        for i in range(0, len(task_ids), chunk_size):
            chunk = task_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            rows = cursor.execute(
                f"SELECT id, status, completed_at FROM tasks "
                f"WHERE workspace_id = ? AND id IN ({placeholders})",
                (wid, *chunk),
            ).fetchall()
            for r in rows:
                out[str(r["id"])] = r
        return out

    def bulk_insert_tasks(self, tasks: list[dict], merge_from_json: bool = False) -> int:
        """Insert multiple tasks in a transaction.

        Args:
            tasks: List of task dicts (from Task.to_dict()).
            merge_from_json: When True (JSON→SQLite sync), do not overwrite SQLite rows
                that are clearly fresher than stale pipeline.json snapshots.

        Returns:
            Number of rows written (INSERT OR REPLACE). Skipped merges are not counted.
        """
        cursor = self.conn.cursor()
        existing_map: dict[str, sqlite3.Row] = {}
        if merge_from_json and tasks:
            ids = [str(t["id"]) for t in tasks if t.get("id")]
            existing_map = self._tasks_existing_snapshot(cursor, ids)

        applied = 0
        for task in tasks:
            values = self._task_dict_to_sql_values(task)
            tid = str(values["id"])
            row = existing_map.get(tid)
            if row is not None and self._sqlite_task_should_win_over_json(row, values):
                continue
            cursor.execute(
                """INSERT OR REPLACE INTO tasks
                   (id, workspace_id, product_id, agent_type, status, state, assigned_to,
                    created_at, started_at, completed_at, input, output,
                    error, priority, retry_count)
                   VALUES
                   (:id, :workspace_id, :product_id, :agent_type, :status, :state, :assigned_to,
                    :created_at, :started_at, :completed_at, :input, :output,
                    :error, :priority, :retry_count)""",
                values,
            )
            applied += 1
        self.conn.commit()
        return applied
