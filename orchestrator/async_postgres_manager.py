"""Async PostgreSQL access for pipeline worker (mirrors AsyncSQLiteManager)."""

from __future__ import annotations

import json
import os

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .schema import POSTGRES_SCHEMA
from .postgres_manager import _PRODUCT_UPSERT, _TASK_UPSERT
from .sqlite_manager import METADATA_SQL_COLUMNS


class AsyncPostgresManager:
    def __init__(self, database_url: str, workspace_id: str | None = None):
        self.database_url = database_url.strip()
        self.workspace_id = (
            workspace_id or os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"
        )
        self._pool: AsyncConnectionPool | None = None

    async def initialize(self) -> None:
        if self._pool is not None:
            return
        self._pool = AsyncConnectionPool(
            conninfo=self.database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
        )
        async with self._pool.connection() as conn:
            await conn.execute(POSTGRES_SCHEMA)
            await conn.commit()

    async def fetchall(self, query: str, params: tuple = ()) -> list[dict]:
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None
        async with self._pool.connection() as conn:
            cur = await conn.execute(query, params)
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def execute(self, query: str, params: tuple = ()) -> None:
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None
        async with self._pool.connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

    async def get_all_products(self) -> list[dict]:
        rows = await self.fetchall(
            "SELECT * FROM products WHERE workspace_id = %s",
            (self.workspace_id,),
        )
        out = []
        for d in rows:
            meta = {}
            for k in ("spec", "architecture", "tags", "monetization_scheme", "evolution_history"):
                val = d.pop(k, None)
                if val:
                    try:
                        meta[k] = json.loads(val) if isinstance(val, str) else val
                    except Exception:
                        meta[k] = val
            for k in ("category", "error", "current_task_id"):
                if d.get(k) is not None:
                    meta[k] = d.pop(k)
            d["metadata"] = meta
            out.append(d)
        return out

    async def get_all_tasks(self) -> list[dict]:
        rows = await self.fetchall(
            "SELECT * FROM tasks WHERE workspace_id = %s ORDER BY created_at ASC",
            (self.workspace_id,),
        )
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
        from .sqlite_manager import SQLiteManager

        m = product.get("metadata", {}) or {}
        values = SQLiteManager._product_dict_to_sql_values(product)
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None
        async with self._pool.connection() as conn:
            await conn.execute(_PRODUCT_UPSERT, values)
            await conn.commit()

    async def upsert_task(self, task: dict) -> None:
        from .sqlite_manager import SQLiteManager

        values = SQLiteManager._task_dict_to_sql_values(task)
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None
        async with self._pool.connection() as conn:
            await conn.execute(_TASK_UPSERT, values)
            await conn.commit()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
