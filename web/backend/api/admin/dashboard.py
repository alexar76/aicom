"""
Admin Dashboard API
===================
Endpoints for the admin dashboard with real-time metrics.
Includes SSE streaming, Director decisions, escalation logs, and metrics history.
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

from core.paths import data_root as factory_data_root
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
from web.backend.services.product_followup import (
    normalize_pipeline_followup,
    patch_admin_decisions,
    read_followup,
    validate_and_save,
)
from web.backend.services.pipeline_demo_replay import metrics_demo_replay_slice
from web.backend.services.storefront_counts_cache import invalidate_storefront_categories_cache
from web.backend.services.product_economics import compute_roi_band, get_product_llm_costs
from web.backend.services.product_pulse import build_product_pulse, build_product_pulses_for_metrics
from web.backend.services.storefront_pricing import (
    patch_admin_storefront_usdt,
    read_sales_inner_and_pricing,
    resolve_storefront_price_usdt,
)
from web.backend.api.products import count_showcase_listable_products, is_shipped_pipeline_product_state

logger = logging.getLogger(__name__)


class StorefrontFollowupPatch(BaseModel):
    """Manual pipeline note: planned rework toward storefront vs explicitly not pursuing."""

    followup: Optional[Literal["planned", "not_pursuing"]] = None
    planned_notes: Optional[str] = Field(None, max_length=8000)
    not_pursuing_reason: Optional[str] = Field(None, max_length=8000)


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


class HumanReviewApproveBody(BaseModel):
    note: str = Field("", max_length=8000)


class HumanReviewRejectBody(BaseModel):
    notes: str = Field(..., min_length=8, max_length=8000)


router = APIRouter(prefix="/api/admin", tags=["admin-dashboard"], dependencies=[Depends(require_admin_with_rbac)])

# ── Helpers ──────────────────────────────────────────────────────────────────

METRICS_HISTORY_FILE = "/app/data/logs/metrics_history.jsonl"


def _admin_pipeline_storefront_hints(
    product_id: str, product_row: Optional[dict[str, Any]] = None
) -> tuple[bool, list[str]]:
    """Storefront eligibility for admin pipeline rows.

    When ``product_row`` is provided (the same dict already held in the pipeline
    catalog loop), reuse it — **do not** reload the full SQLite/JSON snapshot per
    row (that was O(window × full DB) and caused timeouts on large catalogs).
    """
    from web.backend.api.products import public_storefront_listing_eligible

    if isinstance(product_row, dict) and product_row:
        return public_storefront_listing_eligible(product_id, product_row)
    products, _tasks = _load_pipeline_snapshot_for_metrics()
    row = products.get(product_id)
    if not isinstance(row, dict):
        return False, ["product_not_in_pipeline"]
    return public_storefront_listing_eligible(product_id, row)


def _admin_use_sqlite_pipeline() -> bool:
    return os.environ.get("USE_SQLITE", "").strip().lower() in ("1", "true", "yes")


def _admin_sqlite_db_path() -> Path:
    return Path(os.environ.get("SQLITE_PATH", "/app/data/state/pipeline.db"))


def _normalize_pipeline_task(task: dict) -> dict:
    """SQLite stores statuses upper-case; pipeline.json uses lower-case."""
    t = dict(task)
    st = t.get("status")
    if isinstance(st, str):
        t["status"] = st.lower()
    return t


def _load_pipeline_snapshot_for_metrics() -> tuple[dict[str, Any], list[dict]]:
    """
    Products keyed by id and global task list for dashboard counts.

    When ``USE_SQLITE`` is enabled and ``pipeline.db`` exists, SQLite is the
    source of truth (``pipeline.json`` is often empty or stale). Otherwise
    read ``pipeline.json``.
    """
    if _admin_use_sqlite_pipeline() and _admin_sqlite_db_path().exists():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            try:
                plist = sm.get_all_products()
                tlist = sm.get_all_tasks()
            finally:
                sm.close()
            products: dict[str, Any] = {}
            for p in plist:
                pid = p.get("id")
                if pid:
                    products[str(pid)] = p
            task_queue = [_normalize_pipeline_task(dict(t)) for t in tlist]
            return products, task_queue
        except Exception as e:
            logger.warning(
                "Dashboard metrics: SQLite snapshot failed (%s), falling back to pipeline.json",
                e,
            )

    pipeline_file = Path("/app/data/state/pipeline.json")
    pipeline_data: dict[str, Any] = {"products": {}, "task_queue": []}
    if pipeline_file.exists():
        try:
            with open(pipeline_file, "r") as f:
                pipeline_data = json.load(f)
        except Exception:
            pass
    products = pipeline_data.get("products") or {}
    raw_tasks = pipeline_data.get("task_queue") or []
    task_queue = [_normalize_pipeline_task(dict(t)) for t in raw_tasks]
    return products, task_queue


def _task_status_lower(t: dict) -> str:
    return str(t.get("status") or "").strip().lower()


# Large JSONL logs (multi‑MB) were read fully for every dashboard open — major latency.
_AGENT_LOG_FULL_READ_MAX_BYTES = 200_000
_AGENT_LOG_TAIL_MAX_BYTES = 512_000
_AGENT_LOG_TAIL_MAX_LINES = 3_000


def _read_jsonl_tail_entries(path: Path, *, max_bytes: int, max_lines: int) -> list[dict[str, Any]]:
    """Parse JSONL from the tail of a file (avoids reading gigabyte logs on each dashboard hit)."""
    out: list[dict[str, Any]] = []
    try:
        size = path.stat().st_size
    except OSError:
        return out
    if size <= 0:
        return out
    read_bytes = min(max_bytes, size)
    try:
        with open(path, "rb") as f:
            if read_bytes < size:
                f.seek(size - read_bytes)
            raw = f.read()
    except OSError:
        return out
    text = raw.decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if read_bytes < size and lines:
        lines = lines[1:]
    for line in lines[-max_lines:]:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    return out


def _read_jsonl_entries_for_agent_log(path: Path) -> list[dict[str, Any]]:
    """Full read for small logs; tail-only for large files (see size thresholds)."""
    try:
        sz = path.stat().st_size
    except OSError:
        return []
    if sz <= _AGENT_LOG_FULL_READ_MAX_BYTES:
        entries: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            entries.append(obj)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return entries
    return _read_jsonl_tail_entries(
        path,
        max_bytes=_AGENT_LOG_TAIL_MAX_BYTES,
        max_lines=_AGENT_LOG_TAIL_MAX_LINES,
    )


def _collect_agent_metrics() -> dict:
    """Collect per-agent status from JSONL logs (tail-bounded for large files)."""
    log_dir = Path("/app/data/logs")
    agents: dict[str, Any] = {}
    if log_dir.exists():
        for log_file in sorted(log_dir.glob("*.jsonl")):
            agent_type = log_file.stem
            entries = _read_jsonl_entries_for_agent_log(log_file)
            if entries:
                recent = [e for e in entries if e.get("time", 0) > time.time() - 3600]
                errors = [e for e in recent if "ERROR" in str(e.get("message", "")).upper()]
                agents[agent_type] = {
                    "total_entries": len(entries),
                    "recent_entries": len(recent),
                    "recent_errors": len(errors),
                    "last_active": max((e.get("time", 0) for e in entries), default=0),
                    "status": "running" if recent else ("idle" if entries else "offline"),
                }
    # Designer is a pipeline stage (UX in architecture); no separate worker log file — mirror Architect.
    if "designer" not in agents and "architect" in agents:
        agents["designer"] = dict(agents["architect"])
    return agents


def _collect_director_status(*, include_benchmark_payload: bool = True) -> dict:
    """Collect Director AI status (optionally omit large benchmark JSON for fast dashboard)."""
    reports_dir = Path("/app/data/reports/director")
    report_count = 0
    last_report = None
    if reports_dir.exists():
        report_files = sorted(reports_dir.glob("*.md"), reverse=True)
        report_count = len(report_files)
        if report_files:
            try:
                stat = report_files[0].stat()
                last_report = stat.st_mtime
            except Exception:
                pass

    # Check pending decisions
    decisions_file = Path("/app/data/state/director_decisions.json")
    pending_count = 0
    if decisions_file.exists():
        try:
            with open(decisions_file, "r") as f:
                data = json.load(f)
            pending_count = len(data.get("pending", []))
        except Exception:
            pass

    benchmark_scorecard_path = Path("/app/data/reports/benchmark_scorecard.json")
    benchmark_alerts_path = Path("/app/data/reports/benchmark_alerts.json")
    benchmark_scorecard = None
    benchmark_alert_count = 0
    if include_benchmark_payload and benchmark_scorecard_path.exists():
        try:
            benchmark_scorecard = json.loads(benchmark_scorecard_path.read_text(encoding="utf-8"))
        except Exception:
            benchmark_scorecard = None
    if benchmark_alerts_path.exists():
        try:
            alerts_doc = json.loads(benchmark_alerts_path.read_text(encoding="utf-8"))
            benchmark_alert_count = len(alerts_doc.get("alerts") or [])
        except Exception:
            benchmark_alert_count = 0

    return {
        "report_count": report_count,
        "last_report_time": last_report,
        "pending_decisions": pending_count,
        "status": "active" if report_count > 0 else "initializing",
        "benchmark_scorecard": benchmark_scorecard,
        "benchmark_alert_count": benchmark_alert_count,
    }


def _collect_escalation_summary(*, tail_only: bool = False) -> dict:
    """Collect escalation summary from escalation log file."""
    log_file = Path("/app/data/logs/escalations.jsonl")
    entries: list[dict] = []
    if log_file.exists():
        try:
            if tail_only or log_file.stat().st_size > _AGENT_LOG_FULL_READ_MAX_BYTES:
                entries = _read_jsonl_tail_entries(
                    log_file,
                    max_bytes=_AGENT_LOG_TAIL_MAX_BYTES,
                    max_lines=_AGENT_LOG_TAIL_MAX_LINES,
                )
            else:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict):
                                    entries.append(obj)
                            except json.JSONDecodeError:
                                pass
        except Exception:
            pass

    now = time.time()
    recent = [e for e in entries if e.get("timestamp", 0) > now - 3600]

    by_agent: dict[str, dict] = {}
    for e in recent:
        agent = e.get("agent_type", "unknown")
        if agent not in by_agent:
            by_agent[agent] = {"total": 0, "retries": 0, "bypasses": 0, "escalations": 0}
        by_agent[agent]["total"] += 1
        action = e.get("action_taken", "")
        if action == "retry":
            by_agent[agent]["retries"] += 1
        elif action == "bypass":
            by_agent[agent]["bypasses"] += 1
        elif action == "escalate":
            by_agent[agent]["escalations"] += 1

    return {
        "total_all_time": len(entries),
        "recent_1h": len(recent),
        "by_agent": by_agent,
        "recent_events": recent[-10:],
    }


def _build_full_metrics() -> dict:
    """Build the complete metrics payload (used by both /dashboard and SSE)."""
    products, task_queue = _load_pipeline_snapshot_for_metrics()

    total = len(products)
    # Align with storefront / Director: shipped = COMPLETED or DEPLOYED_PRODUCTION (any case).
    completed = sum(1 for p in products.values() if is_shipped_pipeline_product_state(p.get("state")))
    failed = sum(1 for p in products.values() if str(p.get("state", "")).strip().lower() == "failed")
    active = max(0, total - completed - failed)

    try:
        storefront_visible = count_showcase_listable_products()
    except Exception as e:
        logger.warning("Dashboard metrics: storefront visible count failed (%s)", e)
        storefront_visible = 0

    pending = sum(1 for t in task_queue if _task_status_lower(t) == "pending")
    running = sum(1 for t in task_queue if _task_status_lower(t) == "running")
    timed_out = sum(1 for t in task_queue if _task_status_lower(t) in ("timeout", "timed_out"))

    # Resource metrics
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.05)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except ImportError:
        cpu = memory = disk = 0

    # Build the state distribution for stage flow
    state_distribution: dict[str, int] = {}
    for p in products.values():
        s = p.get("state", "UNKNOWN")
        state_distribution[s] = state_distribution.get(s, 0) + 1

    esc_summary = _collect_escalation_summary()

    try:
        product_pulses = build_product_pulses_for_metrics(
            products,
            task_queue,
            data_root=factory_data_root(),
        )
    except Exception as e:
        logger.warning("Dashboard metrics: product_pulses failed (%s)", e)
        product_pulses = {}

    return {
        "pipeline": {
            "total_products": total,
            "active_products": active,
            "completed_products": completed,
            "storefront_visible_products": storefront_visible,
            "failed_products": failed,
            "pending_tasks": pending,
            "running_tasks": running,
            "timed_out_tasks": timed_out,
            "state_distribution": state_distribution,
        },
        "resources": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
        },
        "revenue": compute_dashboard_revenue("/app/data", time.time()),
        "security": {
            "status": "healthy",
            "failed_logins_15min": 0,
        },
        "agent_metrics": _collect_agent_metrics(),
        "director_status": _collect_director_status(),
        # Legacy key name; Live Monitor reads ``escalation_summary`` (see admin UI).
        "escalations": esc_summary,
        "escalation_summary": esc_summary,
        "collected_at": time.time(),
        "demo_replay": metrics_demo_replay_slice(),
        "product_pulses": product_pulses,
    }


def _build_quick_dashboard_metrics() -> dict:
    """Lightweight dashboard payload for first paint (skips expensive storefront scan and log aggregation)."""
    products, task_queue = _load_pipeline_snapshot_for_metrics()

    total = len(products)
    completed = sum(1 for p in products.values() if is_shipped_pipeline_product_state(p.get("state")))
    failed = sum(1 for p in products.values() if str(p.get("state", "")).strip().lower() == "failed")
    active = max(0, total - completed - failed)

    pending = sum(1 for t in task_queue if _task_status_lower(t) == "pending")
    running = sum(1 for t in task_queue if _task_status_lower(t) == "running")
    timed_out = sum(1 for t in task_queue if _task_status_lower(t) in ("timeout", "timed_out"))

    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.05)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except ImportError:
        cpu = memory = disk = 0

    state_distribution: dict[str, int] = {}
    for p in products.values():
        s = p.get("state", "UNKNOWN")
        state_distribution[s] = state_distribution.get(s, 0) + 1

    empty_esc = {
        "total_all_time": 0,
        "recent_1h": 0,
        "by_agent": {},
        "recent_events": [],
    }

    return {
        "pipeline": {
            "total_products": total,
            "active_products": active,
            "completed_products": completed,
            "storefront_visible_products": None,
            "failed_products": failed,
            "pending_tasks": pending,
            "running_tasks": running,
            "timed_out_tasks": timed_out,
            "state_distribution": state_distribution,
        },
        "resources": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
        },
        "revenue": compute_dashboard_revenue("/app/data", time.time()),
        "security": {
            "status": "healthy",
            "failed_logins_15min": 0,
        },
        "agent_metrics": {},
        "director_status": _collect_director_status(include_benchmark_payload=False),
        "escalations": empty_esc,
        "escalation_summary": empty_esc,
        "collected_at": time.time(),
        "demo_replay": metrics_demo_replay_slice(),
        "dashboard_partial": True,
    }


def _append_metrics_history(metrics: dict):
    """Append metrics snapshot to rolling history file."""
    try:
        log_file = Path(METRICS_HISTORY_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "timestamp": time.time(),
            "pipeline": metrics["pipeline"],
            "resources": metrics["resources"],
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(snapshot) + "\n")

        # Trim to last 24h (86400s ≈ 17280 entries at 5s intervals, keep last 20000)
        if log_file.stat().st_size > 5_000_000:  # 5MB limit
            with open(log_file, "r") as f:
                lines = f.readlines()
            if len(lines) > 20000:
                with open(log_file, "w") as f:
                    f.writelines(lines[-20000:])
    except Exception as e:
        logger.warning(f"Failed to append metrics history: {e}")


# ── Enhanced Dashboard Endpoint ─────────────────────────────────────────────


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
        return _build_quick_dashboard_metrics()
    metrics = _build_full_metrics()
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
                metrics = _build_full_metrics()
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
    log_file = Path("/app/data/logs/escalations.jsonl")
    entries = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read escalation log: {e}")

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
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read metrics history: {e}")

    return {"metrics": entries[-limit:], "count": min(len(entries), limit), "total": len(entries)}


# ── Director Decisions ──────────────────────────────────────────────────────


DECISIONS_FILE = "/app/data/state/director_decisions.json"


def _load_decisions() -> dict:
    """Load decisions from file."""
    path = Path(DECISIONS_FILE)
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pending": [], "applied": []}


def _save_decisions(data: dict):
    """Save decisions to file."""
    path = Path(DECISIONS_FILE)
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


@router.get("/providers")
async def get_providers():
    """Get LLM provider status with available models."""
    providers_file = Path("/app/data/config/model_providers.yaml")
    ensure_model_providers_file(providers_file)
    providers = {}
    default_provider = None
    
    if providers_file.exists():
        import yaml
        with open(providers_file, "r") as f:
            config = yaml.safe_load(f)
        
        default_provider = config.get("default_provider")
        
        for name, pconf in config.get("providers", {}).items():
            configured_models = pconf.get("models", {})
            active_heavy = configured_models.get("heavy", "")
            active_light = configured_models.get("light", "")
            
            # Try to fetch available models from the provider
            available_models = []
            base_url = pconf.get("base_url", "")
            if base_url and pconf.get("enabled", False):
                health_path = pconf.get("health_check_endpoint", "/v1/models")
                try:
                    import httpx
                    resp = httpx.get(f"{base_url.rstrip('/v1')}{health_path}", timeout=3)
                    if resp.status_code == 200:
                        data = resp.json()
                        # OpenAI-compatible format
                        if "data" in data:
                            available_models = [m["id"] for m in data["data"]]
                        # Ollama format
                        elif "models" in data:
                            available_models = [m["name"] for m in data["models"]]
                except Exception:
                    pass
            
            # If no available models fetched, use configured ones
            if not available_models:
                available_models = list(set(filter(None, [active_heavy, active_light])))
            
            providers[name] = {
                "enabled": pconf.get("enabled", False),
                "type": pconf.get("provider_type", "unknown"),
                "base_url": base_url,
                "models": {
                    "heavy": active_heavy,
                    "light": active_light,
                },
                "available_models": available_models,
                "status": "online" if available_models else ("disabled" if not pconf.get("enabled", False) else "offline"),
                "is_default": name == default_provider,
            }

    return {"providers": providers, "default_provider": default_provider}


@router.patch("/providers/{provider_name}")
async def update_provider_models(provider_name: str, request: Request):
    """Update model selection for a provider."""
    body = await request.json()
    providers_file = Path("/app/data/config/model_providers.yaml")
    
    if not providers_file.exists():
        raise HTTPException(status_code=404, detail="Providers config not found")
    
    import yaml
    with open(providers_file, "r") as f:
        config = yaml.safe_load(f)
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    # Update models
    models = config["providers"][provider_name].get("models", {})
    if "heavy" in body:
        models["heavy"] = body["heavy"]
    if "light" in body:
        models["light"] = body["light"]
    config["providers"][provider_name]["models"] = models
    
    # Write back
    with open(providers_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Hot-reload - try to reload LLM router if it exists
    try:
        if hasattr(request.app.state, 'llm_router'):
            request.app.state.llm_router.reload_config()
    except Exception:
        pass
    
    return {"message": f"Provider '{provider_name}' updated", "models": models}


@router.post("/providers/{provider_name}/test")
async def test_provider(provider_name: str, request: Request):
    """Test a provider by sending a simple prompt to calibrate response quality."""
    providers_file = Path("/app/data/config/model_providers.yaml")
    
    if not providers_file.exists():
        raise HTTPException(status_code=404, detail="Providers config not found")
    
    import yaml
    import httpx
    
    with open(providers_file, "r") as f:
        config = yaml.safe_load(f)
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    pconf = config["providers"][provider_name]
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    model_role = body.get("model_role", "heavy")
    custom_prompt = body.get("prompt", "")
    
    # Determine which model to use
    models = pconf.get("models", {})
    model_name = models.get(model_role, "")
    if not model_name:
        model_name = pconf.get("model", "")
    if not model_name and pconf.get("available_models"):
        model_name = pconf["available_models"][0]
    
    # Remove trailing /v1 suffix if present (OpenAI-compatible format)
    base_url = pconf.get("base_url", "").replace("/v1", "").rstrip("/")
    api_key = pconf.get("api_key", "")
    chat_endpoint = f"{base_url}/v1/chat/completions"
    
    prompt = custom_prompt or "Reply with exactly three words describing your capabilities:"
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 50,
        "temperature": 0.3,
    }
    
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(chat_endpoint, json=payload, headers=headers)
            latency_ms = round((time.time() - start_time) * 1000)
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                    "model": model_name,
                    "error": resp.text[:500],
                }
            
            data = resp.json()
            response_text = ""
            if "choices" in data and len(data["choices"]) > 0:
                response_text = data["choices"][0].get("message", {}).get("content", "")
            
            return {
                "success": True,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "model": model_name,
                "response": response_text[:500],
                "prompt": prompt,
            }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "model": model_name,
            "error": str(e),
        }


# ── Provider CRUD Management ─────────────────────────────────────────────────

def _load_providers_config() -> dict:
    """Load providers config from YAML file."""
    providers_file = Path("/app/data/config/model_providers.yaml")
    ensure_model_providers_file(providers_file)
    if not providers_file.exists():
        return {"providers": {}, "routing_rules": []}
    import yaml
    with open(providers_file, "r") as f:
        return yaml.safe_load(f) or {"providers": {}, "routing_rules": []}


def _save_providers_config(config: dict):
    """Save providers config to YAML file."""
    import yaml
    providers_file = Path("/app/data/config/model_providers.yaml")
    providers_file.parent.mkdir(parents=True, exist_ok=True)
    with open(providers_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


async def _reload_llm_router(request: Request):
    """Try to hot-reload the LLM router after config changes."""
    try:
        if hasattr(request.app.state, 'llm_router'):
            await request.app.state.llm_router.reload_config()
    except Exception:
        pass


DEFAULT_PROVIDER_TEMPLATE = {
    "enabled": True,
    "provider_type": "openai_compatible",
    "base_url": "",
    "api_key": None,
    "api_key_env": None,
    "models": {"heavy": "", "light": "", "vision": None},
    "capabilities": {
        "context_window": FACTORY_CONTEXT_WINDOW_DEFAULT,
        "max_tokens": FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
        "supports_vision": False,
        "supports_streaming": True,
    },
    "health_check_endpoint": "/v1/models",
    "priority": 10,
}


@router.post("/providers")
async def create_provider(request: Request):
    """Add a new LLM provider."""
    body = await request.json()
    config = _load_providers_config()
    
    name = body.get("name", "").strip().lower().replace(" ", "_")
    if not name:
        raise HTTPException(status_code=400, detail="Provider name is required")
    if name in config.get("providers", {}):
        raise HTTPException(status_code=409, detail=f"Provider '{name}' already exists")
    
    provider_config = dict(DEFAULT_PROVIDER_TEMPLATE)
    provider_config.update({
        k: v for k, v in body.items()
        if k != "name" and k in DEFAULT_PROVIDER_TEMPLATE
    })
    # Override specific fields from body
    if "base_url" in body:
        provider_config["base_url"] = body["base_url"]
    if "enabled" in body:
        provider_config["enabled"] = bool(body["enabled"])
    if "provider_type" in body:
        provider_config["provider_type"] = body["provider_type"]
    if "api_key" in body:
        provider_config["api_key"] = body["api_key"] or None
    if "api_key_env" in body:
        provider_config["api_key_env"] = body["api_key_env"] or None
    if "models" in body:
        provider_config["models"]["heavy"] = body["models"].get("heavy", "")
        provider_config["models"]["light"] = body["models"].get("light", "")
    if "capabilities" in body:
        caps = provider_config["capabilities"]
        caps["context_window"] = body["capabilities"].get("context_window", caps["context_window"])
        caps["max_tokens"] = body["capabilities"].get("max_tokens", caps["max_tokens"])
    if "priority" in body:
        provider_config["priority"] = int(body["priority"])
    if "health_check_endpoint" in body:
        provider_config["health_check_endpoint"] = body["health_check_endpoint"]
    
    config.setdefault("providers", {})[name] = provider_config
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{name}' created", "name": name}


@router.put("/providers/{provider_name}")
async def update_provider(provider_name: str, request: Request):
    """Update full provider configuration."""
    body = await request.json()
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    pconf = config["providers"][provider_name]
    
    # Update scalar fields
    for key in ("base_url", "provider_type", "api_key", "api_key_env", "health_check_endpoint"):
        if key in body:
            pconf[key] = body[key] if body[key] else None
    
    if "enabled" in body:
        pconf["enabled"] = bool(body["enabled"])
    if "priority" in body:
        pconf["priority"] = int(body["priority"])
    
    # Update models
    if "models" in body:
        pconf.setdefault("models", {})
        for role in ("heavy", "light", "vision"):
            if role in body["models"]:
                pconf["models"][role] = body["models"][role] if body["models"][role] else None
    
    # Update capabilities
    if "capabilities" in body:
        pconf.setdefault("capabilities", {})
        for cap in ("context_window", "max_tokens", "supports_vision", "supports_streaming"):
            if cap in body["capabilities"]:
                pconf["capabilities"][cap] = body["capabilities"][cap]
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{provider_name}' updated", "provider": pconf}


@router.post("/providers/{provider_name}/set-default")
async def set_default_provider(provider_name: str, request: Request):
    """Set a provider as the default (primary) provider."""
    providers_file = Path("/app/data/config/model_providers.yaml")
    
    try:
        import yaml
        with open(providers_file, "r") as f:
            config = yaml.safe_load(f) or {}
        
        # Verify provider exists
        if provider_name not in config.get("providers", {}):
            return {"status": "error", "message": f"Provider '{provider_name}' not found"}
        
        # Set default
        config["default_provider"] = provider_name
        
        with open(providers_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Hot-reload LLM router
        await _reload_llm_router(request)
        
        return {"status": "ok", "default_provider": provider_name}
    except Exception as e:
        logger.error(f"Failed to set default provider: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/providers/{provider_name}")
async def delete_provider(provider_name: str, request: Request):
    """Remove a provider."""
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    del config["providers"][provider_name]
    
    # Also clean up routing rules that reference this provider
    if "routing_rules" in config:
        for rule in config["routing_rules"]:
            if rule.get("preferred_provider") == provider_name:
                rule["preferred_provider"] = "auto"
            if rule.get("fallback_provider") == provider_name:
                rule["fallback_provider"] = None
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": f"Provider '{provider_name}' deleted"}


@router.patch("/providers/{provider_name}/toggle")
async def toggle_provider(provider_name: str, request: Request):
    """Enable or disable a provider."""
    body = await request.json()
    config = _load_providers_config()
    
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    
    enabled = body.get("enabled", not config["providers"][provider_name].get("enabled", False))
    config["providers"][provider_name]["enabled"] = bool(enabled)
    
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {
        "message": f"Provider '{provider_name}' {'enabled' if enabled else 'disabled'}",
        "enabled": enabled,
    }


@router.get("/providers/routing-rules")
async def get_routing_rules():
    """Get routing rules configuration."""
    config = _load_providers_config()
    return {"routing_rules": config.get("routing_rules", [])}


@router.put("/providers/routing-rules")
async def update_routing_rules(request: Request):
    """Update all routing rules."""
    body = await request.json()
    config = _load_providers_config()
    
    rules = body.get("routing_rules", [])
    # Validate rules
    valid_task_types = [
        "architecture_design", "code_generation", "pm_analysis",
        "qa_testing", "security_scan", "devops_setup",
        "marketing_copy", "sales_response", "evolution_analysis",
    ]
    for rule in rules:
        if rule.get("task_type") not in valid_task_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task_type '{rule.get('task_type')}'. Must be one of: {valid_task_types}"
            )
        if "timeout_sec" in rule:
            rule["timeout_sec"] = max(10, int(rule["timeout_sec"]))
    
    config["routing_rules"] = rules
    _save_providers_config(config)
    await _reload_llm_router(request)
    
    return {"message": "Routing rules updated", "routing_rules": rules}


class PutProviderLlmPricingBody(BaseModel):
    """USD per 1M tokens for admin cost estimates when model id has no specific rate."""

    usd_per_mtok: float = Field(..., ge=0.0, le=1_000_000.0)


@router.get("/llm-pricing")
async def get_llm_pricing():
    """Per-provider blended $/Mtok for LLM log estimates (YAML override > builtin > global default)."""
    from llm.pricing_estimate import (
        builtin_provider_fallback_usd_per_mtok,
        effective_provider_fallback_usd_per_mtok,
        yaml_override_usd_per_mtok_for_provider,
    )

    config = _load_providers_config()
    providers_out: dict[str, Any] = {}
    for name in sorted(config.get("providers", {}).keys()):
        eff, src = effective_provider_fallback_usd_per_mtok(name)
        providers_out[name] = {
            "effective_usd_per_mtok": eff,
            "source": src,
            "yaml_override_usd_per_mtok": yaml_override_usd_per_mtok_for_provider(name),
            "builtin_usd_per_mtok": builtin_provider_fallback_usd_per_mtok(name),
        }
    return {"providers": providers_out}


@router.put("/llm-pricing/providers/{provider_name}")
async def put_llm_pricing_provider(provider_name: str, body: PutProviderLlmPricingBody):
    """Set YAML override for provider-tier cost estimate (writes ``data/config/llm_pricing.yaml``)."""
    config = _load_providers_config()
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    from llm.pricing_estimate import write_llm_pricing_provider_rate

    try:
        write_llm_pricing_provider_rate(provider_name, body.usd_per_mtok)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "provider": provider_name, "usd_per_mtok": body.usd_per_mtok}


@router.delete("/llm-pricing/providers/{provider_name}")
async def delete_llm_pricing_provider_override(provider_name: str):
    """Remove YAML override so built-in / global default applies again."""
    config = _load_providers_config()
    if provider_name not in config.get("providers", {}):
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    from llm.pricing_estimate import write_llm_pricing_provider_rate

    try:
        write_llm_pricing_provider_rate(provider_name, None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "provider": provider_name, "cleared": True}


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
    if _admin_use_sqlite_pipeline() and _admin_sqlite_db_path().exists():
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
        pipeline_path = Path("/app/data/state/pipeline.json")
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
                pass

    # Load agent logs for last_active
    log_dir = Path("/app/data/logs")
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
                    pass

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
    legacy_file = Path("/app/data/logs/audit.jsonl")
    if legacy_file.exists():
        try:
            with open(legacy_file, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass

    # 2. AuditLogger directory (hash-chained format)
    audit_dir = Path("/app/data/logs/audit")
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
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass

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
    from llm.pricing_estimate import enrich_llm_log_entry

    limit = max(1, min(int(limit or 100), 2000))
    offset = max(0, min(int(offset or 0), 2_000_000))
    log_file = Path("/app/data/logs/llm_calls.jsonl")
    indexed: list[tuple[int, dict]] = []
    use_time_range = since is not None or until is not None

    if log_file.exists():
        with open(log_file, "r") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if line:
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
                    except json.JSONDecodeError:
                        pass

    # Newest first; larger line_no wins on timestamp ties (later JSONL line = newer).
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


@router.get("/director/reports")
async def get_director_reports():
    """Get Director AI reports list."""
    reports_dir = Path("/app/data/reports/director")
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
    report_file = Path(f"/app/data/reports/director/{filename}")
    if not report_file.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    
    with open(report_file, "r") as f:
        content = f.read()
    
    return {"filename": filename, "content": content}


# ── Developer handoff (what the Developer agent receives) ──────────────────


def _load_analyst_brief_for_developer(product_id: str) -> str:
    """Analyst-authored handoff in state/{id}/market_research.json (same as DeveloperAgent)."""
    path = Path(f"/app/data/state/{product_id}/market_research.json")
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
    pipeline_file = Path("/app/data/state/pipeline.json")
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
    if _admin_use_sqlite_pipeline() and _admin_sqlite_db_path().exists():
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
    spec_file = Path(f"/app/data/specs/{product_id}/specification.json")
    if spec_file.exists():
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            spec = None
    arch_file = Path(f"/app/data/arch/{product_id}/architecture.json")
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

    marketing_file = Path(f"/app/data/state/{product_id}/marketing_content.json")
    if marketing_file.exists():
        try:
            marketing = json.loads(marketing_file.read_text(encoding="utf-8"))
            category = marketing.get("category", category)
            tags = marketing.get("tags", tags)
        except (json.JSONDecodeError, OSError):
            pass

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


# ── Pipeline Products (Admin) ──────────────────────────────────────────────

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
    pipeline_file = Path("/app/data/state/pipeline.json")
    products: dict = {}
    task_queue: list = []

    loaded_sqlite = False
    if _admin_use_sqlite_pipeline() and _admin_sqlite_db_path().exists():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            for row in sm.get_all_products():
                pid = row.get("id")
                if pid:
                    products[pid] = row
            for t in sm.get_all_tasks():
                task_queue.append(_normalize_pipeline_task(t))
            sm.close()
            loaded_sqlite = True
            logger.debug(
                "Admin pipeline products: loaded %s products, %s tasks from SQLite",
                len(products),
                len(task_queue),
            )
        except Exception as e:
            logger.warning("Admin pipeline products: SQLite load failed (%s), falling back to JSON", e)

    if not loaded_sqlite:
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
                    "storefront_listable_products": 0,
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
                    "storefront_listable_products": 0,
                    "light": light,
                    "sort": sort,
                },
            }

    try:
        
        # Build task lookup per product
        tasks_by_product: dict[str, list] = {}
        for t in task_queue:
            pid = t.get("product_id", "")
            if pid not in tasks_by_product:
                tasks_by_product[pid] = []
            tasks_by_product[pid].append(t)
        
        # Sort products first and only hydrate the requested window (faster first paint).
        safe_offset = max(offset, 0)
        safe_limit = max(limit, 1)
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
        storefront_listable = 0
        try:
            storefront_listable = count_showcase_listable_products()
        except Exception as ex:
            logger.warning("pipeline products: storefront listable count failed (%s)", ex)
            storefront_listable = 0

        window = all_items[safe_offset:safe_offset + safe_limit]

        result = []
        for pid, product in window:
            meta = product.get("metadata") or {}
            # Load spec / arch — prefer disk artifacts unless ``light`` (Pipeline Monitor catalog).
            spec = None
            arch = None
            if light:
                spec = product.get("spec") or meta.get("spec")
                arch = product.get("architecture") or meta.get("architecture")
            else:
                spec_file = Path(f"/app/data/specs/{pid}/specification.json")
                if spec_file.exists():
                    try:
                        spec = json.loads(spec_file.read_text())
                    except Exception:
                        pass
                if spec is None:
                    spec = product.get("spec") or meta.get("spec")

                arch_file = Path(f"/app/data/arch/{pid}/architecture.json")
                if arch_file.exists():
                    try:
                        arch = json.loads(arch_file.read_text())
                    except Exception:
                        pass
                if arch is None:
                    arch = product.get("architecture") or meta.get("architecture")

            product_tasks = tasks_by_product.get(pid, [])
            completed_tasks = sum(1 for t in product_tasks if t.get("status") == "completed")
            failed_tasks = sum(1 for t in product_tasks if t.get("status") == "failed")
            running_tasks = sum(1 for t in product_tasks if t.get("status") == "running")
            pending_tasks = sum(1 for t in product_tasks if t.get("status") == "pending")
            failed_task_errors = [
                str(t.get("error") or "").strip()
                for t in product_tasks
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
                marketing_file = Path(f"/app/data/state/{pid}/marketing_content.json")
                if marketing_file.exists():
                    try:
                        marketing = json.loads(marketing_file.read_text())
                        category = marketing.get("category", category)
                        tags = marketing.get("tags", tags)
                        inner = marketing.get("marketing")
                        if isinstance(inner, dict):
                            storefront_marketing_copy = inner
                    except Exception:
                        pass

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
                "tasks": product_tasks,
                "task_counts": {
                    "total": len(product_tasks),
                    "completed": completed_tasks,
                    "failed": failed_tasks,
                    "running": running_tasks,
                    "pending": pending_tasks,
                },
                "failure_reason": product.get("failure_reason") or meta.get("failure_reason"),
                "last_error": product.get("error") or meta.get("error"),
                "failed_task_errors": failed_task_errors,
                "quality_repair_round": product.get("quality_repair_round"),
                "storefront_visible": storefront_visible,
                "storefront_gate_reasons": storefront_gate_reasons,
                "storefront_followup": storefront_followup,
                "storefront_marketing_copy": storefront_marketing_copy,
            }
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
        # Single pass over llm_calls.jsonl for all visible products.
        try:
            visible_ids = {r["id"] for r in result}
            eco_map = get_product_llm_costs(visible_ids)
            for r in result:
                pid = r["id"]
                eco = eco_map.get(pid)
                if eco is not None:
                    r["economics"] = eco
                    # Quality score from storefront followup (human, 1‑5) or fallback
                    sf_q = r.get("storefront_followup", {}) or {}
                    qs = sf_q.get("quality_score")
                    try:
                        qs_f = float(qs) if qs is not None else None
                    except (TypeError, ValueError):
                        qs_f = None
                    r["economics"]["roi_band"] = compute_roi_band(
                        eco.get("llm_cost_usd"), qs_f,
                    )
                    r["economics"]["quality_score"] = qs_f
                else:
                    r["economics"] = {
                        "llm_cost_usd": 0.0,
                        "llm_call_count": 0,
                        "llm_total_tokens": 0,
                        "llm_agent_breakdown": {},
                        "quality_score": None,
                        "roi_band": compute_roi_band(0.0, None),
                    }
        except Exception as eco_err:
            logger.warning("Product economics enrichment failed: %s", eco_err)

        try:
            dr = factory_data_root()
            for r in result:
                try:
                    r["pulse"] = build_product_pulse(r, light=light, data_root=dr)
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
        record = validate_and_save(
            product_id,
            followup=body.followup,
            planned_notes=body.planned_notes,
            not_pursuing_reason=body.not_pursuing_reason,
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
    mkt_path = Path(f"/app/data/state/{product_id}/marketing_content.json")
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


_FILES_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "target",
        ".cargo",
        ".eggs",
        "site-packages",
    }
)
_FILES_MAX_PER_CATEGORY = 4000
_FILES_PREVIEW_MAX_CHARS = 5000
_FILES_PREVIEW_READ_BYTES = 262_144
_FILES_PREVIEW_SKIP_BYTES = 8 * 1024 * 1024

# Owner ZIP: same skip rules as file browser; higher per-category cap; skip individual huge blobs.
_PRODUCT_OWNER_EXPORT_MAX_FILES_PER_CATEGORY = 15_000
_PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES = 512 * 1024 * 1024


def _sanitize_admin_product_id(product_id: str) -> str:
    pid = (product_id or "").strip()
    if not pid or len(pid) > 220:
        raise HTTPException(status_code=400, detail="Invalid product id")
    if "/" in pid or "\\" in pid or pid.startswith(".") or ".." in pid:
        raise HTTPException(status_code=400, detail="Invalid product id")
    return pid


def _admin_product_artifact_category_dirs(product_id: str) -> dict[str, Path]:
    dr = factory_data_root()
    return {
        "specs": dr / "specs" / product_id,
        "architecture": dr / "arch" / product_id,
        "code": dr / "code" / product_id,
        "bugs": dr / "bugs" / product_id,
        "security": dr / "security" / product_id,
        "marketing": dr / "state" / product_id,
        "telemetry": dr / "telemetry" / product_id,
    }


def _walk_artifact_files(
    category_root: Path, *, max_files: int = _FILES_MAX_PER_CATEGORY
) -> tuple[list[Path], bool]:
    """List files under category_root, skipping heavy vendor/tool dirs. Returns (paths, truncated)."""
    if not category_root.exists() or not category_root.is_dir():
        return [], False
    out: list[Path] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(
        category_root, topdown=True, followlinks=False
    ):
        dirnames[:] = sorted(d for d in dirnames if d not in _FILES_SKIP_DIR_NAMES)
        for name in sorted(filenames):
            if len(out) >= max_files:
                return out, True
            out.append(Path(dirpath) / name)
    return out, truncated


def _unlink_path_quiet(p: str) -> None:
    try:
        Path(p).unlink(missing_ok=True)
    except OSError:
        pass


def _build_product_owner_export_zip(
    product_id: str,
) -> tuple[Path, str]:
    """Write a temporary ZIP and return (path, suggested_download_filename)."""
    dirs = _admin_product_artifact_category_dirs(product_id)
    merged = _admin_merged_pipeline_product(product_id)
    skipped_large: list[dict[str, Any]] = []
    truncated_by_category: dict[str, bool] = {}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    safe_slug = product_id.replace("/", "_")[:180]
    filename = f"aicom-product-{safe_slug}-{ts}.zip"

    fd, tmp_path = tempfile.mkstemp(prefix="aicom-owner-export-", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for category, dir_path in dirs.items():
                paths, truncated = _walk_artifact_files(
                    dir_path, max_files=_PRODUCT_OWNER_EXPORT_MAX_FILES_PER_CATEGORY
                )
                if truncated:
                    truncated_by_category[category] = True
                for fpath in paths:
                    if not fpath.is_file():
                        continue
                    try:
                        size_bytes = fpath.stat().st_size
                    except OSError:
                        continue
                    if size_bytes > _PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES:
                        skipped_large.append(
                            {
                                "category": category,
                                "path": str(fpath),
                                "size_bytes": size_bytes,
                                "reason": f"file larger than {_PRODUCT_OWNER_EXPORT_MAX_FILE_BYTES} bytes",
                            }
                        )
                        continue
                    try:
                        arc = f"{category}/{fpath.relative_to(dir_path).as_posix()}"
                    except ValueError:
                        arc = f"{category}/{fpath.name}"
                    zf.write(fpath, arcname=arc)

            manifest: dict[str, Any] = {
                "product_id": product_id,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "pipeline_product": merged,
                "truncated_by_category": truncated_by_category or None,
                "skipped_large_files": skipped_large or None,
                "layout": {
                    "specs": "specs/… (specification and PM artifacts)",
                    "architecture": "architecture/… (from data/arch)",
                    "code": "code/… (generated site / app tree)",
                    "bugs": "bugs/… (QA reports)",
                    "security": "security/…",
                    "marketing": "marketing/… (from data/state — storefront copy, marketing JSON)",
                    "telemetry": "telemetry/…",
                },
            }
            zf.writestr(
                "EXPORT_MANIFEST.json",
                (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            )
            readme = (
                "AI Factory — owner product export (single product, on-disk artifacts).\n"
                "This is not a full factory backup. Folders mirror Admin → Files categories.\n"
                "Open EXPORT_MANIFEST.json for pipeline row snapshot and any skip/truncation notes.\n\n"
                "Экспорт одного продукта для владельца фабрики (артефакты на диске), не бэкап всего инстанса.\n"
            )
            zf.writestr("README_OWNER_EXPORT.txt", readme.encode("utf-8"))
    except Exception:
        _unlink_path_quiet(tmp_path)
        raise

    return Path(tmp_path), filename


def _preview_artifact_file(fpath: Path, *, size_bytes: int | None = None) -> tuple[str | None, str | None]:
    """Return (preview, error); exactly one side is set (preview may be empty string)."""
    try:
        size = fpath.stat().st_size if size_bytes is None else size_bytes
    except OSError as e:
        return None, str(e)
    if size == 0:
        return "", None
    if size > _FILES_PREVIEW_SKIP_BYTES:
        return None, "file too large for preview (body not read)"
    try:
        data = fpath.read_bytes()[:_FILES_PREVIEW_READ_BYTES]
    except OSError as e:
        return None, str(e)
    if b"\x00" in data[:8192]:
        return None, "binary file (preview skipped)"
    text = data.decode("utf-8", errors="replace")
    if len(text) > _FILES_PREVIEW_MAX_CHARS:
        return text[:_FILES_PREVIEW_MAX_CHARS] + "\n... (truncated)", None
    if len(data) < size:
        return text + "\n... (truncated; file larger than preview read limit)", None
    return text, None


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
    spec_file = Path(f"/app/data/specs/{product_id}/specification.json")
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
    logs_dir = Path("/app/data/logs")
    all_logs: list[dict[str, Any]] = []

    if not logs_dir.exists():
        return {"logs": [], "count": 0, "total": 0}

    agent_files = list(logs_dir.glob("*.jsonl"))
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
                        except json.JSONDecodeError:
                            pass
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

    reports_dir = Path("/app/data/reports/director")

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


@router.get("/discovery/ideas")
async def get_discovery_ideas(limit: int = 20):
    """Read latest ranked discovery opportunities for admin Idea Queue UI."""
    ranked_file = Path("/app/data/discovery/ranked_ideas.json")
    if not ranked_file.exists():
        return {"generated_at": None, "ranked_ideas": [], "count": 0, "signals_total": 0}
    try:
        payload = json.loads(ranked_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read discovery ideas: {exc}")
    ideas = payload.get("ranked_ideas") if isinstance(payload.get("ranked_ideas"), list) else []
    n = max(1, min(int(limit), 100))
    source_health = {}
    source_health_file = Path("/app/data/discovery/source_health.json")
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
    scorecard_path = Path("/app/data/reports/benchmark_scorecard.json")
    alerts_path = Path("/app/data/reports/benchmark_alerts.json")
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
    status_path = Path("/app/data/state/benchmark_status.json")
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
    spec_path = Path(f"/app/data/specs/{product_id}/specification.json")
    if not spec_path.exists():
        return None
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = raw.get("specification")
        return spec if isinstance(spec, dict) else None
    except Exception:
        return None


def _write_spec_name(product_id: str, new_name: str) -> bool:
    spec_path = Path(f"/app/data/specs/{product_id}/specification.json")
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
    mkt_path = Path(f"/app/data/state/{product_id}/marketing_content.json")
    if not mkt_path.exists():
        return None
    try:
        raw = json.loads(mkt_path.read_text(encoding="utf-8"))
        m = raw.get("marketing")
        return m if isinstance(m, dict) else None
    except Exception:
        return None


def _write_marketing_name(product_id: str, new_name: str) -> bool:
    mkt_path = Path(f"/app/data/state/{product_id}/marketing_content.json")
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
    p = Path("/app/data/state/pipeline.json")
    if not p.exists():
        return {"products": {}, "task_queue": [], "current_task_id": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"products": {}, "task_queue": [], "current_task_id": None}


def _write_pipeline_state(state: dict[str, Any]) -> bool:
    p = Path("/app/data/state/pipeline.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


@router.post("/compliance/remediate-now")
async def run_catalog_compliance_remediation():
    """
    Full hardening sweep:
    - normalize/uniquify names
    - reroute non-compliant released products to DEV_FIXING
    - persist task/state changes immediately
    """
    state = _read_pipeline_state()
    products = state.get("products")
    task_queue = state.get("task_queue")
    if not isinstance(products, dict):
        products = {}
    if not isinstance(task_queue, list):
        task_queue = []

    report = harden_catalog_products(
        products=products,
        task_queue=task_queue,
        data_root="/app/data",
        now=time.time(),
    )
    state["products"] = products
    state["task_queue"] = task_queue
    saved = _write_pipeline_state(state)
    if saved:
        sync_sqlite_from_pipeline_json()
    return {
        **report,
        "state_persisted": saved,
    }
