"""
Admin Dashboard API (split module).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, StreamingResponse

from core.logging_utils import log_suppressed
from core.paths import (
    architecture_json_path,
    audit_log_dir,
    benchmark_alerts_path,
    benchmark_scorecard_path,
    benchmark_status_path,
    data_root as factory_data_root,
    director_decisions_path,
    director_reports_dir,
    discovery_dir,
    escalations_log_path,
    legacy_audit_log_path,
    llm_calls_log_path,
    logs_dir,
    market_research_path,
    marketing_content_path,
    metrics_history_path,
    model_providers_path,
    pipeline_db_path,
    pipeline_json_path,
    reports_dir,
    specification_path,
)
from web.backend.core.admin_roles import AdminRole, normalize_role, rank, require_admin_with_rbac
from finance_stats import compute_dashboard_revenue
from llm.bootstrap_providers import ensure_model_providers_file
from llm.factory_defaults import FACTORY_CONTEXT_WINDOW_DEFAULT, FACTORY_MAX_OUTPUT_TOKENS_HEAVY
from web.backend.services.catalog_hardening import harden_catalog_products
from web.backend.services.product_naming import resolve_product_name
from web.backend.services.policy_audit import sync_sqlite_from_pipeline_json
from web.backend.services.human_pipeline import (
    approve_post_devops_human_review,
    inject_human_admin_rework,
    reject_post_devops_human_review,
)
from web.backend.services.pipeline_failure_report import build_failure_report
from web.backend.services.pipeline_reopen import reopen_failed_product
from web.backend.services.pipeline_failed_notify import failure_reason_from_product
from web.backend.services.product_followup import (
    normalize_pipeline_followup,
    patch_admin_decisions,
    read_followup,
    validate_and_save,
)
from web.backend.services.pipeline_demo_replay import metrics_demo_replay_slice
from web.backend.services.dashboard_metrics_cache import (
    get_cached_dashboard,
    get_or_build_dashboard,
    set_cached_dashboard,
)
from web.backend.services.storefront_counts_cache import invalidate_storefront_categories_cache
from web.backend.services.product_economics import compute_roi_band, get_product_llm_costs
from web.backend.services.factory_floor import build_factory_floor_slice
from web.backend.services.cost_outcome_heatmap import build_cost_outcome_heatmap
from web.backend.services.product_pulse import build_product_pulse, build_product_pulses_for_metrics
from web.backend.services.storefront_pricing import (
    patch_admin_storefront_usdt,
    read_sales_inner_and_pricing,
    resolve_storefront_price_usdt,
)
from web.backend.api.products import count_showcase_listable_products, is_shipped_pipeline_product_state

from ._router import router
from .models import *
from .helpers import *

@router.get("/agents")
async def get_agents():
    """Get agent status and configuration with real task counts from pipeline."""
    agents = {
        "analyst": {"status": "active", "timeout": 45, "last_active": None, "tasks_completed": 0, "current_task": None},
        "pm": {"status": "active", "timeout": 30, "last_active": None, "tasks_completed": 0, "current_task": None},
        "architect": {"status": "active", "timeout": 120, "last_active": None, "tasks_completed": 0, "current_task": None},
        "designer": {"status": "active", "timeout": 0, "last_active": None, "tasks_completed": 0, "current_task": None},
        "methodologist": {"status": "active", "timeout": 60, "last_active": None, "tasks_completed": 0, "current_task": None},
        "developer": {"status": "active", "timeout": 60, "last_active": None, "tasks_completed": 0, "current_task": None},
        "qa": {"status": "active", "timeout": 45, "last_active": None, "tasks_completed": 0, "current_task": None},
        "security": {"status": "active", "timeout": 60, "last_active": None, "tasks_completed": 0, "current_task": None},
        "devops": {"status": "active", "timeout": 60, "last_active": None, "tasks_completed": 0, "current_task": None},
        "marketing": {"status": "active", "timeout": 30, "last_active": None, "tasks_completed": 0, "current_task": None},
        "sales": {"status": "active", "timeout": 15, "last_active": None, "tasks_completed": 0, "current_task": None},
        "evolution_analyst": {"status": "active", "timeout": 90, "last_active": None, "tasks_completed": 0, "current_task": None},
    }

    # Count real completed tasks from pipeline state (SQLite when enabled, else JSON)
    def _bump_completed(task_row: dict) -> None:
        agent_type = task_row.get("agent_type", "")
        st = str(task_row.get("status") or "").strip().lower()
        if st != "completed":
            return
        if agent_type in agents:
            agents[agent_type]["tasks_completed"] += 1
        if agent_type == "architect":
            agents["designer"]["tasks_completed"] += 1

    loaded_from_sqlite = False
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            try:
                for raw in sm.get_all_tasks():
                    _bump_completed(_normalize_pipeline_task(dict(raw)))
                loaded_from_sqlite = True
            finally:
                sm.close()
        except Exception:
            logger.warning("get_agents: SQLite task counts failed, trying pipeline.json")

    if not loaded_from_sqlite:
        pipeline_path = pipeline_json_path()
        if pipeline_path.exists():
            try:
                import json as j

                with open(pipeline_path, "r") as f:
                    pipeline = j.load(f)
                for task in pipeline.get("task_queue", []):
                    _bump_completed(_normalize_pipeline_task(dict(task)))
                for pid, product in pipeline.get("products", {}).items():
                    for task in product.get("tasks", []) or []:
                        _bump_completed(_normalize_pipeline_task(dict(task)))
            except Exception:
                log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

    # Load agent logs for last_active
    log_dir = logs_dir()
    if log_dir.exists():
        for log_file in log_dir.glob("*.jsonl"):
            agent_type = log_file.stem
            if agent_type in agents:
                try:
                    with open(log_file, "r") as f:
                        lines = f.readlines()
                    if lines:
                        import json as j
                        last_entry = j.loads(lines[-1])
                        agents[agent_type]["last_active"] = last_entry.get("time")
                except Exception:
                    log_suppressed(logger, "dashboard: agent log tail read failed", exc_info=True)

    # Designer mirrors Architect telemetry (no designer.jsonl worker log)
    arch = agents.get("architect") or {}
    agents["designer"]["last_active"] = agents["designer"].get("last_active") or arch.get("last_active")
    agents["designer"]["status"] = arch.get("status") or agents["designer"].get("status") or "active"

    # Live-ish log metrics (same source as Live Monitor ``agent_metrics``)
    try:
        am = _collect_agent_metrics()
        for at, row in agents.items():
            if at not in am:
                continue
            m = am[at]
            row["log_metrics"] = {
                "total_entries": int(m.get("total_entries") or 0),
                "recent_entries": int(m.get("recent_entries") or 0),
                "recent_errors": int(m.get("recent_errors") or 0),
                "last_active": float(m.get("last_active") or 0),
                "status": str(m.get("status") or "idle"),
            }
            row["status"] = str(m.get("status") or row.get("status") or "active")
    except Exception:
        logger.warning("get_agents: log_metrics merge failed", exc_info=True)

    arch_after = agents.get("architect") or {}
    if agents.get("designer") and not agents["designer"].get("log_metrics") and arch_after.get("log_metrics"):
        agents["designer"]["log_metrics"] = dict(arch_after["log_metrics"])

    return {"agents": agents}


def _audit_entry_ts_seconds(entry: dict[str, Any]) -> float:
    raw = entry.get("timestamp", 0)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v / 1000.0 if v > 1e12 else v


@router.get("/security/logs")
async def get_security_logs(
    limit: int = Query(500, ge=1, le=5000),
    since: Optional[float] = Query(None, description="Unix seconds, inclusive lower bound"),
    until: Optional[float] = Query(None, description="Unix seconds, inclusive upper bound"),
):
    """Get security audit logs from all audit log locations."""
    entries: list[dict[str, Any]] = []

    # Check both locations:
    # 1. Legacy flat file
    legacy_file = legacy_audit_log_path()
    if legacy_file.exists():
        try:
            with open(legacy_file, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
        except Exception:
            log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

    # 2. AuditLogger directory (hash-chained format)
    audit_dir = audit_log_dir()
    if audit_dir.exists():
        for log_file in sorted(audit_dir.glob("audit-*.jsonl"), reverse=True):
            try:
                lines = log_file.read_text().strip().split("\n")
                for line in reversed(lines):
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            # AuditLogger entries have an 'action' field
                            entries.append(entry)
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
            except Exception:
                log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

    if since is not None or until is not None:
        filtered: list[dict[str, Any]] = []
        for e in entries:
            ts = _audit_entry_ts_seconds(e)
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue
            filtered.append(e)
        entries = filtered

    # Sort by timestamp descending (newest first)
    entries.sort(key=_audit_entry_ts_seconds, reverse=True)
    sliced = entries[:limit]
    return {"logs": sliced, "count": len(sliced), "total": len(entries)}


@router.get("/agent/handoffs")
async def get_agent_handoffs(
    limit: int = Query(200, ge=1, le=2000),
    since: Optional[float] = Query(None, description="Unix seconds, inclusive lower bound"),
    until: Optional[float] = Query(None, description="Unix seconds, inclusive upper bound"),
    product_id: Optional[str] = Query(None, description="Filter by pipeline product id"),
):
    """Pipeline agent-to-agent handoffs (hash-chained ``agent_handoff`` audit events)."""
    res = await get_security_logs(limit=5000, since=since, until=until)
    logs = res.get("logs") or []
    handoffs = [e for e in logs if str(e.get("action") or "") == "agent_handoff"]
    if product_id:
        pid = product_id.strip()
        filtered: list[dict[str, Any]] = []
        for e in handoffs:
            details = e.get("details") if isinstance(e.get("details"), dict) else {}
            resource = str(e.get("resource") or "")
            if details.get("product_id") == pid or resource.endswith(f"/{pid}"):
                filtered.append(e)
        handoffs = filtered
    return {"handoffs": handoffs[:limit], "count": min(len(handoffs), limit), "total": len(handoffs)}


# ── LLM Call Logs ─────────────────────────────────────────────────────────


def _llm_log_sort_ts(entry: dict) -> float:
    """Parse timestamp for sorting (newest first). Naive ISO strings are treated as UTC."""
    for key in ("timestamp", "created_at", "time"):
        t = entry.get(key)
        if t is None:
            continue
        if isinstance(t, (int, float)):
            tf = float(t)
            if tf > 1e12:  # milliseconds since epoch
                tf = tf / 1000.0
            return tf
        if isinstance(t, str) and t.strip():
            try:
                s = t.replace("Z", "+00:00") if t.endswith("Z") else t
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except (ValueError, TypeError):
                continue
    return 0.0


def _aggregate_llm_logs_for_summary(entries: list[dict]) -> dict[str, Any]:
    """Roll up costs/tokens and breakdowns for admin LLM log summary (same semantics as LLMLogsTab)."""
    sum_cost = 0.0
    with_cost = 0
    sum_prompt = 0
    sum_completion = 0
    sum_tokens = 0
    calls_in_out = 0
    by_provider: dict[str, float] = {}
    by_role: dict[str, float] = {}
    by_agent: dict[str, float] = {}

    for log in entries:
        c = log.get("estimated_cost_usd")
        if isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(float(c)):
            sum_cost += float(c)
            with_cost += 1
        p = log.get("prompt_tokens")
        co = log.get("completion_tokens")
        if isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(float(p)):
            sum_prompt += int(p)
        if isinstance(co, (int, float)) and not isinstance(co, bool) and math.isfinite(float(co)):
            sum_completion += int(co)
        tu = log.get("tokens_used")
        if isinstance(tu, (int, float)) and not isinstance(tu, bool) and math.isfinite(float(tu)):
            sum_tokens += int(tu)
        if (
            isinstance(p, (int, float))
            and not isinstance(p, bool)
            and isinstance(co, (int, float))
            and not isinstance(co, bool)
        ):
            calls_in_out += 1

        cc = float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(float(c)) else 0.0
        prov = str(log.get("provider") or "unknown")
        by_provider[prov] = by_provider.get(prov, 0.0) + cc

        role = str(log.get("model_role") or "unknown")
        by_role[role] = by_role.get(role, 0.0) + cc

        ag = str(log.get("agent_type") or "—")
        by_agent[ag] = by_agent.get(ag, 0.0) + cc

    provider_pie = [
        {"name": k, "value": v}
        for k, v in sorted(by_provider.items(), key=lambda kv: -kv[1])
        if v > 0
    ]
    role_bar = [
        {"name": k, "cost": v}
        for k, v in sorted(by_role.items(), key=lambda kv: -kv[1])
        if v > 0
    ]
    agent_bar = [
        {"name": k, "cost": v}
        for k, v in sorted(((k, v) for k, v in by_agent.items() if k != "—"), key=lambda kv: -kv[1])
        if v > 0
    ][:14]

    return {
        "estimated_cost_usd": round(sum_cost, 6),
        "calls_with_cost_estimate": with_cost,
        "prompt_tokens": sum_prompt,
        "completion_tokens": sum_completion,
        "tokens_used_sum": sum_tokens,
        "calls_with_prompt_completion_tokens": calls_in_out,
        "matching_in_range": len(entries),
        "by_provider": provider_pie,
        "by_role": role_bar,
        "by_agent": agent_bar,
    }

