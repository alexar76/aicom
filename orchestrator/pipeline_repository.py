"""
Pipeline persistence
====================
Storage for :class:`orchestrator.state_machine.PipelineStateMachine`.

The state machine used to carry its own JSON/SQLite I/O inline. Splitting it out
leaves the state machine with transitions, the task queue and metrics, and gives the
storage side room for three things it needs and did not have:

* **Writes proportional to the change.** The old SQLite save re-upserted every product
  and every task on every mutation, so flipping one task's status cost O(all state)
  row writes — and re-fired the per-product deploy hook each time. Each entity's
  last-persisted form is fingerprinted here and only moved rows are written.
* **One long-lived async connection.** The old async save constructed an
  ``AsyncSQLiteManager``, ran its schema bootstrap and closed it again on every call.
* **An atomic task claim.** ``pending -> running`` goes through a conditional UPDATE,
  so two workers racing for the same task cannot both win it — and a claim the store
  cannot confirm is refused, never assumed.

Writes of the JSON document go through a temp file and a rename, and a document that
exists but does not parse stops the load instead of reading as empty.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from core.json_state import write_json_atomic

logger = logging.getLogger(__name__)


class PipelineStateLoadError(RuntimeError):
    """The stored pipeline state exists but could not be read.

    Raised instead of returning an empty state: a machine that started empty would
    write that emptiness back over the real document on its first save.
    """


class TaskClaimUnavailable(RuntimeError):
    """The store could not confirm a claim, so nobody may run the task yet."""


class PipelineRepository:
    """Loads and persists pipeline state, tracking what actually changed."""

    def __init__(self, state_file: str, db_path: str, use_sqlite: bool) -> None:
        self.state_file = state_file
        self.db_path = db_path
        self.use_sqlite = use_sqlite
        self._sqlite_manager = None
        self._async_manager = None
        self._async_manager_loop: asyncio.AbstractEventLoop | None = None
        # "p:<id>" / "t:<id>" -> serialized form as last written to the store.
        self._persisted: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    @property
    def sqlite_manager(self):
        """Lazy-init the synchronous SQLiteManager when use_sqlite=True."""
        if self._sqlite_manager is None and self.use_sqlite:
            from .sqlite_manager import SQLiteManager

            self._sqlite_manager = SQLiteManager(self.db_path)
            self._sqlite_manager.connect()
        return self._sqlite_manager

    async def _async_manager_for_loop(self):
        """Return the cached AsyncSQLiteManager, opening one on first use.

        aiosqlite binds its worker thread to the loop that opened the connection, so a
        repository reused across loops (chiefly ``asyncio.run`` per test) reopens rather
        than handing out a connection whose futures belong to a dead loop.
        """
        from .async_sqlite_manager import AsyncSQLiteManager

        loop = asyncio.get_running_loop()
        if self._async_manager is not None and self._async_manager_loop is not loop:
            await self._close_async_manager()
        if self._async_manager is None:
            manager = AsyncSQLiteManager(self.db_path)
            await manager.initialize()
            self._async_manager = manager
            self._async_manager_loop = loop
        return self._async_manager

    async def _close_async_manager(self) -> None:
        manager, self._async_manager, self._async_manager_loop = self._async_manager, None, None
        if manager is None:
            return
        try:
            await manager.close()
        except Exception as exc:
            logger.debug("Async SQLite manager close failed: %s", exc)

    async def aclose(self) -> None:
        """Close the async connection. Safe to call when none was ever opened."""
        await self._close_async_manager()

    def close(self) -> None:
        """Close the synchronous connection. Safe to call when none was ever opened."""
        manager, self._sqlite_manager = self._sqlite_manager, None
        if manager is None:
            return
        try:
            manager.close()
        except Exception as exc:
            logger.debug("SQLite manager close failed: %s", exc)

    # ------------------------------------------------------------------
    # Change tracking
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, default=str)

    def record_persisted(self, products: list[dict], tasks: list[dict]) -> None:
        """Adopt this state as the baseline, so a fresh load does not re-save itself."""
        self._persisted = {}
        for product in products:
            self._persisted[f"p:{product.get('id')}"] = self._fingerprint(product)
        for task in tasks:
            self._persisted[f"t:{task.get('id')}"] = self._fingerprint(task)

    def mark_all_dirty(self) -> None:
        """Drop the baseline so the next save rewrites everything."""
        self._persisted = {}

    def _split_changed(
        self, products: list[dict], tasks: list[dict]
    ) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], dict[str, str]]:
        """Return the (key, payload) pairs whose serialized form moved, plus all keys."""
        current: dict[str, str] = {}
        changed_products: list[tuple[str, dict]] = []
        changed_tasks: list[tuple[str, dict]] = []
        for product in products:
            key = f"p:{product.get('id')}"
            fingerprint = self._fingerprint(product)
            current[key] = fingerprint
            if self._persisted.get(key) != fingerprint:
                changed_products.append((key, product))
        for task in tasks:
            key = f"t:{task.get('id')}"
            fingerprint = self._fingerprint(task)
            current[key] = fingerprint
            if self._persisted.get(key) != fingerprint:
                changed_tasks.append((key, task))
        return changed_products, changed_tasks, current

    def _commit_baseline(self, current: dict[str, str], written: set[str]) -> None:
        """Advance the baseline for rows that were written; drop entities that vanished.

        Rows whose write raised keep their old fingerprint, so the next save retries them.
        """
        baseline = {key: value for key, value in self._persisted.items() if key in current}
        for key in written:
            baseline[key] = current[key]
        self._persisted = baseline

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_json(self) -> dict[str, Any]:
        """Read the JSON state document. A missing file is an empty state.

        Raises:
            PipelineStateLoadError: the file exists but cannot be read or parsed. It is
                left untouched on disk for recovery.
        """
        path = Path(self.state_file)
        if not path.exists():
            return {"products": {}, "task_queue": []}
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError(f"top level is {type(data).__name__}, not an object")
            return {
                "products": data.get("products", {}) or {},
                "task_queue": data.get("task_queue", []) or [],
            }
        except (OSError, ValueError) as exc:
            raise PipelineStateLoadError(
                f"Pipeline state {path} exists but cannot be read ({exc}); "
                "refusing to start from an empty state over it"
            ) from exc

    def load_sqlite(self) -> dict[str, Any]:
        """Read products and tasks from SQLite.

        Raises:
            PipelineStateLoadError: the store could not be opened or read.
        """
        try:
            manager = self.sqlite_manager
            return {
                "products": manager.get_all_products(),
                "task_queue": manager.get_all_tasks(),
            }
        except Exception as exc:
            raise PipelineStateLoadError(
                f"Pipeline state in {self.db_path} cannot be read ({exc})"
            ) from exc

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_json(self, products: dict[str, dict], tasks: list[dict]) -> bool:
        """Rewrite the JSON document when anything moved. Returns True if it was written.

        JSON is a single document, so there is no partial write to make — but an
        unchanged state still costs nothing. The rewrite goes through a sibling temp
        file and a rename, so a crash mid-write leaves the previous document intact.
        """
        changed_products, changed_tasks, current = self._split_changed(
            list(products.values()), tasks
        )
        path = Path(self.state_file)
        vanished = set(self._persisted) - set(current)
        if not changed_products and not changed_tasks and not vanished and path.exists():
            return False
        try:
            data = {
                "products": products,
                "task_queue": tasks,
                "updated_at": time.time(),
            }
            write_json_atomic(path, data, indent=2, ensure_ascii=True)
        except Exception as exc:
            logger.error(f"Failed to save pipeline state: {exc}")
            return False
        self._commit_baseline(current, set(current))
        return True

    def save_sqlite(
        self,
        products: dict[str, dict],
        tasks: list[dict],
        *,
        on_product_saved: Callable[[dict], None] | None = None,
    ) -> tuple[int, int]:
        """Upsert only the products and tasks whose serialized form changed.

        ``on_product_saved`` fires per written product — it is how the deploy-time
        showcase hook stays out of this module, and firing it only on change is also
        what the hook's name implies.
        """
        try:
            manager = self.sqlite_manager
            if manager is None:
                return 0, 0
        except Exception as exc:
            logger.error(f"Failed to save pipeline state to SQLite: {exc}")
            return 0, 0

        changed_products, changed_tasks, current = self._split_changed(
            list(products.values()), tasks
        )
        written: set[str] = set()
        for key, product in changed_products:
            try:
                manager.upsert_product(product)
            except Exception as exc:
                logger.error(f"Failed to save product {product.get('id')} to SQLite: {exc}")
                continue
            written.add(key)
            if on_product_saved is not None:
                try:
                    on_product_saved(product)
                except Exception as exc:
                    logger.warning("Post-save product hook failed for %s: %s", product.get("id"), exc)
        for key, task in changed_tasks:
            try:
                manager.upsert_task(task)
            except Exception as exc:
                logger.error(f"Failed to save task {task.get('id')} to SQLite: {exc}")
                continue
            written.add(key)

        self._commit_baseline(current, written)
        logger.debug(
            "Saved pipeline state to SQLite: %d/%d products, %d/%d tasks",
            len(changed_products), len(products), len(changed_tasks), len(tasks),
        )
        return len(changed_products), len(changed_tasks)

    async def asave_sqlite(
        self,
        products: dict[str, dict],
        tasks: list[dict],
        *,
        on_product_saved: Callable[[dict], None] | None = None,
    ) -> tuple[int, int]:
        """Async twin of :meth:`save_sqlite`, over the cached connection."""
        try:
            manager = await self._async_manager_for_loop()
        except Exception as exc:
            logger.error(f"Failed to open async SQLite connection: {exc}")
            return 0, 0

        changed_products, changed_tasks, current = self._split_changed(
            list(products.values()), tasks
        )
        written: set[str] = set()
        for key, product in changed_products:
            try:
                await manager.upsert_product(product)
            except Exception as exc:
                logger.error(f"Failed to save product {product.get('id')} to SQLite: {exc}")
                continue
            written.add(key)
            if on_product_saved is not None:
                try:
                    on_product_saved(product)
                except Exception as exc:
                    logger.warning("Post-save product hook failed for %s: %s", product.get("id"), exc)
        for key, task in changed_tasks:
            try:
                await manager.upsert_task(task)
            except Exception as exc:
                logger.error(f"Failed to save task {task.get('id')} to SQLite: {exc}")
                continue
            written.add(key)

        self._commit_baseline(current, written)
        return len(changed_products), len(changed_tasks)

    async def asave_json(self, products: dict[str, dict], tasks: list[dict]) -> bool:
        """Run the blocking JSON write off the event loop."""
        return await asyncio.to_thread(self.save_json, products, tasks)

    # ------------------------------------------------------------------
    # Task claiming
    # ------------------------------------------------------------------

    def claim_pending_task(
        self, task_id: str, started_at: float, task: dict | None = None
    ) -> bool:
        """Flip one task pending -> running in the store. False means someone else won it.

        ``task`` is the in-memory row, inserted already running when the store has no
        row for it yet. With the JSON backend, which is single-worker by construction,
        the caller's in-process lock is the guard and this always grants.

        Raises:
            TaskClaimUnavailable: the store could not confirm the claim. Running the
                task anyway is how two workers both run it, so the caller must not.
        """
        if not self.use_sqlite:
            return True
        try:
            return self.sqlite_manager.claim_pending_task(task_id, started_at, task)
        except Exception as exc:
            raise TaskClaimUnavailable(f"claim of task {task_id} not confirmed: {exc}") from exc

    async def aclaim_pending_task(
        self, task_id: str, started_at: float, task: dict | None = None
    ) -> bool:
        """Async twin of :meth:`claim_pending_task`."""
        if not self.use_sqlite:
            return True
        try:
            manager = await self._async_manager_for_loop()
            return await manager.claim_pending_task(task_id, started_at, task)
        except Exception as exc:
            raise TaskClaimUnavailable(f"claim of task {task_id} not confirmed: {exc}") from exc

    def read_task(self, task_id: str) -> dict | None:
        """Read one task back from the store (used to resync a task we lost the race for)."""
        if not self.use_sqlite:
            return None
        try:
            manager = self.sqlite_manager
            if manager is None:
                return None
            return manager.get_task(task_id)
        except Exception as exc:
            logger.debug("Task reread for %s failed: %s", task_id, exc)
            return None

    async def aread_task(self, task_id: str) -> dict | None:
        """Async twin of :meth:`read_task`."""
        if not self.use_sqlite:
            return None
        try:
            manager = await self._async_manager_for_loop()
            rows = await manager.fetchall(
                "SELECT * FROM tasks WHERE id = ? AND workspace_id = ? LIMIT 1",
                (task_id, manager.workspace_id),
            )
            return rows[0] if rows else None
        except Exception as exc:
            logger.debug("Task reread for %s failed: %s", task_id, exc)
            return None

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate_json_to_sqlite(self, db_path: str | None = None) -> dict:
        """Bulk-copy the JSON state document into SQLite. Does NOT modify the JSON file."""
        from .sqlite_manager import SQLiteManager

        target_db = db_path or self.db_path
        manager = SQLiteManager(target_db)
        manager.connect()

        try:
            path = Path(self.state_file)
            if not path.exists():
                logger.warning(f"State file {self.state_file} not found; nothing to migrate.")
                return {"products_migrated": 0, "tasks_migrated": 0}

            with open(path) as handle:
                data = json.load(handle)

            product_dicts = list(data.get("products", {}).values())
            task_dicts = data.get("task_queue", [])

            product_count = manager.bulk_insert_products(product_dicts)
            task_count = manager.bulk_insert_tasks(task_dicts, merge_from_json=True)

            logger.info(
                f"Migration complete: {product_count} products, {task_count} tasks "
                f"migrated to {target_db}"
            )
            return {
                "products_migrated": product_count,
                "tasks_migrated": task_count,
            }
        except Exception as exc:
            logger.error(f"Migration failed: {exc}")
            raise
        finally:
            manager.close()
