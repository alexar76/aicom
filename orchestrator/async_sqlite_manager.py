from __future__ import annotations

import json
import os
import aiosqlite
import sqlite3

from .schema import SQLITE_SCHEMA


class AsyncSQLiteManager:
    """
    Lightweight async access to SQLite for coroutine contexts.
    Used to avoid blocking event loop in async orchestration paths.
    """

    def __init__(self, db_path: str, workspace_id: str | None = None):
        self.db_path = db_path
        self.workspace_id = (
            workspace_id
            or os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip()
            or "default"
        )
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        try:
            await self._conn.executescript(SQLITE_SCHEMA)
        except sqlite3.OperationalError as e:
            # Legacy DBs may miss workspace_id while schema creates indexes for it.
            if "workspace_id" not in str(e):
                raise
            try:
                await self._conn.execute("ALTER TABLE products ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass
            try:
                await self._conn.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
            except Exception:
                pass
            await self._conn.executescript(SQLITE_SCHEMA)
        try:
            await self._conn.execute("ALTER TABLE products ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE tasks ADD COLUMN input TEXT")
        except Exception:
            pass
        await self._conn.commit()

    async def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        async with self._conn.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def execute(self, query: str, params: tuple = ()) -> None:
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        await self._conn.execute(query, params)
        await self._conn.commit()

    async def get_all_products(self) -> list[dict]:
        rows = await self.fetchall("SELECT * FROM products WHERE workspace_id = ?", (self.workspace_id,))
        out = []
        for d in rows:
            meta = {}
            for k in ("spec", "architecture", "tags", "monetization_scheme", "evolution_history"):
                val = d.pop(k, None)
                if val:
                    try:
                        meta[k] = json.loads(val)
                    except Exception:
                        meta[k] = val
            for k in ("category", "error", "current_task_id"):
                if d.get(k) is not None:
                    meta[k] = d.pop(k)
            d["metadata"] = meta
            out.append(d)
        return out

    async def get_worker_tasks(self) -> list[dict]:
        """Active queue rows only — excludes completed/cancelled history (worker hot path)."""
        rows = await self.fetchall(
            "SELECT * FROM tasks WHERE workspace_id = ? AND LOWER(status) IN ('pending', 'running', 'failed') "
            "ORDER BY created_at ASC",
            (self.workspace_id,),
        )
        return self._rows_to_task_dicts(rows)

    async def get_all_tasks(self) -> list[dict]:
        rows = await self.fetchall(
            "SELECT * FROM tasks WHERE workspace_id = ? ORDER BY created_at ASC",
            (self.workspace_id,),
        )
        return self._rows_to_task_dicts(rows)

    def _rows_to_task_dicts(self, rows: list[dict]) -> list[dict]:
        out = []
        for d in rows:
            input_raw = d.pop("input", None)
            output_raw = d.pop("output", None)
            try:
                output_data = json.loads(output_raw) if output_raw else {}
            except Exception:
                output_data = {}
            try:
                input_data = json.loads(input_raw) if input_raw else {}
            except Exception:
                input_data = {}
            d["output_data"] = output_data
            d["input_data"] = input_data
            d["timeout_sec"] = 30
            d["max_retries"] = 3
            d.pop("assigned_to", None)
            out.append(d)
        return out

    async def upsert_product(self, product: dict) -> None:
        m = product.get("metadata", {}) or {}
        await self.execute(
            """INSERT OR REPLACE INTO products
               (id, workspace_id, idea, state, created_at, updated_at, spec, architecture, tags, category, monetization_scheme, evolution_history, error, current_task_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product["id"],
                product.get("workspace_id") or self.workspace_id,
                product.get("idea", ""),
                product.get("state", "idea_received"),
                product.get("created_at"),
                product.get("updated_at"),
                json.dumps(m.get("spec")) if m.get("spec") is not None else None,
                json.dumps(m.get("architecture")) if m.get("architecture") is not None else None,
                json.dumps(m.get("tags")) if m.get("tags") is not None else None,
                m.get("category"),
                json.dumps(m.get("monetization_scheme")) if m.get("monetization_scheme") is not None else None,
                json.dumps(m.get("evolution_history")) if m.get("evolution_history") is not None else None,
                m.get("error"),
                m.get("current_task_id"),
            ),
        )

    async def upsert_task(self, task: dict) -> None:
        await self.execute(
            """INSERT OR REPLACE INTO tasks
               (id, workspace_id, product_id, agent_type, status, state, assigned_to, created_at, started_at, completed_at, input, output, error, priority, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task["id"],
                task.get("workspace_id") or self.workspace_id,
                task.get("product_id"),
                task.get("agent_type"),
                task.get("status"),
                task.get("state"),
                task.get("assigned_to"),
                task.get("created_at"),
                task.get("started_at"),
                task.get("completed_at"),
                json.dumps(task.get("input_data") or {}),
                json.dumps(task.get("output_data") or {}),
                task.get("error"),
                task.get("priority", 0),
                task.get("retry_count", 0),
            ),
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
