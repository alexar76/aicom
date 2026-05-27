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
from web.backend.services.product_pulse import (
    build_product_pulse,
    build_product_pulses_for_metrics,
    enrich_pipeline_catalog_quality_fields,
)
from web.backend.services.storefront_pricing import (
    patch_admin_storefront_usdt,
    read_sales_inner_and_pricing,
    resolve_storefront_price_usdt,
)
from web.backend.api.products import count_showcase_listable_products, is_shipped_pipeline_product_state

from ._router import router
from .models import *
from .helpers import *
from .helpers import (
    _admin_pipeline_storefront_hints,
    _admin_sql_store_available,
    _admin_sqlite_db_path,
    _admin_use_sqlite_pipeline,
    _load_pipeline_snapshot_for_metrics,
    _normalize_pipeline_task,
    _slim_pipeline_task_payloads_for_light_catalog,
    _slim_spec_arch_for_light_catalog,
)
from .routes_director_reports import (
    _admin_merged_pipeline_product,
    _compute_material_summary,
    _load_analyst_brief_for_developer,
    _load_spec_arch_from_disk,
)
from .routes_discovery import _read_marketing_inner
from .artifact_files import (
    admin_product_artifact_category_dirs as _admin_product_artifact_category_dirs,
    build_product_owner_export_zip as _build_product_owner_export_zip,
    preview_artifact_file as _preview_artifact_file,
    sanitize_admin_product_id as _sanitize_admin_product_id,
    unlink_path_quiet as _unlink_path_quiet,
    walk_artifact_files as _walk_artifact_files,
)

logger = logging.getLogger(__name__)

@router.get("/products/{product_id}/developer-handoff")
async def get_developer_handoff(product_id: str):
    """Material the Developer agent sees: spec, architecture, admin text, analyst brief, plus a quality summary."""
    from agents.dev_delivery import DeliveryMode, infer_delivery_mode

    merged = _admin_merged_pipeline_product(product_id)
    if merged is None:
        raise HTTPException(status_code=404, detail="Product not found")

    spec, arch = _load_spec_arch_from_disk(product_id)
    brief = _load_analyst_brief_for_developer(product_id)

    meta = merged.get("metadata") or {}
    category = meta.get("category") if isinstance(meta, dict) else None
    if category is None:
        category = merged.get("category", "uncategorized")
    tags = meta.get("tags") if isinstance(meta, dict) and meta.get("tags") is not None else merged.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    marketing_file = marketing_content_path(product_id)
    if marketing_file.exists():
        try:
            marketing = json.loads(marketing_file.read_text(encoding="utf-8"))
            category = marketing.get("category", category)
            tags = marketing.get("tags", tags)
        except (json.JSONDecodeError, OSError):
            log_suppressed(logger, "dashboard: marketing_content read failed", exc_info=True)

    idea = str(merged.get("idea") or "")
    admin_instructions = str(merged.get("admin_instructions") or "")
    dp = merged.get("delivery_profile")
    if not dp and isinstance(spec, dict):
        dp = spec.get("delivery_profile")
    delivery_profile = str(dp) if dp else None

    mode = infer_delivery_mode(admin_instructions or None, spec or {})
    delivery_mode = mode.value if isinstance(mode, DeliveryMode) else str(mode)

    material_summary = _compute_material_summary(
        spec=spec,
        arch=arch,
        admin_instructions=admin_instructions,
        brief=brief,
        idea=idea,
        delivery_mode=delivery_mode,
    )

    return {
        "product_id": product_id,
        "idea": idea,
        "category": category,
        "tags": tags,
        "admin_instructions": admin_instructions,
        "delivery_profile": delivery_profile,
        "delivery_mode": delivery_mode,
        "analyst_brief_for_developer": brief,
        "specification": spec,
        "architecture": arch,
        "material_summary": material_summary,
    }


# Agent types needed for Pipeline Monitor stage columns (includes dev alias).
_PIPELINE_CATALOG_STAGE_AGENT_TYPES: tuple[str, ...] = (
    "analyst",
    "pm",
    "marketing",
    "methodologist",
    "architect",
    "designer",
    "developer",
    "dev",
    "qa",
    "security",
    "devops",
    "sales",
)


@router.get("/pipeline/products")
async def get_pipeline_products(
    limit: int = Query(60, ge=1, le=2000, description="Page size (admin-only; capped at 2000 per request)."),
    offset: int = Query(0, ge=0),
    sort: Literal["newest", "shipped_first"] = Query(
        "newest",
        description="newest = by created_at only; shipped_first = COMPLETED/DEPLOYED rows first, then newest.",
    ),
    light: bool = Query(
        False,
        description=(
            "When true, skip per-row disk reads for spec/arch/marketing/followup (faster Pipeline Monitor "
            "pagination). Catalog summary still includes the public storefront listable count (same scan "
            "as the marketplace grid)."
        ),
    ),
):
    """Get pipeline products with pagination (same catalog as dashboard / storefront hints)."""
    safe_offset = max(offset, 0)
    safe_limit = max(limit, 1)
    pipeline_file = pipeline_json_path()
    products: dict = {}
    task_queue: list = []
    loaded_sqlite_snapshot = False
    sqlite_fast: tuple[list[tuple[str, dict]], dict[str, int], list[dict], dict[str, dict[str, int]] | None] | None = None

    from core.pipeline_database import pipeline_db_backend

    if (
        _admin_use_sqlite_pipeline()
        and pipeline_db_backend() == "sqlite"
        and _admin_sqlite_db_path().exists()
    ):
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            counts = sm.get_catalog_summary_counts()
            page_rows = sm.list_products_catalog_page(sort, safe_offset, safe_limit)
            pids = [str(p["id"]) for p in page_rows if p.get("id")]
            per_pid_task_counts: dict[str, dict[str, int]] | None = None
            if light:
                per_pid_task_counts = sm.get_task_counts_for_product_ids(pids)
                page_tasks_raw = sm.get_latest_stage_tasks_for_product_ids(
                    pids,
                    agent_types=_PIPELINE_CATALOG_STAGE_AGENT_TYPES,
                )
            else:
                page_tasks_raw = sm.get_tasks_for_product_ids(pids, omit_blob_columns=False)
            sm.close()
            window_list = [(str(p["id"]), p) for p in page_rows if p.get("id")]
            page_tasks = [_normalize_pipeline_task(dict(t)) for t in page_tasks_raw]
            sqlite_fast = (window_list, counts, page_tasks, per_pid_task_counts)
            logger.debug(
                "Admin pipeline products: SQLite paginated catalog sort=%s offset=%s limit=%s rows=%s tasks=%s",
                sort,
                safe_offset,
                safe_limit,
                len(window_list),
                len(page_tasks),
            )
        except Exception as e:
            logger.warning(
                "Admin pipeline products: SQLite paginated load failed (%s), trying full snapshot",
                e,
            )
            sqlite_fast = None

    if sqlite_fast is None and _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from core.pipeline_database import create_sync_pipeline_manager

            sm = create_sync_pipeline_manager()
            for row in sm.get_all_products():
                pid = row.get("id")
                if pid:
                    products[pid] = row
            for t in sm.get_all_tasks():
                task_queue.append(_normalize_pipeline_task(t))
            sm.close()
            loaded_sqlite_snapshot = True
            logger.debug(
                "Admin pipeline products: loaded %s products, %s tasks from SQLite (full snapshot)",
                len(products),
                len(task_queue),
            )
        except Exception as e:
            logger.warning("Admin pipeline products: SQLite load failed (%s), falling back to JSON", e)

    if sqlite_fast is None and not loaded_sqlite_snapshot:
        if not pipeline_file.exists():
            return {
                "products": [],
                "count": 0,
                "total": 0,
                "offset": 0,
                "limit": max(limit, 1),
                "catalog_summary": {
                    "total_products": 0,
                    "shipped_products": 0,
                    "failed_products": 0,
                    "storefront_listable_products": None,
                    "light": light,
                    "sort": sort,
                },
            }
        try:
            with open(pipeline_file, "r") as f:
                data = json.load(f)
            products = data.get("products", {})
            task_queue = [_normalize_pipeline_task(t) for t in data.get("task_queue", [])]
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read pipeline.json: {e}")
            return {
                "products": [],
                "count": 0,
                "total": 0,
                "offset": 0,
                "limit": max(limit, 1),
                "catalog_summary": {
                    "total_products": 0,
                    "shipped_products": 0,
                    "failed_products": 0,
                    "storefront_listable_products": None,
                    "light": light,
                    "sort": sort,
                },
            }

    try:

        # Build task lookup per product
        tasks_by_product: dict[str, list] = {}
        per_pid_task_counts: dict[str, dict[str, int]] | None = None
        if sqlite_fast is not None:
            _window_pairs, catalog_counts, _page_tasks, per_pid_task_counts = sqlite_fast
            task_queue = _page_tasks
            for t in task_queue:
                pid = t.get("product_id", "")
                if pid not in tasks_by_product:
                    tasks_by_product[pid] = []
                tasks_by_product[pid].append(t)
            total_count = int(catalog_counts.get("total", 0))
            shipped_catalog = int(catalog_counts.get("shipped", 0))
            failed_catalog = int(catalog_counts.get("failed", 0))
            window = _window_pairs
        else:
            for t in task_queue:
                pid = t.get("product_id", "")
                if pid not in tasks_by_product:
                    tasks_by_product[pid] = []
                tasks_by_product[pid].append(t)

            # Sort products first and only hydrate the requested window (faster first paint).
            all_items = list(products.items())
            if sort == "shipped_first":
                all_items.sort(
                    key=lambda item: (
                        0 if is_shipped_pipeline_product_state(item[1].get("state")) else 1,
                        -float(item[1].get("created_at") or 0),
                    )
                )
            else:
                all_items.sort(key=lambda item: float(item[1].get("created_at") or 0), reverse=True)
            total_count = len(all_items)
            shipped_catalog = sum(1 for _, p in all_items if is_shipped_pipeline_product_state(p.get("state")))
            failed_catalog = sum(
                1 for _, p in all_items if str(p.get("state", "")).strip().lower() == "failed"
            )
            window = all_items[safe_offset : safe_offset + safe_limit]

        storefront_listable: int | None = None
        try:
            storefront_listable = count_showcase_listable_products()
        except Exception as ex:
            logger.warning("pipeline products: storefront listable count failed (%s)", ex)

        result = []
        for pid, product in window:
            meta = product.get("metadata") or {}
            # Load spec / arch — prefer disk artifacts unless ``light`` (Pipeline Monitor catalog).
            spec = None
            arch = None
            if light:
                spec = product.get("spec") or meta.get("spec")
                arch = product.get("architecture") or meta.get("architecture")
                spec, arch = _slim_spec_arch_for_light_catalog(spec, arch)
            else:
                spec_file = specification_path(pid)
                if spec_file.exists():
                    try:
                        spec = json.loads(spec_file.read_text())
                    except Exception:
                        log_suppressed(logger, "dashboard: spec read failed for %s", pid, exc_info=True)
                if spec is None:
                    spec = product.get("spec") or meta.get("spec")

                arch_file = architecture_json_path(pid)
                if arch_file.exists():
                    try:
                        arch = json.loads(arch_file.read_text())
                    except Exception:
                        log_suppressed(logger, "dashboard: architecture read failed for %s", pid, exc_info=True)
                if arch is None:
                    arch = product.get("architecture") or meta.get("architecture")

            product_tasks_all = tasks_by_product.get(pid, [])
            pre_tc = (per_pid_task_counts or {}).get(pid) if per_pid_task_counts is not None else None
            if pre_tc is not None:
                completed_tasks = int(pre_tc.get("completed", 0))
                failed_tasks = int(pre_tc.get("failed", 0))
                running_tasks = int(pre_tc.get("running", 0))
                pending_tasks = int(pre_tc.get("pending", 0))
                total_tasks_n = int(pre_tc.get("total", len(product_tasks_all)))
            else:
                completed_tasks = sum(1 for t in product_tasks_all if t.get("status") == "completed")
                failed_tasks = sum(1 for t in product_tasks_all if t.get("status") == "failed")
                running_tasks = sum(1 for t in product_tasks_all if t.get("status") == "running")
                pending_tasks = sum(1 for t in product_tasks_all if t.get("status") == "pending")
                total_tasks_n = len(product_tasks_all)
            failed_task_errors = [
                str(t.get("error") or "").strip()
                for t in product_tasks_all
                if t.get("status") == "failed" and str(t.get("error") or "").strip()
            ]
            failed_task_errors = failed_task_errors[:3]

            storefront_visible = False
            storefront_gate_reasons: list[str] = []
            try:
                storefront_visible, storefront_gate_reasons = _admin_pipeline_storefront_hints(pid, product)
            except Exception as ex:
                logger.debug("storefront hints for %s: %s", pid, ex)

            fu_raw = read_followup(pid)
            storefront_followup = normalize_pipeline_followup(fu_raw)

            category = meta.get("category") or product.get("category", "uncategorized")
            tags = meta.get("tags") if meta.get("tags") is not None else product.get("tags", [])
            storefront_marketing_copy: dict[str, Any] = {}
            if not light:
                marketing_file = marketing_content_path(pid)
                if marketing_file.exists():
                    try:
                        marketing = json.loads(marketing_file.read_text())
                        category = marketing.get("category", category)
                        tags = marketing.get("tags", tags)
                        inner = marketing.get("marketing")
                        if isinstance(inner, dict):
                            storefront_marketing_copy = inner
                    except Exception:
                        log_suppressed(logger, "dashboard: marketing_content read failed for %s", pid, exc_info=True)

            row: dict[str, Any] = {
                "id": pid,
                "idea": product.get("idea", ""),
                "category": category,
                "tags": tags,
                "admin_instructions": product.get("admin_instructions", ""),
                "state": product.get("state", "UNKNOWN"),
                "created_at": product.get("created_at", 0),
                "updated_at": product.get("updated_at", 0),
                "spec": spec,
                "architecture": arch,
                "tasks": (
                    _slim_pipeline_task_payloads_for_light_catalog(product_tasks_all)
                    if light
                    else product_tasks_all
                ),
                "task_counts": {
                    "total": total_tasks_n,
                    "completed": completed_tasks,
                    "failed": failed_tasks,
                    "running": running_tasks,
                    "pending": pending_tasks,
                },
                "failure_reason": product.get("failure_reason") or meta.get("failure_reason"),
                "last_error": product.get("error") or meta.get("error"),
                "failed_task_errors": failed_task_errors,
                "quality_repair_round": product.get("quality_repair_round"),
                "pm_spec_requeue_count": product.get("pm_spec_requeue_count")
                or meta.get("pm_spec_requeue_count"),
                "storefront_visible": storefront_visible,
                "storefront_gate_reasons": storefront_gate_reasons,
                "storefront_followup": storefront_followup,
                "storefront_marketing_copy": storefront_marketing_copy,
            }
            if str(product.get("state") or "").upper() == "FAILED":
                try:
                    row["failure_report"] = build_failure_report(
                        product,
                        product_tasks_all if not light else product_tasks_all,
                    )
                except Exception as ex:
                    logger.debug("failure_report for %s: %s", pid, ex)

            if not light and is_shipped_pipeline_product_state(product.get("state")):
                s_inner, s_pricing = read_sales_inner_and_pricing(pid)
                m_for_price = storefront_marketing_copy if isinstance(storefront_marketing_copy, dict) else {}
                eff, tier = resolve_storefront_price_usdt(
                    marketing=m_for_price,
                    sales_config_inner=s_inner,
                )
                row["storefront_effective_price_usdt"] = eff
                row["storefront_price_tier"] = tier
                raw_adm = s_pricing.get("admin_storefront_usdt")
                if isinstance(raw_adm, (int, float)) and float(raw_adm) > 0:
                    row["storefront_admin_price_usdt"] = float(raw_adm)
                else:
                    row["storefront_admin_price_usdt"] = None

            result.append(row)
        
        # ── Per-product economics enrichment ─────────────────────────────────
        # Single pass over llm_calls.jsonl (light + full — vitals need real spend per product).
        try:
            from core.quality_settings import max_pipeline_cost_usd

            _cap = max_pipeline_cost_usd()
            visible_ids = {r["id"] for r in result}
            eco_map = get_product_llm_costs(visible_ids)
            for r in result:
                pid = r["id"]
                eco = eco_map.get(pid)
                sf_q = r.get("storefront_followup", {}) or {}
                qs = sf_q.get("quality_score")
                try:
                    qs_f = float(qs) if qs is not None else None
                except (TypeError, ValueError):
                    qs_f = None
                if eco is not None:
                    r["economics"] = eco
                else:
                    r["economics"] = {
                        "llm_cost_usd": 0.0,
                        "llm_call_count": 0,
                        "llm_total_tokens": 0,
                        "llm_agent_breakdown": {},
                    }
                r["economics"]["roi_band"] = compute_roi_band(
                    r["economics"].get("llm_cost_usd"), qs_f,
                )
                r["economics"]["quality_score"] = qs_f
                if _cap > 0:
                    r["economics"]["pipeline_cost_cap_usd"] = _cap
        except Exception as eco_err:
            logger.warning("Product economics enrichment failed: %s", eco_err)

        try:
            dr = factory_data_root()
            for r in result:
                try:
                    r["pulse"] = build_product_pulse(r, light=light, data_root=dr)
                    enrich_pipeline_catalog_quality_fields(r, data_root=dr)
                except Exception as ex:
                    logger.debug("product pulse for %s: %s", r.get("id"), ex)
                    r["pulse"] = None
        except Exception as pulse_err:
            logger.warning("Product pulse enrichment failed: %s", pulse_err)
            for r in result:
                r["pulse"] = None

        return {
            "products": result,
            "count": len(result),
            "total": total_count,
            "offset": safe_offset,
            "limit": safe_limit,
            "catalog_summary": {
                "total_products": total_count,
                "shipped_products": shipped_catalog,
                "failed_products": failed_catalog,
                "storefront_listable_products": storefront_listable,
                "light": light,
                "sort": sort,
                "sort_note": (
                    "Shipped builds (COMPLETED / DEPLOYED_PRODUCTION) are listed first, then the newest in-progress work."
                    if sort == "shipped_first"
                    else "Rows are strictly newest-first by created_at only — shipped SKUs may be far down; switch sort or use filters."
                ),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get pipeline products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline products: {str(e)}")


@router.patch("/pipeline/products/{product_id}/followup")
async def patch_pipeline_product_followup(product_id: str, body: StorefrontFollowupPatch):
    """Set manual storefront follow-up label (planned rework vs not pursuing). Stored on disk under state/product_followup/."""
    try:
        from web.backend.services.product_followup import set_product_improvement_on_hold

        record = None
        if body.improvement_on_hold is not None:
            record = set_product_improvement_on_hold(product_id, bool(body.improvement_on_hold))
        if body.followup is not None or body.planned_notes is not None or body.not_pursuing_reason is not None:
            record = validate_and_save(
                product_id,
                followup=body.followup,
                planned_notes=body.planned_notes,
                not_pursuing_reason=body.not_pursuing_reason,
            )
        if record is None:
            from web.backend.services.product_followup import read_followup, normalize_pipeline_followup

            record = normalize_pipeline_followup(read_followup(product_id))
        vis, reasons = _admin_pipeline_storefront_hints(product_id)
        invalidate_storefront_categories_cache()
        return {
            "product_id": product_id,
            "storefront_followup": record,
            "storefront_visible": vis,
            "storefront_gate_reasons": reasons,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/pipeline/products/{product_id}/storefront-admin")
async def patch_pipeline_product_storefront_admin(product_id: str, body: StorefrontAdminPatch):
    """Human quality score (1–5) and/or forced public listing (requires justification note when enabling)."""
    if (
        body.quality_score is None
        and body.admin_force_list is None
        and not body.clear_force_list
        and body.admin_hide_from_storefront is None
        and not body.clear_hide_from_storefront
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide quality_score, admin_force_list, clear_force_list, "
                "admin_hide_from_storefront, or clear_hide_from_storefront"
            ),
        )
    try:
        record = patch_admin_decisions(
            product_id,
            quality_score=body.quality_score,
            admin_force_list=body.admin_force_list,
            admin_force_list_note=body.admin_force_list_note,
            clear_force_list=body.clear_force_list,
            admin_hide_from_storefront=body.admin_hide_from_storefront,
            clear_hide_from_storefront=body.clear_hide_from_storefront,
        )
        vis, reasons = _admin_pipeline_storefront_hints(product_id)
        invalidate_storefront_categories_cache()
        return {
            "product_id": product_id,
            "storefront_followup": record,
            "storefront_visible": vis,
            "storefront_gate_reasons": reasons,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _merge_marketing_copy(product_id: str, body: MarketplaceCopyPatch) -> None:
    mkt_path = marketing_content_path(product_id)
    raw: dict[str, Any]
    if mkt_path.exists():
        try:
            loaded = json.loads(mkt_path.read_text(encoding="utf-8"))
            raw = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            raw = {}
    else:
        raw = {}
    m = raw.get("marketing")
    if not isinstance(m, dict):
        m = {}
    for key in ("product_name", "tagline", "short_description", "selling_description", "long_description"):
        val = getattr(body, key)
        if val is not None and isinstance(val, str):
            m[key] = val.strip()
    raw["marketing"] = m
    mkt_path.parent.mkdir(parents=True, exist_ok=True)
    mkt_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


@router.patch("/pipeline/products/{product_id}/marketplace-copy")
async def patch_pipeline_product_marketplace_copy(product_id: str, body: MarketplaceCopyPatch):
    """Edit storefront-facing strings stored under marketing_content.json → marketing."""
    if all(
        getattr(body, k) is None
        for k in ("product_name", "tagline", "short_description", "selling_description", "long_description")
    ):
        raise HTTPException(status_code=400, detail="Provide at least one marketplace copy field")
    _merge_marketing_copy(product_id, body)
    inner = _read_marketing_inner(product_id) or {}
    vis, reasons = _admin_pipeline_storefront_hints(product_id)
    invalidate_storefront_categories_cache()
    return {
        "product_id": product_id,
        "storefront_marketing_copy": inner,
        "storefront_visible": vis,
        "storefront_gate_reasons": reasons,
    }


@router.patch("/pipeline/products/{product_id}/storefront-pricing")
async def patch_pipeline_product_storefront_pricing(product_id: str, body: StorefrontPricingPatch):
    """Set or clear manual storefront / crypto checkout USDT price (``sales_config.json``)."""
    if not body.clear_admin_storefront_usdt and body.admin_storefront_usdt is None:
        raise HTTPException(
            status_code=400,
            detail="Provide admin_storefront_usdt or set clear_admin_storefront_usdt to true",
        )
    try:
        out = patch_admin_storefront_usdt(
            product_id,
            admin_storefront_usdt=body.admin_storefront_usdt,
            clear_admin_storefront_usdt=body.clear_admin_storefront_usdt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    products, _tasks = _load_pipeline_snapshot_for_metrics()
    row = products.get(product_id)
    vis, reasons = _admin_pipeline_storefront_hints(product_id, row if isinstance(row, dict) else None)
    invalidate_storefront_categories_cache()
    return {
        "product_id": product_id,
        "storefront_pricing": out,
        "storefront_visible": vis,
        "storefront_gate_reasons": reasons,
    }


@router.post("/pipeline/products/{product_id}/human-rework")
async def post_pipeline_product_human_rework(product_id: str, body: HumanReworkBody):
    """Shipped product → BUG_FOUND + developer DEV_FIXING with human instructions (repair loop)."""
    res = inject_human_admin_rework(product_id, body.notes)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason") or "rework_failed")
    return {"product_id": product_id, **res}


@router.get("/pipeline/products/{product_id}/failure-report")
async def get_pipeline_product_failure_report(product_id: str):
    """Structured failure report for a FAILED (or recently failed) product."""
    pid = _sanitize_admin_product_id(product_id)
    product: dict[str, Any] | None = None
    tasks: list[dict[str, Any]] = []
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            product = sm.get_product(pid)
            if product:
                tasks = sm.get_tasks_by_product(pid)
            sm.close()
        except Exception as e:
            logger.debug("failure-report sqlite: %s", e)
    if not product:
        merged = _admin_merged_pipeline_product(pid)
        if not merged:
            raise HTTPException(status_code=404, detail="product_not_found")
        product = merged
    return {"product_id": pid, "failure_report": build_failure_report(product, tasks)}


@router.post("/pipeline/products/{product_id}/reopen-failed")
async def post_pipeline_product_reopen_failed(product_id: str, body: ReopenFailedBody):
    """FAILED product → recovery state + new agent task (operator rework, not terminal)."""
    res = reopen_failed_product(
        product_id,
        body.notes,
        agent_type=body.agent_type,
        target_state=body.target_state,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason") or "reopen_failed")
    return {"product_id": product_id, **res}


@router.post("/pipeline/products/{product_id}/human-review/approve")
async def post_pipeline_human_review_approve(product_id: str, body: HumanReviewApproveBody | None = None):
    """After DevOps (full-software profile): advance to SALES_ACTIVE and queue sales task."""
    note = (body.note if body else None) or ""
    res = approve_post_devops_human_review(product_id, note)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason") or "human_review_approve_failed")
    return {"product_id": product_id, **res}


@router.post("/pipeline/products/{product_id}/human-review/reject")
async def post_pipeline_human_review_reject(product_id: str, body: HumanReviewRejectBody):
    """Send product back to developer with notes (BUG_FOUND → DEV_FIXING)."""
    res = reject_post_devops_human_review(product_id, body.notes)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason") or "human_review_reject_failed")
    return {"product_id": product_id, **res}

