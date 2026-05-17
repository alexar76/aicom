"""Re-open FAILED pipeline products for operator-driven rework."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from core.paths import pipeline_db_path, pipeline_json_path
from core.pipeline_retry_limits import task_max_retries
from web.backend.services.pipeline_failure_report import build_failure_report

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def sqlite_db_path() -> Path:
    return pipeline_db_path()


def _sync_sqlite_from_json() -> None:
    from core.pipeline_state_writer import sync_sqlite_from_pipeline_json

    sync_sqlite_from_pipeline_json()


def _priority(agent_type: str) -> int:
    defaults = {
        "analyst": 3,
        "pm": 4,
        "architect": 4,
        "developer": 5,
        "qa": 4,
        "devops": 3,
        "hardening": 5,
    }
    return int(defaults.get(agent_type, 4))


def _recovery_plan(
    product: dict[str, Any],
    tasks: list[dict[str, Any]],
    *,
    agent_type: str | None,
    target_state: str | None,
) -> tuple[str, str]:
    if agent_type and target_state:
        return agent_type.strip().lower(), target_state.strip().upper()
    report = build_failure_report(product, tasks)
    sug = report.get("suggested_recovery") or {}
    return (
        str(sug.get("agent_type") or "pm").lower(),
        str(sug.get("target_state") or "MARKET_RESEARCHED").upper(),
    )


def _clear_failure_fields(product: dict[str, Any]) -> None:
    for key in ("failure_reason", "last_error", "error"):
        product.pop(key, None)
    meta = product.get("metadata")
    if isinstance(meta, dict):
        for key in ("failure_reason", "error", "last_error"):
            meta.pop(key, None)


def _cancel_active_tasks(tasks: list[dict[str, Any]], now: float) -> int:
    n = 0
    for t in tasks:
        st = str(t.get("status") or "").lower()
        if st in ("pending", "running"):
            t["status"] = "cancelled"
            t["completed_at"] = now
            n += 1
    return n


def _build_recovery_task(
    *,
    pid: str,
    product: dict[str, Any],
    agent_type: str,
    target_state: str,
    notes: str,
    now: float,
) -> dict[str, Any]:
    base_instructions = (product.get("admin_instructions") or "").strip()
    block = (
        f"Operator rework (reopen from FAILED): {(notes or '')[:6000]}\n"
        "Address the failure report root cause before advancing."
    )
    merged_instructions = f"{base_instructions}\n\n{block}".strip() if base_instructions else block

    input_data: dict[str, Any] = {
        "product_id": pid,
        "idea": product.get("idea", ""),
        "admin_instructions": merged_instructions,
        "operator_reopen": True,
        "operator_reopen_notes": (notes or "")[:8000],
    }
    if agent_type == "pm":
        input_data["quality_gates_feedback"] = {
            "passed": False,
            "reasons": [f"Operator reopen: {(notes or '')[:2000]}"],
            "source": "operator_reopen_failed",
        }

    return {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": agent_type,
        "state": target_state,
        "status": "pending",
        "retry_count": 0,
        "max_retries": task_max_retries(),
        "input_data": input_data,
        "output_data": {},
        "created_at": now,
        "priority": _priority(agent_type),
        "auto_requeue_reason": "operator_reopen_failed",
    }


def _reopen_sqlite(
    product_id: str,
    notes: str,
    *,
    agent_type: str | None,
    target_state: str | None,
) -> dict[str, Any]:
    from orchestrator.sqlite_manager import SQLiteManager

    pid = product_id.strip()
    sm = SQLiteManager(str(sqlite_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            return {"ok": False, "reason": "product_not_found"}
        st = str(product.get("state") or "").upper()
        if st != "FAILED":
            return {"ok": False, "reason": "product_not_failed", "state": st}

        tasks = sm.get_tasks_by_product(pid)
        rec_agent, rec_state = _recovery_plan(product, tasks, agent_type=agent_type, target_state=target_state)

        now = time.time()
        try:
            from orchestrator.task_queue_hygiene import is_likely_false_failed_product, recovery_state_after_false_failed

            if is_likely_false_failed_product(product, tasks):
                product["state"] = recovery_state_after_false_failed(product, tasks)
                _clear_failure_fields(product)
                product["updated_at"] = now
                sm.upsert_product(product)
                active = [
                    t
                    for t in tasks
                    if str(t.get("status") or "").lower() in ("pending", "running")
                ]
                if active:
                    return {
                        "ok": True,
                        "product_state": product["state"],
                        "agent_type": str(active[0].get("agent_type") or rec_agent),
                        "target_state": str(active[0].get("state") or rec_state),
                        "cancelled_tasks": 0,
                        "recovered_in_place": True,
                        "message": "False FAILED cleared; existing repair task will continue.",
                    }
        except Exception:
            logger.debug("reopen_failed_product: false-FAILED in-place recovery check failed", exc_info=True)

        if any(
            str(t.get("agent_type") or "") == rec_agent
            and str(t.get("state") or "").upper() == rec_state
            and str(t.get("status") or "").lower() in ("pending", "running")
            for t in tasks
        ):
            _clear_failure_fields(product)
            if rec_agent == "pm":
                product["state"] = "MARKET_RESEARCHED"
            elif rec_agent == "developer":
                product["state"] = "BUG_FOUND"
            product["updated_at"] = now
            sm.upsert_product(product)
            return {
                "ok": True,
                "product_state": product["state"],
                "agent_type": rec_agent,
                "target_state": rec_state,
                "cancelled_tasks": 0,
                "recovery_already_pending": True,
            }

        cancelled = _cancel_active_tasks(tasks, now)
        for t in tasks:
            if str(t.get("status") or "").lower() == "cancelled":
                sm.upsert_task(t)

        meta = dict(product.get("metadata") or {})
        reopen_count = int(meta.get("failed_reopen_count") or 0) + 1
        meta["failed_reopen_count"] = reopen_count
        meta["last_operator_reopen"] = {"at": now, "notes": notes[:8000], "agent": rec_agent, "state": rec_state}

        _clear_failure_fields(product)
        product["metadata"] = meta

        if rec_agent == "pm":
            product["state"] = "MARKET_RESEARCHED"
        elif rec_agent == "developer":
            product["state"] = "BUG_FOUND"
        elif rec_agent == "architect":
            product["state"] = "METHODOLOGY_REVIEWED"
        else:
            product["state"] = rec_state
        product["updated_at"] = now

        new_task = _build_recovery_task(
            pid=pid,
            product=product,
            agent_type=rec_agent,
            target_state=rec_state,
            notes=notes,
            now=now,
        )
        product["admin_instructions"] = new_task["input_data"]["admin_instructions"]
        sm.upsert_product(product)
        sm.upsert_task(new_task)

        logger.warning(
            "reopen_failed_product %s → %s / %s (cancelled %s tasks, reopen #%s)",
            pid,
            product["state"],
            rec_agent,
            cancelled,
            reopen_count,
        )
        return {
            "ok": True,
            "task_id": new_task["id"],
            "product_state": product["state"],
            "agent_type": rec_agent,
            "target_state": rec_state,
            "cancelled_tasks": cancelled,
            "failed_reopen_count": reopen_count,
        }
    finally:
        sm.close()


def _reopen_json(
    product_id: str,
    notes: str,
    *,
    agent_type: str | None,
    target_state: str | None,
) -> dict[str, Any]:
    from core.pipeline_database import pipeline_uses_sql_store
    from core.pipeline_state_writer import read_pipeline_state, write_pipeline_state

    if pipeline_uses_sql_store():
        return _reopen_sqlite(product_id, notes, agent_type=agent_type, target_state=target_state)

    data = read_pipeline_state()
    if not data.get("products"):
        pj = pipeline_json_path()
        if not pj.is_file():
            return {"ok": False, "reason": "pipeline_state_missing"}

    products: dict[str, Any] = data.get("products") or {}
    task_queue: list = data.get("task_queue") or []
    pid = product_id.strip()
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}
    st = str(product.get("state") or "").upper()
    if st != "FAILED":
        return {"ok": False, "reason": "product_not_failed", "state": st}

    product_tasks = [t for t in task_queue if t.get("product_id") == pid]
    report = build_failure_report(product, product_tasks)
    rec_agent, rec_state = _recovery_plan(product, product_tasks, agent_type=agent_type, target_state=target_state)

    if any(
        t.get("product_id") == pid
        and str(t.get("agent_type") or "") == rec_agent
        and str(t.get("state") or "").upper() == rec_state
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    ):
        return {"ok": False, "reason": "recovery_already_pending"}

    now = time.time()
    cancelled = _cancel_active_tasks(product_tasks, now)

    reopen_count = int(product.get("failed_reopen_count") or 0) + 1
    product["failed_reopen_count"] = reopen_count
    product["last_operator_reopen_at"] = now
    product.pop("failure_reason", None)
    product.pop("last_error", None)
    product.pop("error", None)

    if rec_agent == "pm":
        product["state"] = "MARKET_RESEARCHED"
    elif rec_agent == "architect":
        product["state"] = "METHODOLOGY_REVIEWED"
    elif rec_agent == "developer":
        product["state"] = "BUG_FOUND"
    else:
        product["state"] = rec_state

    product["updated_at"] = now
    new_task = _build_recovery_task(
        pid=pid,
        product=product,
        agent_type=rec_agent,
        target_state=rec_state,
        notes=notes,
        now=now,
    )
    product["admin_instructions"] = new_task["input_data"]["admin_instructions"]
    task_queue.append(new_task)
    data["products"][pid] = product
    data["task_queue"] = task_queue
    if not write_pipeline_state(data):
        return {"ok": False, "reason": "pipeline_write_error"}

    return {
        "ok": True,
        "task_id": new_task["id"],
        "product_state": product["state"],
        "agent_type": rec_agent,
        "target_state": rec_state,
        "cancelled_tasks": cancelled,
        "failed_reopen_count": reopen_count,
        "failure_report": report,
    }


def reopen_failed_product(
    product_id: str,
    notes: str,
    *,
    agent_type: str | None = None,
    target_state: str | None = None,
) -> dict[str, Any]:
    """Move FAILED → recovery state and queue a fresh agent task with operator notes."""
    notes = (notes or "").strip()
    if len(notes) < 8:
        return {"ok": False, "reason": "notes_too_short", "min": 8}

    if _truthy("USE_SQLITE", "0") and sqlite_db_path().is_file():
        res = _reopen_sqlite(product_id, notes, agent_type=agent_type, target_state=target_state)
        if res.get("reason") == "product_not_found" and pipeline_json_path().is_file():
            return _reopen_json(product_id, notes, agent_type=agent_type, target_state=target_state)
        return res
    return _reopen_json(product_id, notes, agent_type=agent_type, target_state=target_state)
