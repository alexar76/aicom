"""Time-travel replay timeline built from SQLite task history."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def _snippet(val: Any, limit: int = 400) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.strip()
    else:
        try:
            s = json.dumps(val, ensure_ascii=False)[: limit * 2]
        except (TypeError, ValueError):
            s = str(val)
    return s[:limit] + ("…" if len(s) > limit else "")


def _task_cost_usd(task: dict[str, Any]) -> float | None:
    metrics = task.get("metrics") or task.get("output_data") or {}
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except json.JSONDecodeError:
            metrics = {}
    if not isinstance(metrics, dict):
        return None
    for key in ("estimated_cost_usd", "llm_cost_usd", "cost_usd"):
        v = metrics.get(key)
        if v is not None:
            try:
                return round(float(v), 6)
            except (TypeError, ValueError):
                pass
    return None


def build_replay_timeline(sm: Any, product_id: str) -> dict[str, Any]:
    product = sm.get_product(product_id)
    if not product:
        return {"product_id": product_id, "frames": [], "error": "product_not_found"}

    tasks = sm.get_tasks_by_product(product_id) or []
    tasks_sorted = sorted(tasks, key=lambda t: float(t.get("created_at") or t.get("started_at") or 0))

    frames: list[dict[str, Any]] = []
    cumulative_cost = 0.0
    for i, task in enumerate(tasks_sorted):
        cost = _task_cost_usd(task) or 0.0
        cumulative_cost += cost
        started = float(task.get("started_at") or task.get("created_at") or 0)
        completed = float(task.get("completed_at") or 0)
        duration_sec = (completed - started) if completed and started else None
        inp = task.get("input_data") or task.get("input") or {}
        out = task.get("output_data") or task.get("output") or {}
        frames.append(
            {
                "index": i,
                "task_id": task.get("id"),
                "agent_type": task.get("agent_type"),
                "status": task.get("status"),
                "state_before": task.get("state"),
                "state_after": task.get("state_after"),
                "started_at": started,
                "completed_at": completed or None,
                "duration_sec": round(duration_sec, 2) if duration_sec is not None else None,
                "cost_usd": cost,
                "cumulative_cost_usd": round(cumulative_cost, 6),
                "input_preview": _snippet(inp if isinstance(inp, (dict, list, str)) else inp),
                "output_preview": _snippet(out if isinstance(out, (dict, list, str)) else out),
                "error": _snippet(task.get("error"), 200) if task.get("error") else None,
            }
        )

    return {
        "product_id": product_id,
        "product_title": _snippet(product.get("idea") or product.get("name"), 120),
        "product_state": product.get("state"),
        "frame_count": len(frames),
        "total_cost_usd": round(cumulative_cost, 6),
        "frames": frames,
        "generated_at": time.time(),
    }


def fork_replay_from_frame(
    sm: Any,
    product_id: str,
    *,
    frame_index: int,
    operator_notes: str = "",
    model_override: str | None = None,
) -> dict[str, Any]:
    timeline = build_replay_timeline(sm, product_id)
    frames = timeline.get("frames") or []
    if not frames:
        raise ValueError("no_frames")
    idx = max(0, min(int(frame_index), len(frames) - 1))
    frame = frames[idx]
    agent_type = str(frame.get("agent_type") or "pm")
    target_state = str(frame.get("state_before") or product.get("state") or "IDEA_RECEIVED")

    product = sm.get_product(product_id) or {}
    product = dict(product)
    product["state"] = target_state
    product["failure_reason"] = None
    sm.upsert_product(product)

    import uuid

    task_id = f"task-fork-{uuid.uuid4().hex[:12]}"
    payload = {
        "id": task_id,
        "product_id": product_id,
        "agent_type": agent_type,
        "status": "pending",
        "state": target_state,
        "priority": 10,
        "created_at": time.time(),
        "input_data": {
            "fork_from_frame": idx,
            "fork_from_task": frame.get("task_id"),
            "operator_notes": operator_notes[:2000],
            "model_override": model_override,
            "replay_fork": True,
        },
    }
    sm.upsert_task(payload)
    return {
        "status": "fork_queued",
        "product_id": product_id,
        "frame_index": idx,
        "agent_type": agent_type,
        "target_state": target_state,
        "task_id": task_id,
    }
