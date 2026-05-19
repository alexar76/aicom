"""Live Factory Floor graph payload for admin WS / SSE metrics."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.paths import llm_calls_log_path, logs_dir
from orchestrator.pipeline_flow import pipeline_stage_agents

logger = logging.getLogger(__name__)


def _parse_log_timestamp(raw: Any) -> float:
    """Accept epoch seconds or ISO-8601 strings from llm_calls.jsonl."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    try:
        from datetime import datetime

        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return 0.0


_AGENT_LABELS: dict[str, str] = {
    "analyst": "Market Analyst",
    "pm": "Product Manager",
    "marketing": "Marketing",
    "methodologist": "Methodologist",
    "architect": "Architect",
    "designer": "Designer",
    "developer": "Developer",
    "qa": "QA",
    "security": "Security",
    "devops": "DevOps",
    "sales": "Sales",
    "evolution_analyst": "Evolution",
}


def _stage_order() -> list[str]:
    stages = pipeline_stage_agents()
    if "designer" not in stages:
        try:
            ai = stages.index("architect")
            stages = stages[: ai + 1] + ["designer"] + stages[ai + 1 :]
        except ValueError:
            stages = [*stages, "designer"]
    return stages


def _pipeline_edges() -> list[dict[str, str]]:
    order = _stage_order()
    edges: list[dict[str, str]] = []
    for i in range(len(order) - 1):
        edges.append({"from": order[i], "to": order[i + 1], "kind": "flow"})
    edges.append({"from": "qa", "to": "developer", "kind": "rework"})
    edges.append({"from": "security", "to": "developer", "kind": "rework"})
    return edges


def _tail_llm_by_agent(*, limit_per_agent: int = 3) -> dict[str, dict[str, Any]]:
    path = llm_calls_log_path()
    if not path.is_file():
        return {}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    cutoff = time.time() - 3600
    for line in reversed(lines[-8000:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_log_timestamp(row.get("timestamp") or row.get("time"))
        if ts and ts < cutoff:
            continue
        agent = str(row.get("agent_type") or "unknown")
        if len(buckets[agent]) >= limit_per_agent:
            continue
        buckets[agent].append(row)
    out: dict[str, dict[str, Any]] = {}
    for agent, rows in buckets.items():
        costs = [float(r.get("estimated_cost_usd") or 0) for r in rows]
        latencies = [float(r.get("latency_ms") or r.get("duration_ms") or 0) for r in rows if r.get("latency_ms") or r.get("duration_ms")]
        prompts = [str(r.get("prompt_preview") or r.get("task_preview") or "")[:120] for r in rows if r.get("prompt_preview") or r.get("task_preview")]
        out[agent] = {
            "provider": str(rows[0].get("provider") or rows[0].get("model_provider") or "—"),
            "model": str(rows[0].get("model") or "—"),
            "last_latency_ms": round(latencies[0], 1) if latencies else None,
            "last_cost_usd": round(costs[0], 6) if costs else 0.0,
            "calls_1h": len(rows),
            "prompt_line": prompts[0] if prompts else "",
        }
    return out


def _running_tasks_snapshot(sqlite_path: Path) -> list[dict[str, Any]]:
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(sqlite_path))
        sm.connect()
        rows = sm.conn.execute(
            """
            SELECT t.id, t.product_id, t.agent_type, t.status, t.started_at, t.created_at,
                   p.idea, p.state AS product_state
            FROM tasks t
            LEFT JOIN products p ON p.id = t.product_id AND p.workspace_id = t.workspace_id
            WHERE t.workspace_id = ?
              AND lower(trim(t.status)) IN ('running', 'pending')
            ORDER BY COALESCE(t.started_at, t.created_at) DESC
            LIMIT 40
            """,
            (sm.workspace_id,),
        ).fetchall()
        sm.close()
    except Exception:
        logger.debug("factory_floor running tasks query failed", exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {}
        if not d and isinstance(r, tuple):
            continue
        agent = str(d.get("agent_type") or "")
        out.append(
            {
                "task_id": d.get("id"),
                "product_id": d.get("product_id"),
                "agent_type": agent,
                "status": d.get("status"),
                "product_title": (str(d.get("idea") or "")[:80] or None),
                "product_state": d.get("product_state"),
                "started_at": d.get("started_at") or d.get("created_at"),
            }
        )
    return out


def _agent_log_pulse() -> dict[str, str]:
    log_dir = logs_dir()
    pulse: dict[str, str] = {}
    if not log_dir.is_dir():
        return pulse
    now = time.time()
    for log_file in sorted(log_dir.glob("*.jsonl")):
        agent = log_file.stem
        try:
            tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        except OSError:
            continue
        recent = False
        for line in reversed(tail):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = float(row.get("time") or 0)
            if ts > now - 120:
                recent = True
                break
        pulse[agent] = "active" if recent else "idle"
    return pulse


def build_factory_floor_slice(
    *,
    sqlite_path: Path,
    circuit_breakers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Graph nodes/edges + live pulses for the Factory Floor UI."""
    llm_by_agent = _tail_llm_by_agent()
    running = _running_tasks_snapshot(sqlite_path)
    log_pulse = _agent_log_pulse()

    active_by_agent: dict[str, dict[str, Any]] = {}
    for row in running:
        agent = str(row.get("agent_type") or "")
        if agent and agent not in active_by_agent:
            active_by_agent[agent] = row

    cb_providers = (circuit_breakers or {}).get("providers") or {}
    open_providers = {
        name
        for name, row in cb_providers.items()
        if str((row or {}).get("state") or "").lower() in ("open", "half_open")
    }

    nodes: list[dict[str, Any]] = []
    stage_order = _stage_order()
    for agent in stage_order:
        llm = llm_by_agent.get(agent) or {}
        active = active_by_agent.get(agent)
        pulse = log_pulse.get(agent, "idle")
        if active:
            status = "running"
        elif pulse == "active":
            status = "thinking"
        else:
            status = "idle"

        provider = llm.get("provider") or "—"
        circuit_tripped = any(p.lower() in provider.lower() for p in open_providers) if provider != "—" else False
        if not circuit_tripped and open_providers and llm.get("provider"):
            for pname in open_providers:
                if pname.split("_")[0] in str(llm.get("provider", "")).lower():
                    circuit_tripped = True
                    break

        nodes.append(
            {
                "id": agent,
                "label": _AGENT_LABELS.get(agent, agent.title()),
                "status": status,
                "prompt_line": (active and active.get("product_title")) or llm.get("prompt_line") or "",
                "provider": provider,
                "model": llm.get("model") or "—",
                "latency_ms": llm.get("last_latency_ms"),
                "cost_usd": llm.get("last_cost_usd"),
                "product_id": active.get("product_id") if active else None,
                "circuit_tripped": circuit_tripped,
            }
        )

    hot_edges: list[dict[str, str]] = []
    for i, row in enumerate(running[:8]):
        agent = str(row.get("agent_type") or "")
        if not agent:
            continue
        idx = stage_order.index(agent) if agent in stage_order else -1
        if idx > 0:
            hot_edges.append({"from": stage_order[idx - 1], "to": agent, "pulse_id": f"pulse-{i}"})

    return {
        "nodes": nodes,
        "edges": _pipeline_edges(),
        "hot_edges": hot_edges,
        "running_count": len(running),
        "open_circuits": sorted(open_providers),
        "updated_at": time.time(),
    }
