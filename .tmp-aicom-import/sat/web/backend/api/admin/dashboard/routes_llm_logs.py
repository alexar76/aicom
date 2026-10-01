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
from .routes_agents import _aggregate_llm_logs_for_summary, _llm_log_sort_ts

logger = logging.getLogger(__name__)


def _load_llm_logs_page(
    *,
    limit: int,
    offset: int,
    provider: Optional[str],
    since: Optional[float],
    until: Optional[float],
) -> dict[str, Any]:
    """Sync loader for ``llm_calls.jsonl`` (run via ``asyncio.to_thread`` under pipeline load)."""
    from llm.pricing_estimate import enrich_llm_log_entry

    log_file = llm_calls_log_path()
    indexed: list[tuple[int, dict]] = []
    use_time_range = since is not None or until is not None

    if log_file.exists():
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if provider and entry.get("provider") != provider:
                        continue
                    if use_time_range:
                        ts = _llm_log_sort_ts(entry)
                        if since is not None and ts < float(since):
                            continue
                        if until is not None and ts > float(until):
                            continue
                    indexed.append((line_no, entry))
                except json.JSONDecodeError as _suppressed_exc:
                    log_suppressed(
                        logger,
                        "non-fatal (web/backend/api/admin/dashboard/routes_llm_logs.py)",
                        exc_info=_suppressed_exc,
                    )

    indexed.sort(key=lambda x: (_llm_log_sort_ts(x[1]), x[0]), reverse=True)
    logs = [e for _, e in indexed]
    summary: dict[str, Any] | None = None
    if use_time_range:
        for entry in logs:
            enrich_llm_log_entry(entry)
        summary = _aggregate_llm_logs_for_summary(logs)
        trimmed = logs[offset : offset + limit]
    else:
        window = logs[offset : offset + limit]
        for entry in window:
            enrich_llm_log_entry(entry)
        trimmed = window

    return {
        "logs": trimmed,
        "count": len(trimmed),
        "total": len(logs),
        "summary": summary,
        "offset": offset,
        "limit": limit,
    }


@router.get("/llm/logs")
async def get_llm_logs(
    limit: int = Query(100, ge=1, le=2000, description="Page size (newest-first window)."),
    offset: int = Query(0, ge=0, le=2_000_000, description="Skip this many newest-matching rows before returning a page."),
    provider: Optional[str] = Query(None),
    since: Optional[float] = Query(
        None,
        description="Inclusive range start as Unix time in seconds (e.g. from Date.now()/1000).",
    ),
    until: Optional[float] = Query(
        None,
        description="Inclusive range end as Unix time in seconds.",
    ),
):
    """Get LLM API call logs for admin visibility (newest entries first).

    Use ``offset`` + ``limit`` to page through results without loading the whole file in the browser.
    When ``since`` and/or ``until`` are set, ``summary`` aggregates **all** matching rows; ``logs`` is only
    the requested page.
    """
    limit = max(1, min(int(limit or 100), 2000))
    offset = max(0, min(int(offset or 0), 2_000_000))
    try:
        return await asyncio.to_thread(
            _load_llm_logs_page,
            limit=limit,
            offset=offset,
            provider=provider,
            since=since,
            until=until,
        )
    except Exception as exc:
        logger.exception("LLM logs load failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to load LLM logs: {exc}") from exc

