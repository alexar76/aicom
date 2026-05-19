"""
Human-triggered pipeline rework for shipped products (same path as user-support inject).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from orchestrator.pipeline_flow import PIPELINE_AGENT_FLOW

from core.quality_settings import max_pipeline_repair_rounds

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION"})


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def pipeline_json_path() -> Path:
    from core.paths import pipeline_json_path

    return pipeline_json_path()


def sqlite_db_path() -> Path:
    from core.paths import pipeline_db_path

    return pipeline_db_path()


def _sync_sqlite_from_json() -> None:
    if not _truthy("USE_SQLITE", "0"):
        return
    try:
        from orchestrator.migrate import migrate

        migrate(json_path=str(pipeline_json_path()), db_path=str(sqlite_db_path()))
        logger.info("SQLite synced after human_admin rework inject")
    except Exception:
        logger.exception("SQLite sync after human_admin rework failed")


def _dev_fixing_pending_sqlite(pid: str) -> bool:
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(sqlite_db_path()))
        sm.connect()
        try:
            for t in sm.get_tasks_by_product(pid):
                if (
                    str(t.get("agent_type") or "") == "developer"
                    and str(t.get("state") or "").upper() == "DEV_FIXING"
                    and str(t.get("status") or "").lower() in ("pending", "running")
                ):
                    return True
        finally:
            sm.close()
    except Exception:
        logger.exception("human_pipeline pending check sqlite")
    return False


def _inject_via_sqlite(product_id: str, notes: str) -> dict[str, Any]:
    from orchestrator.sqlite_manager import SQLiteManager

    max_loops = max_pipeline_repair_rounds()
    pid = product_id.strip()
    sm = SQLiteManager(str(sqlite_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            return {"ok": False, "reason": "product_not_found"}
        st = (product.get("state") or "").upper()
        if st not in _TERMINAL_STATES:
            return {"ok": False, "reason": "product_not_terminal", "state": st}
        if _dev_fixing_pending_sqlite(pid):
            return {"ok": False, "reason": "dev_fix_already_pending"}

        meta = dict(product.get("metadata") or {})
        new_round = int(meta.get("quality_repair_round") or 0) + 1
        if new_round > max_loops:
            return {"ok": False, "reason": "repair_budget_exhausted", "max_loops": max_loops}

        now = time.time()
        meta["quality_repair_round"] = new_round
        meta["human_admin_rework"] = {"requested_at": now, "notes": (notes or "")[:8000]}

        product["state"] = "BUG_FOUND"
        product["updated_at"] = now
        product["metadata"] = meta
        sm.upsert_product(product)

        dev_task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "product_id": pid,
            "agent_type": "developer",
            "state": "DEV_FIXING",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {
                "product_id": pid,
                "idea": product.get("idea", ""),
                "demo_quality_feedback": {
                    "source": "human_admin_rework",
                    "notes": (notes or "")[:8000],
                },
                "quality_gates_feedback": {
                    "passed": False,
                    "reasons": [f"Human admin rework: {(notes or '')[:2000]}"],
                    "source": "human_admin_rework",
                },
                "quality_repair_round": new_round,
                "quality_repair_max": max_loops,
                "qa_gate_blocked": True,
                "human_admin_rework": True,
            },
            "output_data": {},
            "created_at": now,
            "priority": 5,
        }
        sm.upsert_task(dev_task)
        logger.warning(
            "human_admin_rework → BUG_FOUND / DEV_FIXING for %s round %s/%s",
            pid,
            new_round,
            max_loops,
        )
        return {"ok": True, "task_id": dev_task["id"], "repair_round": new_round}
    finally:
        sm.close()


def _inject_via_pipeline_json(product_id: str, notes: str) -> dict[str, Any]:
    """Same shape as support_pipeline.inject_user_support_bug (pipeline.json + migrate)."""
    max_loops = max_pipeline_repair_rounds()

    pj = pipeline_json_path()
    if not pj.is_file():
        return {"ok": False, "reason": "pipeline_state_missing"}

    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("human_pipeline: cannot read pipeline: %s", e)
        return {"ok": False, "reason": "pipeline_read_error"}

    products: dict[str, Any] = data.get("products") or {}
    task_queue: list = data.get("task_queue") or []

    pid = product_id.strip()
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}

    state = (product.get("state") or "").upper()
    if state not in _TERMINAL_STATES:
        return {"ok": False, "reason": "product_not_terminal", "state": state}

    def _pending_json() -> bool:
        return any(
            t.get("product_id") == pid
            and t.get("agent_type") == "developer"
            and str(t.get("state") or "").upper() == "DEV_FIXING"
            and str(t.get("status") or "").lower() in ("pending", "running")
            for t in task_queue
        )

    if _pending_json():
        return {"ok": False, "reason": "dev_fix_already_pending"}

    new_round = int(product.get("quality_repair_round") or 0) + 1
    now = time.time()
    product["quality_repair_round"] = new_round
    product["updated_at"] = now
    product["last_human_admin_rework_at"] = now

    if new_round > max_loops:
        product["state"] = "FAILED"
        product["failure_reason"] = (
            f"Human rework exhausted repair budget ({max_loops} rounds). Manual review required."
        )
        pj.parent.mkdir(parents=True, exist_ok=True)
        pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _sync_sqlite_from_json()
        return {"ok": False, "reason": "repair_budget_exhausted"}

    product["state"] = "BUG_FOUND"

    demo_payload = {
        "source": "human_admin_rework",
        "notes": (notes or "")[:8000],
    }

    dev_task = {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": "developer",
        "state": "DEV_FIXING",
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
            "demo_quality_feedback": demo_payload,
            "quality_gates_feedback": {
                "passed": False,
                "demo_quality": demo_payload,
                "reasons": [f"Human admin rework: {(notes or '')[:2000]}"],
                "source": "human_admin_rework",
            },
            "quality_repair_round": new_round,
            "quality_repair_max": max_loops,
            "qa_gate_blocked": True,
            "human_admin_rework": True,
        },
        "created_at": now,
        "priority": 5,
    }
    task_queue.append(dev_task)
    data["task_queue"] = task_queue
    data["products"][pid] = product

    pj.parent.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _sync_sqlite_from_json()
    logger.warning("human_admin_rework → BUG_FOUND / DEV_FIXING for %s round %s", pid, new_round)
    return {"ok": True, "task_id": dev_task["id"], "repair_round": new_round}


def _data_feedback_root() -> Path:
    """``…/data`` directory (pipeline.json lives under ``…/data/state/``)."""
    pj = pipeline_json_path()
    return pj.parent.parent


def _append_human_feedback(product_id: str, decision: str, note: str = "") -> None:
    fb_dir = _data_feedback_root() / "feedback"
    fb_dir.mkdir(parents=True, exist_ok=True)
    path = fb_dir / f"fb-{uuid.uuid4().hex[:16]}.json"
    payload = {
        "product_id": product_id.strip(),
        "source": "human_review",
        "review_decision": decision,
        "tags": ["human_review", decision],
        "note": (note or "")[:8000],
        "created_at": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("human_review feedback written: %s decision=%s", path.name, decision)


def _fire_preview_deploy_hook(product_id: str, event: str) -> None:
    url = os.environ.get("AIFACTORY_PREVIEW_DEPLOY_WEBHOOK_URL", "").strip()
    if not url:
        return
    body = json.dumps(
        {"product_id": product_id, "event": event, "ts": time.time()},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                logger.warning("preview deploy webhook HTTP %s for %s", resp.status, product_id)
    except urllib.error.URLError as e:
        logger.warning("preview deploy webhook failed for %s: %s", product_id, e)


def _agent_priority(agent_type: str) -> int:
    priorities = {
        "analyst": 1,
        "pm": 2,
        "marketing": 3,
        "methodologist": 4,
        "architect": 5,
        "developer": 6,
        "design_critic": 6,
        "hardening": 6,
        "qa": 7,
        "security": 7,
        "devops": 8,
        "sales": 9,
        "evolution_analyst": 10,
    }
    return priorities.get(agent_type, 5)


def _sales_task_dict(product: dict) -> dict[str, Any]:
    agent_type, next_state = PIPELINE_AGENT_FLOW["SALES_ACTIVE"]
    pid = str(product.get("id") or "").strip()
    now = time.time()
    return {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "workspace_id": os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default",
        "product_id": pid,
        "agent_type": agent_type,
        "state": next_state,
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
            "human_post_devops_review": {"decision": "approve"},
        },
        "output_data": {},
        "created_at": now,
        "priority": _agent_priority(agent_type),
    }


def _sales_task_pending_sqlite(sm: Any, pid: str) -> bool:
    try:
        for t in sm.get_tasks_by_product(pid):
            if (
                str(t.get("agent_type") or "") == "sales"
                and str(t.get("status") or "").lower() in ("pending", "running")
            ):
                return True
    except Exception:
        logger.exception("human_gate sales pending check (sqlite)")
    return False


def _sales_task_pending_json(task_queue: list, pid: str) -> bool:
    return any(
        t.get("product_id") == pid
        and str(t.get("agent_type") or "") == "sales"
        and str(t.get("status") or "").lower() in ("pending", "running")
        for t in task_queue
    )


def _approve_followup_sidecar(product_id: str, note: str) -> dict[str, Any]:
    from web.backend.services.product_followup import record_post_devops_human_review_approval

    followup = record_post_devops_human_review_approval(product_id, note)
    return {
        "storefront_followup": followup,
        "storefront_force_list": bool(followup.get("admin_force_list")),
    }


def _approve_apply_product(
    product: dict[str, Any],
    *,
    note: str,
    sales_pending: bool,
    queue_sales,
) -> dict[str, Any]:
    """Shared approve body: SALES_ACTIVE + optional sales task + durable follow-up."""
    pid = str(product.get("id") or "").strip()
    st = str(product.get("state") or "").upper()
    now = time.time()

    if st != "HUMAN_REVIEW_PENDING":
        ranks = {
            "HUMAN_REVIEW_PENDING": 0,
            "SALES_ACTIVE": 1,
            "SANDBOX_RUNNING": 2,
            "TELEMETRY_COLLECTING": 3,
            "EVOLUTION_ANALYZING": 4,
            "COMPLETED": 5,
            "DEPLOYED_PRODUCTION": 5,
        }
        if ranks.get(st, -1) > 0:
            sidecar = _approve_followup_sidecar(pid, note)
            return {
                "ok": True,
                "state": st,
                "already_approved": True,
                "message": "already_past_human_gate",
                **sidecar,
            }
        return {"ok": False, "reason": "not_at_human_gate", "state": st}

    sidecar = _approve_followup_sidecar(pid, note)
    product["state"] = "SALES_ACTIVE"
    product["updated_at"] = now
    product["post_devops_human_review"] = {
        "status": "approved",
        "at": now,
        "note": (note or "")[:8000],
    }

    task_id: str | None = None
    if sales_pending:
        return {
            "ok": True,
            "state": "SALES_ACTIVE",
            "already_approved": True,
            "message": "sales_already_queued",
            **sidecar,
        }

    task = queue_sales(product)
    task_id = str(task.get("id") or "")
    _append_human_feedback(pid, "approve", note)
    _fire_preview_deploy_hook(pid, "human_review_approved")
    logger.warning("post_devops human approve → SALES_ACTIVE + sales task for %s", pid)
    return {
        "ok": True,
        "task_id": task_id,
        "state": "SALES_ACTIVE",
        "message": "sales_queued",
        **sidecar,
    }


def _approve_via_sqlite(product_id: str, note: str) -> dict[str, Any]:
    from orchestrator.sqlite_manager import SQLiteManager

    pid = product_id.strip()
    sm = SQLiteManager(str(sqlite_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            return {"ok": False, "reason": "product_not_found"}

        def _queue_sales(prod: dict) -> dict:
            task = _sales_task_dict(prod)
            sm.upsert_task(task)
            return task

        res = _approve_apply_product(
            product,
            note=note,
            sales_pending=_sales_task_pending_sqlite(sm, pid),
            queue_sales=_queue_sales,
        )
        if res.get("ok") and not res.get("already_approved"):
            sm.upsert_product(product)
        elif res.get("ok") and res.get("message") == "sales_already_queued":
            sm.upsert_product(product)
        return res
    finally:
        sm.close()


def _approve_via_pipeline_json(product_id: str, note: str) -> dict[str, Any]:
    pj = pipeline_json_path()
    if not pj.is_file():
        return {"ok": False, "reason": "pipeline_state_missing"}
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("human_gate approve: cannot read pipeline: %s", e)
        return {"ok": False, "reason": "pipeline_read_error"}

    products: dict[str, Any] = data.get("products") or {}
    task_queue: list = data.get("task_queue") or []
    pid = product_id.strip()
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}

    def _queue_sales(prod: dict) -> dict:
        task = _sales_task_dict(prod)
        task.pop("workspace_id", None)
        task_queue.append(task)
        return task

    res = _approve_apply_product(
        product,
        note=note,
        sales_pending=_sales_task_pending_json(task_queue, pid),
        queue_sales=_queue_sales,
    )
    if res.get("ok"):
        data["products"][pid] = product
        data["task_queue"] = task_queue
        pj.parent.mkdir(parents=True, exist_ok=True)
        pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _sync_sqlite_from_json()
    return res


def approve_post_devops_human_review(product_id: str, note: str = "") -> dict[str, Any]:
    """Resume pipeline after post-DevOps gate: SALES_ACTIVE + queued sales task."""
    note = (note or "").strip()
    if _truthy("USE_SQLITE", "0") and sqlite_db_path().is_file():
        res = _approve_via_sqlite(product_id, note)
        if res.get("reason") == "product_not_found" and pipeline_json_path().is_file():
            return _approve_via_pipeline_json(product_id, note)
        return res
    return _approve_via_pipeline_json(product_id, note)


def _reject_via_sqlite(product_id: str, notes: str) -> dict[str, Any]:
    from orchestrator.sqlite_manager import SQLiteManager

    max_loops = max_pipeline_repair_rounds()
    pid = product_id.strip()
    sm = SQLiteManager(str(sqlite_db_path()))
    sm.connect()
    try:
        product = sm.get_product(pid)
        if not product:
            return {"ok": False, "reason": "product_not_found"}
        st = str(product.get("state") or "").upper()
        if st != "HUMAN_REVIEW_PENDING":
            return {"ok": False, "reason": "not_at_human_gate", "state": st}
        if _dev_fixing_pending_sqlite(pid):
            return {"ok": False, "reason": "dev_fix_already_pending"}

        meta = dict(product.get("metadata") or {})
        new_round = int(meta.get("quality_repair_round") or 0) + 1
        if new_round > max_loops:
            return {"ok": False, "reason": "repair_budget_exhausted", "max_loops": max_loops}

        now = time.time()
        meta["quality_repair_round"] = new_round
        meta["post_devops_human_review"] = {
            "status": "rejected",
            "at": now,
            "notes": notes[:8000],
        }
        product["state"] = "BUG_FOUND"
        product["updated_at"] = now
        product["metadata"] = meta
        sm.upsert_product(product)

        dev_task = {
            "id": f"task-{uuid.uuid4().hex[:12]}",
            "workspace_id": os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default",
            "product_id": pid,
            "agent_type": "developer",
            "state": "DEV_FIXING",
            "status": "pending",
            "retry_count": 0,
            "max_retries": 3,
            "input_data": {
                "product_id": pid,
                "idea": product.get("idea", ""),
                "human_post_devops_review": {"decision": "reject", "notes": notes[:8000]},
                "quality_gates_feedback": {
                    "passed": False,
                    "reasons": [f"Human post-DevOps reject: {notes[:2000]}"],
                    "source": "human_post_devops_review",
                },
                "quality_repair_round": new_round,
                "quality_repair_max": max_loops,
                "qa_gate_blocked": True,
            },
            "output_data": {},
            "created_at": now,
            "priority": _agent_priority("developer"),
        }
        sm.upsert_task(dev_task)
        _append_human_feedback(pid, "block", notes)
        logger.warning(
            "post_devops human reject → BUG_FOUND / DEV_FIXING for %s round %s/%s",
            pid,
            new_round,
            max_loops,
        )
        return {"ok": True, "task_id": dev_task["id"], "repair_round": new_round, "state": "BUG_FOUND"}
    finally:
        sm.close()


def _reject_via_pipeline_json(product_id: str, notes: str) -> dict[str, Any]:
    max_loops = max_pipeline_repair_rounds()

    pj = pipeline_json_path()
    if not pj.is_file():
        return {"ok": False, "reason": "pipeline_state_missing"}
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("human_gate reject: cannot read pipeline: %s", e)
        return {"ok": False, "reason": "pipeline_read_error"}

    products: dict[str, Any] = data.get("products") or {}
    task_queue: list = data.get("task_queue") or []
    pid = product_id.strip()
    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}
    st = str(product.get("state") or "").upper()
    if st != "HUMAN_REVIEW_PENDING":
        return {"ok": False, "reason": "not_at_human_gate", "state": st}

    def _pending_json() -> bool:
        return any(
            t.get("product_id") == pid
            and t.get("agent_type") == "developer"
            and str(t.get("state") or "").upper() == "DEV_FIXING"
            and str(t.get("status") or "").lower() in ("pending", "running")
            for t in task_queue
        )

    if _pending_json():
        return {"ok": False, "reason": "dev_fix_already_pending"}

    new_round = int(product.get("quality_repair_round") or 0) + 1
    now = time.time()
    product["post_devops_human_review"] = {
        "status": "rejected",
        "at": now,
        "notes": notes[:8000],
    }
    product["quality_repair_round"] = new_round
    product["updated_at"] = now

    if new_round > max_loops:
        product["state"] = "FAILED"
        product["failure_reason"] = (
            f"Post-DevOps human reject exhausted repair budget ({max_loops} rounds)."
        )
        pj.parent.mkdir(parents=True, exist_ok=True)
        pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        _sync_sqlite_from_json()
        _append_human_feedback(pid, "block", notes)
        return {"ok": False, "reason": "repair_budget_exhausted"}

    product["state"] = "BUG_FOUND"
    dev_task = {
        "id": f"task-{uuid.uuid4().hex[:12]}",
        "product_id": pid,
        "agent_type": "developer",
        "state": "DEV_FIXING",
        "status": "pending",
        "retry_count": 0,
        "max_retries": 3,
        "input_data": {
            "product_id": pid,
            "idea": product.get("idea", ""),
            "human_post_devops_review": {"decision": "reject", "notes": notes[:8000]},
            "quality_gates_feedback": {
                "passed": False,
                "reasons": [f"Human post-DevOps reject: {notes[:2000]}"],
                "source": "human_post_devops_review",
            },
            "quality_repair_round": new_round,
            "quality_repair_max": max_loops,
            "qa_gate_blocked": True,
        },
        "created_at": now,
        "priority": _agent_priority("developer"),
    }
    task_queue.append(dev_task)
    data["task_queue"] = task_queue
    data["products"][pid] = product
    pj.parent.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _sync_sqlite_from_json()
    _append_human_feedback(pid, "block", notes)
    logger.warning("post_devops human reject → BUG_FOUND / DEV_FIXING for %s round %s", pid, new_round)
    return {"ok": True, "task_id": dev_task["id"], "repair_round": new_round, "state": "BUG_FOUND"}


def reject_post_devops_human_review(product_id: str, notes: str) -> dict[str, Any]:
    """Send product back to developer after operator rejects post-DevOps gate."""
    notes = (notes or "").strip()
    if len(notes) < 8:
        return {"ok": False, "reason": "notes_too_short", "min": 8}
    if _truthy("USE_SQLITE", "0") and sqlite_db_path().is_file():
        res = _reject_via_sqlite(product_id, notes)
        if res.get("reason") == "product_not_found" and pipeline_json_path().is_file():
            return _reject_via_pipeline_json(product_id, notes)
        return res
    return _reject_via_pipeline_json(product_id, notes)


def inject_human_admin_rework(product_id: str, notes: str) -> dict[str, Any]:
    """
    Move a completed product into BUG_FOUND + developer DEV_FIXING with human instructions.
    Prefers SQLite path when USE_SQLITE and DB exist and product is in DB.
    """
    notes = (notes or "").strip()
    if len(notes) < 8:
        return {"ok": False, "reason": "notes_too_short", "min": 8}

    if _truthy("USE_SQLITE", "0") and sqlite_db_path().is_file():
        res = _inject_via_sqlite(product_id, notes)
        if res.get("reason") == "product_not_found" and pipeline_json_path().is_file():
            return _inject_via_pipeline_json(product_id, notes)
        return res

    return _inject_via_pipeline_json(product_id, notes)
