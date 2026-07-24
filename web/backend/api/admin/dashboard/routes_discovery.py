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

@router.get("/discovery/ideas")
async def get_discovery_ideas(limit: int = 20):
    """Read latest ranked discovery opportunities for admin Idea Queue UI."""
    ranked_file = discovery_dir() / "ranked_ideas.json"
    if not ranked_file.exists():
        return {"generated_at": None, "ranked_ideas": [], "count": 0, "signals_total": 0}
    try:
        payload = json.loads(ranked_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read discovery ideas: {exc}")
    ideas = payload.get("ranked_ideas") if isinstance(payload.get("ranked_ideas"), list) else []
    n = max(1, min(int(limit), 100))
    source_health = {}
    source_health_file = discovery_dir() / "source_health.json"
    if source_health_file.exists():
        try:
            source_health = json.loads(source_health_file.read_text(encoding="utf-8"))
        except Exception:
            source_health = {}
    return {
        "generated_at": payload.get("generated_at"),
        "signals_total": payload.get("signals_total", 0),
        "signals_collected_now": payload.get("signals_collected_now", 0),
        "signal_pruning": payload.get("signal_pruning", {}),
        "source_health": source_health,
        "anomaly": payload.get("anomaly"),
        "ranked_ideas": ideas[:n],
        "count": min(len(ideas), n),
    }


@router.get("/benchmark/scorecard")
async def get_benchmark_scorecard():
    """Get latest benchmark scorecard + alerts produced by regression league."""
    scorecard_path = benchmark_scorecard_path()
    alerts_path = benchmark_alerts_path()
    scorecard = {}
    alerts = []
    if scorecard_path.exists():
        try:
            scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
        except Exception:
            scorecard = {}
    if alerts_path.exists():
        try:
            payload = json.loads(alerts_path.read_text(encoding="utf-8"))
            alerts = payload.get("alerts") or []
        except Exception:
            alerts = []
    status = {}
    status_path = benchmark_status_path()
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    investor = _build_investor_passrate_metrics(scorecard)
    return {"scorecard": scorecard, "alerts": alerts, "status": status, "investor_metrics": investor}


def _build_investor_passrate_metrics(scorecard: dict) -> dict[str, Any]:
    p24 = scorecard.get("pass_rate_last_24h_avg")
    p7 = scorecard.get("pass_rate_last_7d_avg")
    latest = (scorecard.get("latest") or {}).get("pass_rate")
    def _f(x: Any) -> float:
        try:
            return float(x)
        except Exception:
            return 0.0
    p24f = _f(p24)
    p7f = _f(p7)
    latestf = _f(latest)
    trend = round(latestf - p7f, 3)
    n = int(scorecard.get("runs_last_7d") or 0)
    # Approximate CI for Bernoulli proportion from pass-rate.
    ci_half = 0.0
    if n > 0:
        ci_half = 1.96 * math.sqrt(max(p7f * (1.0 - p7f), 0.0) / n)
    ci_low = max(0.0, round(p7f - ci_half, 3))
    ci_high = min(1.0, round(p7f + ci_half, 3))
    readiness_index = round(
        max(0.0, min(1.0, 0.45 * latestf + 0.45 * p7f + 0.10 * p24f)),
        3,
    )
    return {
        "rolling_24h_pass_rate": round(p24f, 3) if p24 is not None else None,
        "rolling_7d_pass_rate": round(p7f, 3) if p7 is not None else None,
        "latest_pass_rate": round(latestf, 3) if latest is not None else None,
        "trend_vs_7d": trend,
        "confidence_interval_95": {"low": ci_low, "high": ci_high, "n": n},
        "production_readiness_index": readiness_index,
    }


def _read_spec_inner(product_id: str) -> dict[str, Any] | None:
    spec_path = specification_path(product_id)
    if not spec_path.exists():
        return None
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = raw.get("specification")
        return spec if isinstance(spec, dict) else None
    except Exception:
        return None


def _write_spec_name(product_id: str, new_name: str) -> bool:
    spec_path = specification_path(product_id)
    if not spec_path.exists():
        return False
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        spec = raw.get("specification")
        if not isinstance(spec, dict):
            return False
        spec["product_name"] = new_name
        raw["specification"] = spec
        spec_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _read_marketing_inner(product_id: str) -> dict[str, Any] | None:
    mkt_path = marketing_content_path(product_id)
    if not mkt_path.exists():
        return None
    try:
        raw = json.loads(mkt_path.read_text(encoding="utf-8"))
        m = raw.get("marketing")
        return m if isinstance(m, dict) else None
    except Exception:
        return None


def _write_marketing_name(product_id: str, new_name: str) -> bool:
    mkt_path = marketing_content_path(product_id)
    if not mkt_path.exists():
        return False
    try:
        raw = json.loads(mkt_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        marketing = raw.get("marketing")
        if not isinstance(marketing, dict):
            marketing = {}
        marketing["product_name"] = new_name
        raw["marketing"] = marketing
        mkt_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


@router.post("/products/rename-now")
async def rename_existing_catalog_products():
    """
    Mass-rename existing catalog products to unique, marketable names.
    Persists names in specs/marketing artifacts (not only runtime API response).
    """
    products, _tasks = _load_pipeline_snapshot_for_metrics()
    used_names: set[str] = set()
    results: list[dict[str, Any]] = []

    for product_id, product in products.items():
        state = str((product or {}).get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue
        if not isinstance(product, dict):
            continue

        spec_inner = _read_spec_inner(product_id)
        marketing_inner = _read_marketing_inner(product_id)
        resolved_name, is_template = resolve_product_name(
            product_id=product_id,
            product=product,
            spec=spec_inner,
            marketing=marketing_inner,
            used_names=used_names,
        )
        spec_written = _write_spec_name(product_id, resolved_name)
        marketing_written = _write_marketing_name(product_id, resolved_name)
        results.append(
            {
                "product_id": product_id,
                "name": resolved_name,
                "is_template": is_template,
                "spec_updated": spec_written,
                "marketing_updated": marketing_written,
            }
        )

    return {
        "status": "ok",
        "renamed_count": len(results),
        "products": results,
    }


def _read_pipeline_state() -> dict[str, Any]:
    from core.pipeline_state_writer import read_pipeline_state

    return read_pipeline_state()


def _write_pipeline_state(state: dict[str, Any]) -> bool:
    from core.pipeline_state_writer import write_pipeline_state

    return write_pipeline_state(state)

