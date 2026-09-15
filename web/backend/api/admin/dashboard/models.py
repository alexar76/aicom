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
class StorefrontFollowupPatch(BaseModel):
    """Manual pipeline note: planned rework toward storefront vs explicitly not pursuing."""

    followup: Optional[Literal["planned", "not_pursuing"]] = None
    planned_notes: Optional[str] = Field(None, max_length=8000)
    not_pursuing_reason: Optional[str] = Field(None, max_length=8000)
    improvement_on_hold: Optional[bool] = None
    pipeline_on_hold: Optional[bool] = None


class PipelineFocusModeBody(BaseModel):
    """Focus factory on one product; pause pipeline work on all others."""

    focus_product_id: Optional[str] = Field(None, max_length=128)
    auto_select: bool = False
    resume_factory: bool = True
    clear_focus: bool = False


class StorefrontAdminPatch(BaseModel):
    """Human score + optional forced storefront listing (bypasses marketplace gates only)."""

    quality_score: Optional[int] = Field(None, ge=1, le=5)
    admin_force_list: Optional[bool] = None
    admin_force_list_note: Optional[str] = Field(None, max_length=8000)
    clear_force_list: bool = False
    admin_hide_from_storefront: Optional[bool] = None
    clear_hide_from_storefront: bool = False


class MarketplaceCopyPatch(BaseModel):
    """Merge into ``marketing_content.json`` → ``marketing`` (storefront cards + detail)."""

    product_name: Optional[str] = Field(None, max_length=500)
    tagline: Optional[str] = Field(None, max_length=1200)
    short_description: Optional[str] = Field(None, max_length=12000)
    selling_description: Optional[str] = Field(None, max_length=24000)
    long_description: Optional[str] = Field(None, max_length=32000)


class StorefrontPricingPatch(BaseModel):
    """Manual storefront / checkout USDT price (``sales_data.pricing.admin_storefront_usdt``)."""

    admin_storefront_usdt: Optional[float] = Field(None, gt=0, lt=1_000_000)
    clear_admin_storefront_usdt: bool = False


class HumanReworkBody(BaseModel):
    notes: str = Field(..., min_length=8, max_length=8000)


class ReopenFailedBody(BaseModel):
    notes: str = Field(..., min_length=8, max_length=8000)
    agent_type: Optional[str] = Field(None, max_length=64)
    target_state: Optional[str] = Field(None, max_length=64)


class HumanReviewApproveBody(BaseModel):
    note: str = Field("", max_length=8000)


class HumanReviewRejectBody(BaseModel):
    notes: str = Field(..., min_length=8, max_length=8000)
