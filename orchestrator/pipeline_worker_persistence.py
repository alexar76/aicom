"""
Pipeline state load/save for the background worker (extracted from pipeline_worker.py).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from core.pipeline_state_writer import (
    read_pipeline_state_from_sql,
    should_recover_json_from_sqlite,
)
from core.paths import pipeline_json_path

logger = logging.getLogger(__name__)


def _sql_dirty_save_enabled() -> bool:
    return os.environ.get("AIFACTORY_PIPELINE_SQL_DIRTY_SAVE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class PipelineStatePersistence:
    """JSON file and/or async SQL store for pipeline products + task queue."""

    def __init__(self, *, state_file: Path | None = None, use_sql_store: bool = False) -> None:
        self.state_file = state_file or pipeline_json_path()
        self.use_sql_store = use_sql_store
        self._async_store: Any | None = None

    async def close(self) -> None:
        if self._async_store is not None:
            try:
                await self._async_store.close()
            except Exception:
                logger.debug("async pipeline store close failed", exc_info=True)
            self._async_store = None

    def load_json_with_recovery(self) -> dict | None:
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cannot read pipeline state: %s", e)

        try:
            ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            bad_backup = self.state_file.with_suffix(f".json.corrupt-{ts}.bak")
            try:
                bad_backup.write_text(
                    self.state_file.read_text(encoding="utf-8", errors="replace"),
                    encoding="utf-8",
                )
                logger.warning("Corrupted pipeline state backed up to %s", bad_backup)
            except OSError as copy_exc:
                logger.warning("Failed to backup corrupted state file: %s", copy_exc)

            if not should_recover_json_from_sqlite(self.state_file):
                logger.warning(
                    "Corrupt pipeline.json; SQLite recovery skipped "
                    "(set AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE=1 or ensure pipeline.db is newer)"
                )
                return None

            rebuilt = read_pipeline_state_from_sql()
            if not rebuilt:
                return None
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(rebuilt, f, indent=2)
            logger.warning(
                "Recovered pipeline.json from SQL store: products=%s tasks=%s",
                len(rebuilt.get("products", {})),
                len(rebuilt.get("task_queue", [])),
            )
            return rebuilt
        except Exception:
            logger.exception("Pipeline state auto-recovery failed")
            return None

    async def load_async(self) -> dict | None:
        if not self.use_sql_store:
            return self.load_json_with_recovery()
        try:
            from core.pipeline_database import create_async_pipeline_store

            if self._async_store is None:
                self._async_store = create_async_pipeline_store()
                await self._async_store.initialize()

            products = await self._async_store.get_all_products()
            get_tasks = getattr(self._async_store, "get_worker_tasks", None) or self._async_store.get_all_tasks
            tasks = await get_tasks()
            products_map = {p["id"]: p for p in products if isinstance(p.get("id"), str)}
            current_task_id: Optional[str] = None
            for t in tasks:
                st = str(t.get("status") or "").upper()
                if st == "RUNNING":
                    current_task_id = t.get("id")
                    break
                if st == "PENDING" and current_task_id is None:
                    current_task_id = t.get("id")
            return {"products": products_map, "task_queue": tasks, "current_task_id": current_task_id}
        except Exception:
            logger.exception("Failed to load state from SQL async path")
            return None

    async def save_async(self, state: dict) -> bool:
        if not self.use_sql_store:
            try:
                compact = os.environ.get("AIFACTORY_PIPELINE_JSON_COMPACT", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                )
                with open(self.state_file, "w", encoding="utf-8") as f:
                    if compact:
                        json.dump(state, f, separators=(",", ":"))
                    else:
                        json.dump(state, f, indent=2)
                return True
            except OSError:
                logger.exception("Cannot save pipeline state file")
                return False
        try:
            from core.pipeline_database import create_async_pipeline_store

            if self._async_store is None:
                self._async_store = create_async_pipeline_store()
                await self._async_store.initialize()

            products_map: dict[str, dict] = state.get("products") or {}
            task_queue: list[dict] = state.get("task_queue") or []

            dirty_p = set(state.pop("_dirty_product_ids", None) or [])
            dirty_t = set(state.pop("_dirty_task_ids", None) or [])
            full_save = bool(state.pop("_sql_full_save", False))

            use_dirty = _sql_dirty_save_enabled() and not full_save and bool(dirty_p or dirty_t)
            if use_dirty and not dirty_p and not dirty_t:
                return True
            if use_dirty:
                product_rows = [products_map[pid] for pid in dirty_p if pid in products_map]
                task_ids = dirty_t
                task_rows = [t for t in task_queue if t.get("id") in task_ids]
                logger.debug(
                    "SQL dirty save: products=%s tasks=%s (of %s/%s)",
                    len(product_rows),
                    len(task_rows),
                    len(products_map),
                    len(task_queue),
                )
            else:
                product_rows = list(products_map.values())
                task_rows = task_queue
                if dirty_p or dirty_t:
                    logger.debug(
                        "SQL full save: products=%s tasks=%s",
                        len(product_rows),
                        len(task_rows),
                    )

            for p in product_rows:
                await self._async_store.upsert_product(p)
            for t in task_rows:
                await self._async_store.upsert_task(t)
            return True
        except Exception:
            logger.exception("Cannot save pipeline state to SQL store")
            return False
