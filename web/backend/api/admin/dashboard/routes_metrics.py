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
    pipeline_db_path,
    pipeline_json_path,
    reports_dir,
    specification_path,
)
from web.backend.core.admin_roles import AdminRole, normalize_role, rank, require_admin_with_rbac
from finance_stats import compute_dashboard_revenue
from product_pnl import compute_product_pnl
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
from .helpers import (
    METRICS_HISTORY_FILE,
    _append_metrics_history,
    _build_degraded_dashboard_metrics,
    _build_full_metrics_async,
    _build_quick_dashboard_metrics,
    get_live_metrics_stream_payload,
)

logger = logging.getLogger(__name__)


@router.get("/dashboard/pipeline-summary")
async def get_dashboard_pipeline_summary(_admin: dict = Depends(require_admin_with_rbac)):
    """
    Fast pipeline totals — same SQL as Pipeline Monitor ``catalog_summary`` (one query).
    Use for dashboard first paint when the full dashboard payload is slow or contended.
    """
    _ = _admin

    def _build() -> dict[str, Any]:
        from orchestrator.sqlite_manager import SQLiteManager

        from core.paths import pipeline_db_path

        db = pipeline_db_path()
        if not db.is_file():
            return {
                "total_products": 0,
                "active_products": 0,
                "completed_products": 0,
                "failed_products": 0,
                "pending_tasks": 0,
                "running_tasks": 0,
                "timed_out_tasks": 0,
            }
        sm = SQLiteManager(str(db))
        sm.connect()
        try:
            counts = sm.get_catalog_summary_counts()
            m = sm.get_metrics()
        finally:
            sm.close()
        total = int(counts["total"])
        shipped = int(counts["shipped"])
        failed = int(counts["failed"])
        active = max(0, total - shipped - failed)
        return {
            "total_products": total,
            "active_products": active,
            "completed_products": shipped,
            "failed_products": failed,
            "pending_tasks": int(m.get("pending_tasks") or 0),
            "running_tasks": int(m.get("running_tasks") or 0),
            "timed_out_tasks": int(m.get("timeout_tasks") or 0),
        }

    return await asyncio.to_thread(_build)


@router.get("/finance/product-pnl")
async def get_product_pnl(_admin: dict = Depends(require_admin_with_rbac)):
    """
    Live per-product P&L (unit economics): revenue, inference COGS, gross margin,
    ROI and cost-recovery per product, plus a portfolio rollup. Read-only — joins
    paid orders (commerce.db) with accumulated per-product LLM spend.
    """
    _ = _admin
    return await asyncio.to_thread(compute_product_pnl)


@router.get("/dashboard")
async def get_dashboard(
    background_tasks: BackgroundTasks,
    quick: bool = Query(
        False,
        description="Fast first paint: skip storefront listing scan and heavy agent/escalation reads",
    ),
):
    """Get enhanced dashboard metrics including agent_metrics, director_status, escalations."""
    if quick:
        try:
            return await asyncio.to_thread(
                lambda: get_or_build_dashboard(_build_quick_dashboard_metrics, quick=True),
            )
        except Exception as exc:
            logger.exception("Quick dashboard build failed, using degraded snapshot: %s", exc)
            return _build_degraded_dashboard_metrics()
    cached = get_cached_dashboard(quick=False)
    if cached is not None:
        metrics = cached
    else:
        try:
            metrics = await _build_full_metrics_async(include_product_pulses=False)
            set_cached_dashboard(metrics, quick=False)
        except Exception as exc:
            logger.exception("Full dashboard metrics build failed: %s", exc)
            metrics = _build_quick_dashboard_metrics()
            metrics = dict(metrics)
            metrics["dashboard_partial"] = True
            metrics["dashboard_build_degraded"] = True
            try:
                sf = count_showcase_listable_products()
                if sf is not None:
                    metrics["pipeline"] = dict(metrics.get("pipeline") or {})
                    metrics["pipeline"]["storefront_visible_products"] = sf
            except Exception as sf_exc:
                logger.warning("Storefront count during dashboard fallback failed: %s", sf_exc)
            set_cached_dashboard(metrics, quick=False)
    background_tasks.add_task(_append_metrics_history, metrics)
    out = dict(metrics)
    out["dashboard_partial"] = False
    return out


# ── SSE Metrics Stream ──────────────────────────────────────────────────────


@router.get("/metrics/stream")
async def metrics_stream(request: Request):
    """SSE endpoint that pushes full metrics payload every 5 seconds."""
    async def event_generator():
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            try:
                metrics = await get_live_metrics_stream_payload()
                _append_metrics_history(metrics)
                yield f"data: {json.dumps(metrics)}\n\n"
            except Exception as e:
                logger.error(f"SSE metrics error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Escalation Logs ─────────────────────────────────────────────────────────


@router.get("/escalations")
async def get_escalations(limit: int = 50):
    """Get recent escalation events (failures, timeouts, bypasses)."""
    log_file = escalations_log_path()
    entries = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to read escalation log")

    return {"escalations": entries[-limit:], "count": min(len(entries), limit), "total": len(entries)}


# ── Metrics History ──────────────────────────────────────────────────────────


@router.get("/metrics/history")
async def get_metrics_history(limit: int = 100):
    """Get historical metrics snapshots (rolling 24h window)."""
    log_file = Path(METRICS_HISTORY_FILE)
    entries = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to read metrics history")

    return {"metrics": entries[-limit:], "count": min(len(entries), limit), "total": len(entries)}


# ── Director Decisions ──────────────────────────────────────────────────────


DECISIONS_FILE = str(director_decisions_path())


