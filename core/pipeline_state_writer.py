"""
Unified pipeline state read/write contract.

When ``pipeline_uses_sql_store()`` is true, SQLite/Postgres is the source of truth.
``pipeline.json`` is written only when ``AIFACTORY_PIPELINE_MIRROR_JSON=1`` (explicit mirror)
or when the backend is JSON-only.

API and scripts must use this module instead of writing ``pipeline.json`` directly.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from core.paths import pipeline_db_path, pipeline_json_path
from core.pipeline_database import create_sync_pipeline_manager, pipeline_uses_sql_store

logger = logging.getLogger(__name__)

_DEFAULT_STATE: dict[str, Any] = {"products": {}, "task_queue": [], "current_task_id": None}


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def pipeline_json_mirror_enabled() -> bool:
    """When SQL store is primary, mirror in-memory state to pipeline.json only if enabled."""
    if not pipeline_uses_sql_store():
        return True
    return _truthy("AIFACTORY_PIPELINE_MIRROR_JSON", "0")


def pipeline_json_recovery_enabled() -> bool:
    return _truthy("AIFACTORY_PIPELINE_JSON_RECOVER_FROM_SQLITE", "0")


def empty_pipeline_state() -> dict[str, Any]:
    return {
        "products": {},
        "task_queue": [],
        "current_task_id": None,
    }


def _json_path(path: Path | None = None) -> Path:
    return path or pipeline_json_path()


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cannot read pipeline JSON at %s: %s", path, e)
        return None


def _write_json_file(state: dict[str, Any], path: Path | None = None) -> bool:
    p = _json_path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        compact = _truthy("AIFACTORY_PIPELINE_JSON_COMPACT", "0")
        if compact:
            p.write_text(
                json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        else:
            p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError:
        logger.exception("Cannot write pipeline JSON at %s", p)
        return False


def sqlite_store_mtime() -> float:
    db = pipeline_db_path()
    try:
        return db.stat().st_mtime if db.is_file() else 0.0
    except OSError:
        return 0.0


def pipeline_json_mtime(path: Path | None = None) -> float:
    p = _json_path(path)
    try:
        return p.stat().st_mtime if p.is_file() else 0.0
    except OSError:
        return 0.0


def sqlite_state_newer_than_json(path: Path | None = None) -> bool:
    """True when the SQL store file is newer than pipeline.json (by filesystem mtime)."""
    return sqlite_store_mtime() > pipeline_json_mtime(path)


def should_recover_json_from_sqlite(path: Path | None = None) -> bool:
    """
  Allow rebuilding corrupt pipeline.json from SQLite when the operator opted in
  or when the database is strictly newer than the JSON file.
    """
    if pipeline_json_recovery_enabled():
        return True
    return sqlite_state_newer_than_json(path)


def read_pipeline_state_from_sql() -> dict[str, Any] | None:
    try:
        mgr = create_sync_pipeline_manager()
        try:
            products = mgr.get_all_products()
            tasks = mgr.get_all_tasks()
        finally:
            close = getattr(mgr, "close", None)
            if callable(close):
                close()

        products_map: dict[str, dict] = {}
        for p in products:
            pid = p.get("id")
            if isinstance(pid, str) and pid:
                products_map[pid] = p

        current_task_id = None
        for t in tasks:
            st = str(t.get("status") or "").upper()
            if st == "RUNNING":
                current_task_id = t.get("id")
                break
            if st == "PENDING" and current_task_id is None:
                current_task_id = t.get("id")

        return {
            "products": products_map,
            "task_queue": tasks,
            "current_task_id": current_task_id,
        }
    except Exception:
        logger.exception("Failed to read pipeline state from SQL store")
        return None


def read_pipeline_state(*, json_path: Path | None = None) -> dict[str, Any]:
    if pipeline_uses_sql_store():
        state = read_pipeline_state_from_sql()
        return state if state is not None else empty_pipeline_state()
    data = _read_json_file(_json_path(json_path))
    if data is None:
        return empty_pipeline_state()
    data.setdefault("products", {})
    data.setdefault("task_queue", [])
    data.setdefault("current_task_id", None)
    return data


def apply_state_to_sql_store(state: dict[str, Any], *, sql_full_save: bool = True) -> bool:
    """Upsert products and tasks from an in-memory pipeline snapshot."""
    products_map: dict[str, dict] = state.get("products") or {}
    task_queue: list[dict] = state.get("task_queue") or []
    try:
        mgr = create_sync_pipeline_manager()
        try:
            for p in products_map.values():
                if isinstance(p, dict) and p.get("id"):
                    mgr.upsert_product(p)
            for t in task_queue:
                if isinstance(t, dict) and t.get("id"):
                    mgr.upsert_task(t)
        finally:
            close = getattr(mgr, "close", None)
            if callable(close):
                close()
        return True
    except Exception:
        logger.exception("Cannot apply pipeline state to SQL store (full_save=%s)", sql_full_save)
        return False


def write_pipeline_state(
    state: dict[str, Any],
    *,
    json_path: Path | None = None,
    mirror_json: bool | None = None,
) -> bool:
    """
    Persist pipeline snapshot using the configured backend.

    ``mirror_json`` overrides ``AIFACTORY_PIPELINE_MIRROR_JSON`` when SQL is primary.
    """
    state = dict(state)
    state.pop("_dirty_product_ids", None)
    state.pop("_dirty_task_ids", None)
    state.pop("_sql_full_save", None)

    if pipeline_uses_sql_store():
        ok = apply_state_to_sql_store(state)
        do_mirror = mirror_json if mirror_json is not None else pipeline_json_mirror_enabled()
        if ok and do_mirror:
            if not _write_json_file(state, json_path):
                logger.warning("SQL save OK but pipeline.json mirror failed")
        return ok

    return _write_json_file(state, json_path)


def append_product_to_pipeline_state(
    product: dict,
    *,
    pipeline_path: Path | None = None,
) -> bool:
    """Insert or update one product in the active pipeline store."""
    pid = product.get("id")
    if not isinstance(pid, str) or not pid:
        raise ValueError("product must include a non-empty id")

    if pipeline_uses_sql_store():
        try:
            mgr = create_sync_pipeline_manager()
            try:
                mgr.upsert_product(product)
            finally:
                close = getattr(mgr, "close", None)
                if callable(close):
                    close()
        except Exception:
            logger.exception("Cannot append product %s to SQL pipeline store", pid)
            return False

        if pipeline_json_mirror_enabled():
            path = _json_path(pipeline_path)
            state = _read_json_file(path) or empty_pipeline_state()
            state.setdefault("products", {})
            state.setdefault("task_queue", [])
            state["products"][pid] = product
            _write_json_file(state, path)
        return True

    path = _json_path(pipeline_path)
    state = _read_json_file(path) or empty_pipeline_state()
    state.setdefault("task_queue", [])
    state.setdefault("products", {})
    state["products"][pid] = product
    return _write_json_file(state, path)


def sync_sqlite_from_pipeline_json(
    *,
    json_path: Path | None = None,
    db_path: str | None = None,
) -> None:
    """
    Legacy JSON→SQL import (scripts, one-off repair).

    When SQL is already primary, logs a warning and no-ops unless mirror mode implies
    intentional JSON export→import.
    """
    if pipeline_uses_sql_store() and not _truthy("AIFACTORY_PIPELINE_ALLOW_JSON_TO_SQL_IMPORT", "0"):
        logger.debug(
            "sync_sqlite_from_pipeline_json skipped: SQL store is primary "
            "(set AIFACTORY_PIPELINE_ALLOW_JSON_TO_SQL_IMPORT=1 to force import)"
        )
        return
    if not _truthy("USE_SQLITE", "true") and not pipeline_uses_sql_store():
        return
    try:
        from orchestrator.migrate import migrate

        migrate(
            json_path=str(_json_path(json_path)),
            db_path=db_path or str(pipeline_db_path()),
        )
    except Exception as e:
        logger.warning("SQLite sync from pipeline JSON skipped: %s", e)
