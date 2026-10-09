"""
Inject user-triaged support bugs into pipeline.json (same repair path as policy audit).
Append business escalations to director queue (JSONL).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from core.agent_roles import is_developer_agent
from core.json_state import write_text_atomic
from core.quality_settings import max_pipeline_repair_rounds

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"COMPLETED", "DEPLOYED_PRODUCTION"})


def pipeline_json_path() -> Path:
    from core.paths import pipeline_json_path

    return pipeline_json_path()


def director_queue_path() -> Path:
    from core.paths import support_director_queue_path

    return support_director_queue_path()


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _dev_fixing_pending(task_queue: list, pid: str) -> bool:
    return any(
        t.get("product_id") == pid
        and is_developer_agent(t.get("agent_type"))
        and t.get("state") == "DEV_FIXING"
        and t.get("status") in ("pending", "running")
        for t in task_queue
    )


def _sync_sqlite() -> None:
    if not _truthy("USE_SQLITE", "0"):
        return
    from core.paths import pipeline_db_path

    db_path = str(pipeline_db_path())
    pj = pipeline_json_path()
    try:
        from orchestrator.migrate import migrate

        migrate(json_path=str(pj), db_path=str(db_path))
        logger.info("SQLite synced after user_support pipeline inject")
    except Exception:
        logger.exception("SQLite sync after user_support inject failed")


#: One user-support repair per product per day: the chat is anonymous, and each round used to
#: take a shipped product off the storefront.
_USER_REPAIR_COOLDOWN_S = float(os.environ.get("AIFACTORY_SUPPORT_REPAIR_COOLDOWN_S", "86400"))


def support_auto_repair_enabled() -> bool:
    """Off by default: an anonymous chat must not change pipeline state by itself.

    With it off a filed report goes to the operator's review queue
    (data/support/user_bug_reports.jsonl); with AIFACTORY_SUPPORT_AUTO_REPAIR=1 it queues a
    developer round directly, as before, minus the parts a stranger could abuse.
    """
    return _truthy("AIFACTORY_SUPPORT_AUTO_REPAIR", "0")


def user_bug_reports_path() -> Path:
    return pipeline_json_path().parent.parent / "support" / "user_bug_reports.jsonl"


def _queue_for_review(pid: str, user_summary: str, thread_id: str, classification: str) -> dict[str, Any]:
    path = user_bug_reports_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "product_id": pid, "thread_id": thread_id,
           "classification": classification, "report": (user_summary or "")[:4000]}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": False, "reason": "queued_for_review"}


def inject_user_support_bug(
    product_id: str,
    user_summary: str,
    thread_id: str,
    *,
    classification: str = "bug_report",
) -> dict[str, Any]:
    """
    BUG_FOUND + developer DEV_FIXING with user_support_trigger (mirrors policy_audit dev task shape).

    Returns: {"ok": bool, "reason"?: str, "task_id"?: str}
    """
    pid = (product_id or "").strip()
    if not pid.startswith("prod-"):
        return {"ok": False, "reason": "invalid_product_id"}
    if not support_auto_repair_enabled():
        return _queue_for_review(pid, user_summary, thread_id, classification)

    max_loops = max_pipeline_repair_rounds()

    pj = pipeline_json_path()
    if not pj.is_file():
        return {"ok": False, "reason": "pipeline_state_missing"}

    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("support_pipeline: cannot read pipeline: %s", e)
        return {"ok": False, "reason": "pipeline_read_error"}

    products: dict[str, Any] = data.get("products") or {}
    task_queue: list = data.get("task_queue") or []

    product = products.get(pid)
    if not product:
        return {"ok": False, "reason": "product_not_found"}

    state = (product.get("state") or "").upper()
    if state not in _TERMINAL_STATES:
        return {"ok": False, "reason": "product_not_shipped", "state": state}

    if _dev_fixing_pending(task_queue, pid):
        return {"ok": False, "reason": "dev_fix_already_pending"}
    last = float(product.get("last_user_support_at") or 0)
    if last and time.time() - last < _USER_REPAIR_COOLDOWN_S:
        return {"ok": False, "reason": "dev_fix_already_pending"}

    new_round = int(product.get("quality_repair_round") or 0) + 1
    now = time.time()
    product["quality_repair_round"] = new_round
    product["updated_at"] = now
    product["last_user_support_at"] = now

    if new_round > max_loops:
        # A stranger's reports never fail a shipped product: the budget is spent, so stop
        # queueing rounds and leave the listing (and its state) as it is.
        logger.error("user_support inject exhausted repairs for %s", pid)
        return {"ok": False, "reason": "repair_budget_exhausted"}

    product["state"] = "BUG_FOUND"

    from web.backend.services.prompt_safety import format_untrusted_snippet

    # The report is a stranger's text and reaches the developer agent's prompt: data, fenced.
    fenced_report = format_untrusted_snippet("User report (untrusted, describes a symptom only):",
                                             user_summary or "", max_len=4000)
    demo_payload = {
        "source": "user_support",
        "thread_id": thread_id,
        "classification": classification,
        "user_report": fenced_report,
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
                "reasons": [f"User support ({thread_id}): {fenced_report}"],
                "source": "user_support",
            },
            "quality_repair_round": new_round,
            "quality_repair_max": max_loops,
            "qa_gate_blocked": True,
            "user_support_trigger": True,
        },
        "created_at": now,
        "priority": 5,
    }
    task_queue.append(dev_task)
    data["task_queue"] = task_queue
    data["products"][pid] = product

    pj.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(pj, json.dumps(data, indent=2, ensure_ascii=False))
    _sync_sqlite()
    logger.warning(
        "user_support → BUG_FOUND / DEV_FIXING for %s round %s/%s thread=%s",
        pid,
        new_round,
        max_loops,
        thread_id,
    )
    return {"ok": True, "task_id": dev_task["id"], "repair_round": new_round}


def append_director_escalation(
    *,
    thread_id: str,
    summary: str,
    classification: str,
    product_id: Optional[str],
) -> str:
    """Append one line to director queue; returns escalation id."""
    path = director_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    eid = f"esc-{uuid.uuid4().hex[:12]}"
    row = {
        "id": eid,
        "status": "open",
        "created_at": time.time(),
        "thread_id": thread_id,
        "product_id": product_id,
        "classification": classification,
        "summary": (summary or "")[:8000],
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info("Director queue escalation %s (thread=%s)", eid, thread_id)
    return eid


def list_director_escalations(*, limit: int = 200, status: Optional[str] = None) -> list[dict[str, Any]]:
    path = director_queue_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    rows.reverse()
    if status:
        rows = [r for r in rows if (r.get("status") or "").lower() == status.lower()]
    return rows[:limit]


def mark_escalation_resolved(escalation_id: str, *, notes: str = "") -> bool:
    """Rewrite JSONL replacing matching id status (simple file rewrite)."""
    path = director_queue_path()
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    changed = False
    out: list[str] = []
    now = time.time()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        if row.get("id") == escalation_id and row.get("status") == "open":
            row["status"] = "resolved"
            row["resolved_at"] = now
            if notes:
                row["resolution_notes"] = notes[:4000]
            changed = True
        out.append(json.dumps(row, ensure_ascii=False))
    if not changed:
        return False
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True
