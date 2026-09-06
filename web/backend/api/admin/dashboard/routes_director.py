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

def _load_decisions() -> dict:
    """Load decisions from file.

    The path comes from ``core.paths`` on every call rather than a module constant. When this
    package was split, ``DECISIONS_FILE`` stayed behind in ``routes_metrics`` and this module
    kept using the bare name — so every ``GET /director/decisions`` raised
    ``NameError: name 'DECISIONS_FILE' is not defined`` and answered 500, and ``_save_decisions``
    would have done the same to the write path. The two ``import *`` lines above are why no
    linter caught it: pyflakes stops reporting undefined names once a star import is present.
    """
    path = director_decisions_path()
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)
    return {"pending": [], "applied": []}


def _save_decisions(data: dict):
    """Save decisions to file."""
    path = director_decisions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


@router.get("/director/decisions")
async def get_director_decisions():
    """Get all Director AI decisions (pending + applied)."""
    data = _load_decisions()
    all_decisions = data.get("applied", []) + data.get("pending", [])
    all_decisions.sort(key=lambda d: d.get("applied_at", 0) or d.get("created_at", 0), reverse=True)
    return {
        "pending": data.get("pending", []),
        "applied": data.get("applied", []),
        "all": all_decisions[:50],
        "pending_count": len(data.get("pending", [])),
        "total_count": len(all_decisions),
    }


@router.post("/director/decisions/{decision_id}/approve")
async def approve_decision(decision_id: str):
    """Approve a pending Director AI decision."""
    data = _load_decisions()
    for i, d in enumerate(data.get("pending", [])):
        if d.get("id") == decision_id:
            decision = data["pending"].pop(i)
            decision["status"] = "approved"
            decision["approved_at"] = time.time()
            data.setdefault("applied", []).append(decision)
            _save_decisions(data)
            return {"status": "approved", "decision": decision}
    raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found in pending")


@router.post("/director/decisions/{decision_id}/reject")
async def reject_decision(decision_id: str):
    """Reject a pending Director AI decision."""
    data = _load_decisions()
    for i, d in enumerate(data.get("pending", [])):
        if d.get("id") == decision_id:
            decision = data["pending"].pop(i)
            decision["status"] = "rejected"
            decision["rejected_at"] = time.time()
            data.setdefault("applied", []).append(decision)
            _save_decisions(data)
            return {"status": "rejected", "decision": decision}
    raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found in pending")

