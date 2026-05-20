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

@router.get("/director/reports")
async def get_director_reports():
    """Get Director AI reports list."""
    reports_dir = director_reports_dir()
    reports = []
    
    if reports_dir.exists():
        for report_file in sorted(reports_dir.glob("*.md"), reverse=True)[:20]:
            stat = report_file.stat()
            reports.append({
                "filename": report_file.name,
                "created_at": stat.st_mtime,
                "size": stat.st_size,
            })

    return {"reports": reports}


@router.get("/director/report/{filename}")
async def get_director_report(filename: str):
    """Get a specific Director AI report."""
    report_file = director_reports_dir() / filename
    if not report_file.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    
    with open(report_file, "r") as f:
        content = f.read()
    
    return {"filename": filename, "content": content}


# ── Developer handoff (what the Developer agent receives) ──────────────────


def _load_analyst_brief_for_developer(product_id: str) -> str:
    """Analyst-authored handoff in state/{id}/market_research.json (same as DeveloperAgent)."""
    path = market_research_path(product_id)
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    inner = raw.get("market_research")
    if isinstance(inner, dict):
        text = inner.get("developer_investigation_brief")
    else:
        text = raw.get("developer_investigation_brief")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


def _admin_merged_pipeline_product(product_id: str) -> Optional[dict]:
    """Merge pipeline.json shell with SQLite row when USE_SQLITE is on."""
    pipeline_file = pipeline_json_path()
    pj: dict = {}
    if pipeline_file.exists():
        try:
            with open(pipeline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = (data.get("products") or {}).get(product_id)
            if isinstance(raw, dict):
                pj = raw
        except (json.JSONDecodeError, OSError):
            pj = {}

    row: Optional[dict] = None
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            row = sm.get_product(product_id)
            sm.close()
        except Exception as e:
            logger.debug("admin merged product: SQLite get_product failed: %s", e)

    if not pj and not row:
        return None

    out: dict = dict(pj)
    if row:
        for k in ("id", "idea", "state", "created_at", "updated_at"):
            if row.get(k) is not None:
                out[k] = row[k]
        meta = row.get("metadata") or {}
        if isinstance(meta, dict) and meta:
            om = out.get("metadata")
            if not isinstance(om, dict):
                om = {}
            out["metadata"] = {**om, **meta}
    return out


def _load_spec_arch_from_disk(product_id: str) -> tuple[Optional[dict], Optional[dict]]:
    spec: Optional[dict] = None
    arch: Optional[dict] = None
    spec_file = specification_path(product_id)
    if spec_file.exists():
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            spec = None
    arch_file = architecture_json_path(product_id)
    if arch_file.exists():
        try:
            arch = json.loads(arch_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            arch = None
    return spec, arch


def _compute_material_summary(
    *,
    spec: Optional[dict],
    arch: Optional[dict],
    admin_instructions: str,
    brief: str,
    idea: str,
    delivery_mode: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    s = spec if isinstance(spec, dict) else None
    a = arch if isinstance(arch, dict) else None

    spec_missing = s is None or len(s) == 0
    arch_missing = a is None or len(a) == 0

    if spec_missing:
        warnings.append("Specification missing or empty — developer prompt has little PM detail.")
    if arch_missing:
        warnings.append("Architecture missing or empty — developer has no structural blueprint.")

    desc = ""
    if s:
        desc = str(s.get("description") or "").strip()
    desc_len = len(desc)
    core_features = s.get("core_features") if s else None
    n_core = len(core_features) if isinstance(core_features, list) else 0
    stories = s.get("user_stories") if s else None
    n_stories = len(stories) if isinstance(stories, list) else 0

    admin_s = (admin_instructions or "").strip()
    admin_len = len(admin_s)
    brief_s = (brief or "").strip()
    brief_len = len(brief_s)
    idea_len = len((idea or "").strip())

    if s and not spec_missing:
        if n_core == 0:
            warnings.append("No core_features in specification — scope is vague for implementation.")
        if desc_len > 0 and desc_len < 120:
            warnings.append("Product description is very short — positioning and UX intent may be unclear.")
        if n_stories == 0:
            warnings.append("No user_stories in specification — acceptance criteria are thin.")

    if admin_len > 0 and admin_len < 40:
        warnings.append("Admin instructions are very short — delivery constraints may be underspecified.")

    if delivery_mode == "web_app" and brief_len == 0:
        warnings.append(
            "Web delivery mode: analyst developer_investigation_brief is empty — "
            "developer will not receive the investigator handoff block."
        )

    if idea_len > 0 and idea_len < 30:
        warnings.append("Original idea text is very short — charter context for the developer is minimal.")

    arch_chars = len(json.dumps(a, ensure_ascii=False)) if a else 0
    spec_chars = len(json.dumps(s, ensure_ascii=False)) if s else 0

    if spec_missing or arch_missing:
        band = "weak"
    elif n_core == 0 or desc_len < 80 or (admin_len > 0 and admin_len < 40) or (delivery_mode == "web_app" and brief_len == 0):
        band = "thin"
    else:
        band = "ok"

    return {
        "quality_band": band,
        "warnings": warnings,
        "stats": {
            "spec_chars": spec_chars,
            "architecture_chars": arch_chars,
            "admin_chars": admin_len,
            "brief_chars": brief_len,
            "idea_chars": idea_len,
            "description_chars": desc_len,
            "core_features_count": n_core,
            "user_stories_count": n_stories,
        },
    }

