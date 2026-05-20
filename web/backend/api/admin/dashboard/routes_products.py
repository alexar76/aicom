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

@router.get("/products/{product_id}/files")
async def get_product_files(product_id: str):
    """Browse all generated files/artifacts for a product (recursive per category)."""
    pid = _sanitize_admin_product_id(product_id)
    base_dirs = _admin_product_artifact_category_dirs(pid)

    files: list[dict[str, Any]] = []
    truncated_by_category: dict[str, bool] = {}
    for category, dir_path in base_dirs.items():
        paths, truncated = _walk_artifact_files(dir_path)
        if truncated:
            truncated_by_category[category] = True
        for fpath in paths:
            if not fpath.is_file():
                continue
            try:
                rel = fpath.relative_to(dir_path).as_posix()
            except ValueError:
                rel = fpath.name
            try:
                size_bytes = fpath.stat().st_size
            except OSError:
                size_bytes = 0
            preview, err = _preview_artifact_file(fpath, size_bytes=size_bytes)
            entry: dict[str, Any] = {
                "category": category,
                "filename": rel,
                "path": str(fpath),
                "size_bytes": size_bytes,
            }
            if err is not None:
                entry["error"] = err
            else:
                entry["preview"] = preview
            files.append(entry)

    payload: dict[str, Any] = {
        "product_id": pid,
        "files": files,
        "count": len(files),
    }
    if truncated_by_category:
        payload["truncated_by_category"] = truncated_by_category
    return payload


@router.get("/products/{product_id}/owner-export.zip")
async def download_product_owner_export_zip(
    product_id: str,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin_with_rbac),
):
    """ZIP of on-disk artifacts for one product (factory owner), same tree as Admin → Files.

    Requires **operator** role or higher — viewers can browse file previews but must not bulk-export IP.
    """
    pid = _sanitize_admin_product_id(product_id)
    role = normalize_role(admin.get("role"))
    if rank(role) < rank(AdminRole.OPERATOR):
        raise HTTPException(
            status_code=403,
            detail="Product owner archive requires operator, admin, or super_admin role (viewer cannot download).",
        )

    merged = _admin_merged_pipeline_product(pid)
    dirs = _admin_product_artifact_category_dirs(pid)
    has_file = False
    for root in dirs.values():
        if root.is_dir():
            for _, _, fnames in os.walk(root, topdown=True, followlinks=False):
                # prune heavy dirs same as export walk
                if fnames:
                    has_file = True
                    break
        if has_file:
            break
    if merged is None and not has_file:
        raise HTTPException(
            status_code=404,
            detail="Product not found, or no pipeline record and no on-disk artifacts yet.",
        )

    zip_path, filename = _build_product_owner_export_zip(pid)
    background_tasks.add_task(_unlink_path_quiet, str(zip_path))
    return FileResponse(
        path=str(zip_path),
        filename=filename,
        media_type="application/zip",
    )


@router.get("/products/{product_id}/spec")
async def get_product_spec(product_id: str):
    """Get the specification for a product."""
    spec_file = specification_path(product_id)
    if not spec_file.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Specification not found for this product")

    try:
        with open(spec_file, "r") as f:
            spec = json.load(f)
        return {"product_id": product_id, "spec": spec}
    except json.JSONDecodeError:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Invalid specification file")


@router.get("/products/{product_id}/architecture")
async def get_product_architecture(product_id: str):
    """Get persisted ``architecture.json`` for a product (Workshop / diff tooling)."""
    arch_file = architecture_json_path(product_id)
    if not arch_file.exists():
        raise HTTPException(status_code=404, detail="Architecture file not found for this product")

    try:
        with open(arch_file, "r") as f:
            arch = json.load(f)
        return {"product_id": product_id, "architecture": arch}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid architecture file")


def _agent_log_time(entry: dict[str, Any]) -> float:
    t = entry.get("time", 0)
    try:
        return float(t)
    except (TypeError, ValueError):
        return 0.0


@router.get("/agent/logs")
async def get_agent_logs(
    agent: Optional[str] = None,
    limit: int = Query(200, ge=1, le=5000),
    since: Optional[float] = Query(None, description="Unix seconds, inclusive lower bound on entry `time`"),
    until: Optional[float] = Query(None, description="Unix seconds, inclusive upper bound on entry `time`"),
):
    """Get agent execution logs from all agent log files."""
    logs_dir_path = logs_dir()
    all_logs: list[dict[str, Any]] = []

    if not logs_dir_path.exists():
        return {"logs": [], "count": 0, "total": 0}

    agent_files = list(logs_dir_path.glob("*.jsonl"))
    if agent:
        agent_files = [f for f in agent_files if f.stem == agent]

    for log_file in agent_files:
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            if agent and entry.get("agent") != agent:
                                continue
                            all_logs.append(entry)
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
        except Exception as e:
            logger.warning(f"Failed to read agent log {log_file}: {e}")

    if since is not None:
        all_logs = [x for x in all_logs if _agent_log_time(x) >= since]
    if until is not None:
        all_logs = [x for x in all_logs if _agent_log_time(x) <= until]

    # Sort by time ascending, return the last `limit` rows (most recent within the window)
    all_logs.sort(key=_agent_log_time)
    window_total = len(all_logs)
    tail = all_logs[-limit:] if all_logs else []
    return {"logs": tail, "count": len(tail), "total": window_total}


@router.get("/products/{product_id}/security-report")
async def get_security_report(product_id: str):
    """Get the security report for a product from pipeline artifacts."""
    from web.backend.services.security_report_loader import load_security_report

    report = load_security_report(product_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No security report found for this product")

    return {"product_id": product_id, "report": report}


@router.get("/director/analysis")
async def get_director_analysis():
    """Get the latest Director AI analysis status and recent decisions."""
    from director.scheduler import DirectorScheduler
    from director.report_generator import ReportGenerator

    reports_dir = director_reports_dir()

    # Count ALL reports in the directory (not just the ones we return)
    total_report_count = 0
    reports = []
    if reports_dir.exists():
        all_files = sorted(reports_dir.glob("*.md"), reverse=True)
        total_report_count = len(all_files)
        for f in all_files[:10]:
            try:
                content = f.read_text()
                reports.append({
                    "filename": f.name,
                    "content": content[:500],  # Preview only
                    "modified": f.stat().st_mtime,
                })
            except Exception as e:
                reports.append({"filename": f.name, "error": str(e)})

    return {
        "reports": reports,
        "report_count": total_report_count,
    }

