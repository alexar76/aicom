"""
Feedback guardrail audit
========================
Escalates shipped products back into PM rework when real-user feedback degrades.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _load_recent_feedback(window_hours: int) -> list[dict[str, Any]]:
    fb_dir = Path("/app/data/feedback")
    if not fb_dir.exists():
        return []
    cutoff = time.time() - (window_hours * 3600)
    rows: list[dict[str, Any]] = []
    for p in sorted(fb_dir.glob("fb-*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if float(row.get("created_at") or 0) < cutoff:
            continue
        rows.append(row)
    return rows


def _active_pm_task_exists(task_queue: list[dict[str, Any]], pid: str) -> bool:
    return any(
        t.get("product_id") == pid
        and t.get("agent_type") == "pm"
        and t.get("status") in ("pending", "running")
        for t in task_queue
    )


def apply_feedback_guardrail(products: dict[str, Any], task_queue: list[dict[str, Any]], now: float) -> bool:
    """
    If user sentiment degrades for shipped products, force a PM rework cycle.

    Trigger criteria (24h defaults):
    - journey_prompt negative votes (tag == "no") >= threshold
    - bug-class feedback count >= threshold
    """
    if not _truthy("AIFACTORY_FEEDBACK_GUARDRAIL_ENABLED", "1"):
        return False

    window_h = _env_int("AIFACTORY_FEEDBACK_GUARDRAIL_WINDOW_HOURS", 24)
    neg_threshold = _env_int("AIFACTORY_FEEDBACK_NEGATIVE_THRESHOLD", 3)
    bug_threshold = _env_int("AIFACTORY_FEEDBACK_BUG_THRESHOLD", 3)
    rows = _load_recent_feedback(window_h)
    if not rows:
        return False

    by_product: dict[str, dict[str, int]] = {}
    for r in rows:
        pid = str(r.get("product_id") or "")
        if not pid.startswith("prod-"):
            continue
        stats = by_product.setdefault(pid, {"negative": 0, "bugs": 0, "total": 0})
        stats["total"] += 1
        if str(r.get("classification") or "") == "bug":
            stats["bugs"] += 1
        tags = r.get("tags") if isinstance(r.get("tags"), list) else []
        if "journey_prompt" in tags and "no" in tags:
            stats["negative"] += 1

    changed = False
    terminal = {"COMPLETED", "DEPLOYED_PRODUCTION"}
    for pid, st in by_product.items():
        p = products.get(pid)
        if not isinstance(p, dict):
            continue
        if str(p.get("state") or "").upper() not in terminal:
            continue
        if st["negative"] < neg_threshold and st["bugs"] < bug_threshold:
            continue
        if _active_pm_task_exists(task_queue, pid):
            continue

        # Mark product as needing rework and enqueue PM rewrite from real user signals.
        p["state"] = "MARKET_RESEARCHED"
        p["updated_at"] = now
        p["feedback_guardrail"] = {
            "window_hours": window_h,
            "negative_journey_votes": st["negative"],
            "bug_reports": st["bugs"],
            "total_feedback_items": st["total"],
            "triggered_at": now,
        }
        task_queue.append(
            {
                "id": f"task-{uuid.uuid4().hex[:12]}",
                "product_id": pid,
                "agent_type": "pm",
                "state": "SPEC_WRITTEN",
                "status": "pending",
                "retry_count": 0,
                "max_retries": 3,
                "input_data": {
                    "product_id": pid,
                    "idea": p.get("idea", ""),
                    "admin_instructions": (
                        "Feedback guardrail triggered. Rework the product specification using real user pain signals. "
                        "Then pipeline must pass architecture, development, hardening, QA, and constitution again."
                    ),
                    "feedback_guardrail": p["feedback_guardrail"],
                },
                "created_at": now,
                "priority": 2,
                "auto_requeue_reason": "feedback_guardrail",
            }
        )
        changed = True
    return changed

