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

logger = logging.getLogger(__name__)

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

# ── Helpers ──────────────────────────────────────────────────────────────────

METRICS_HISTORY_FILE = str(metrics_history_path())


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
    from core.pipeline_database import pipeline_uses_sql_store

    return pipeline_uses_sql_store()


def _admin_sql_store_available() -> bool:
    from core.pipeline_database import pipeline_database_url, pipeline_db_backend

    if pipeline_db_backend() == "postgres":
        return bool(pipeline_database_url())
    return _admin_sqlite_db_path().exists()


def _admin_sqlite_db_path() -> Path:
    return pipeline_db_path()


def _normalize_pipeline_task(task: dict) -> dict:
    """SQLite stores statuses upper-case; pipeline.json uses lower-case."""
    t = dict(task)
    st = t.get("status")
    if isinstance(st, str):
        t["status"] = st.lower()
    return t


def _slim_pipeline_task_payloads_for_light_catalog(tasks: list[dict]) -> list[dict]:
    """Strip heavy agent I/O blobs from embedded tasks (``light=true`` catalog / Pipeline Monitor)."""
    out: list[dict] = []
    for t in tasks:
        d = dict(t)
        d["input_data"] = {}
        d["output_data"] = {}
        out.append(d)
    return out


def _slim_spec_arch_for_light_catalog(spec: Any, arch: Any) -> tuple[Any, Any]:
    """Keep only card-sized fields so SQLite-embedded specs do not megabyte-scale JSON responses."""
    s_out: Any = spec
    if isinstance(spec, dict):
        s_out = {k: spec[k] for k in ("product_name", "description", "delivery_profile") if k in spec}
    a_out: Any = arch
    if isinstance(arch, dict):
        ts = arch.get("tech_stack")
        summ = arch.get("summary")
        a_out = {}
        if isinstance(ts, (dict, list)):
            a_out["tech_stack"] = ts
        if isinstance(summ, str) and summ.strip():
            a_out["summary"] = summ.strip()[:2000]
        if not a_out:
            a_out = None
    return s_out, a_out


def _pipeline_failed_alerts(*, limit: int = 12) -> list[dict[str, Any]]:
    """Recent FAILED products with human-readable cause for dashboard banner."""
    lim = max(1, min(int(limit), 50))
    alerts: list[dict[str, Any]] = []

    def _row_to_alert(pid: str, product: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
        report = build_failure_report(product, tasks)
        idea = str(product.get("idea") or "")
        title = idea.strip()[:80] or pid
        if len(idea.strip()) > 80:
            title += "…"
        return {
            "product_id": pid,
            "title": title,
            "idea": idea[:500],
            "updated_at": float(product.get("updated_at") or 0),
            "headline": report.get("headline"),
            "cause_plain": report.get("cause_plain"),
            "failure_reason": failure_reason_from_product(product) or report.get("failure_reason"),
            "failed_agent": report.get("failed_agent"),
        }

    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from orchestrator.sqlite_manager import SQLiteManager

            sm = SQLiteManager(str(_admin_sqlite_db_path()))
            sm.connect()
            try:
                ws = sm.workspace_id
                rows = sm.conn.execute(
                    """
                    SELECT id FROM products
                    WHERE workspace_id = ? AND upper(trim(state)) = 'FAILED'
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (ws, lim),
                ).fetchall()
                for row in rows:
                    pid = str(row["id"])
                    product = sm.get_product(pid)
                    if not product:
                        continue
                    tasks = sm.get_tasks_by_product(pid)
                    alerts.append(_row_to_alert(pid, product, tasks))
            finally:
                sm.close()
            return alerts
        except Exception as e:
            logger.debug("dashboard failed_alerts sqlite: %s", e)

    products, task_queue = _load_pipeline_snapshot_for_metrics()
    failed_ids = [
        pid
        for pid, p in products.items()
        if str(p.get("state") or "").strip().upper() == "FAILED"
    ]
    failed_ids.sort(
        key=lambda pid: float(products[pid].get("updated_at") or 0),
        reverse=True,
    )
    for pid in failed_ids[:lim]:
        product = products[pid]
        tasks = [t for t in task_queue if t.get("product_id") == pid]
        alerts.append(_row_to_alert(pid, product, tasks))
    return alerts


async def _fast_pipeline_metrics_async() -> tuple[dict[str, int], dict[str, int]]:
    """
    Aggregate pipeline counts without loading full products/tasks tables (non-blocking SQLite).
    Returns (pipeline_counts, state_distribution).
    """
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from core.pipeline_database import create_async_pipeline_store

            store = create_async_pipeline_store()
            await store.initialize()
            try:
                m = await store.get_metrics()
                state_distribution = await store.get_state_distribution()
            finally:
                await store.close()
            pipeline = {
                "total_products": int(m["total_products"]),
                "active_products": int(m["active_products"]),
                "completed_products": int(m["completed_products"]),
                "failed_products": int(m["failed_products"]),
                "pending_tasks": int(m["pending_tasks"]),
                "running_tasks": int(m["running_tasks"]),
                "timed_out_tasks": int(m.get("timeout_tasks") or 0),
            }
            return pipeline, state_distribution
        except Exception as e:
            logger.warning("Dashboard metrics: async SQL aggregates failed (%s), falling back to snapshot", e)

    return _fast_pipeline_metrics_json()


def _fast_pipeline_metrics_sqlite_sync() -> tuple[dict[str, int], dict[str, int]] | None:
    """Sync SQL aggregates for quick dashboard inside an active event loop."""
    if not (_admin_use_sqlite_pipeline() and _admin_sql_store_available()):
        return None
    try:
        from core.pipeline_database import create_sync_pipeline_manager

        sm = create_sync_pipeline_manager()
        try:
            m = sm.get_metrics()
            state_distribution = sm.get_state_distribution()
        finally:
            sm.close()
        pipeline = {
            "total_products": int(m["total_products"]),
            "active_products": int(m["active_products"]),
            "completed_products": int(m["completed_products"]),
            "failed_products": int(m["failed_products"]),
            "pending_tasks": int(m["pending_tasks"]),
            "running_tasks": int(m["running_tasks"]),
            "timed_out_tasks": int(m.get("timeout_tasks") or 0),
        }
        return pipeline, state_distribution
    except Exception as e:
        logger.warning("Dashboard metrics: sync SQL aggregates failed (%s), falling back to snapshot", e)
        return None


def _fast_pipeline_metrics() -> tuple[dict[str, int], dict[str, int]]:
    """Sync entry: asyncio when no loop; sync SQLite when inside FastAPI; JSON last resort."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_fast_pipeline_metrics_async())
    synced = _fast_pipeline_metrics_sqlite_sync()
    if synced is not None:
        return synced
    return _fast_pipeline_metrics_json()


def _fast_pipeline_metrics_json() -> tuple[dict[str, int], dict[str, int]]:
    """JSON snapshot fallback when SQL store is disabled or async read fails."""
    products, task_queue = _load_pipeline_snapshot_for_metrics()
    total = len(products)
    completed = sum(1 for p in products.values() if is_shipped_pipeline_product_state(p.get("state")))
    failed = sum(1 for p in products.values() if str(p.get("state", "")).strip().lower() == "failed")
    active = max(0, total - completed - failed)
    pending = sum(1 for t in task_queue if _task_status_lower(t) == "pending")
    running = sum(1 for t in task_queue if _task_status_lower(t) == "running")
    timed_out = sum(1 for t in task_queue if _task_status_lower(t) in ("timeout", "timed_out"))
    state_distribution: dict[str, int] = {}
    for p in products.values():
        s = str(p.get("state") or "UNKNOWN")
        state_distribution[s] = state_distribution.get(s, 0) + 1
    return (
        {
            "total_products": total,
            "active_products": active,
            "completed_products": completed,
            "failed_products": failed,
            "pending_tasks": pending,
            "running_tasks": running,
            "timed_out_tasks": timed_out,
        },
        state_distribution,
    )


def _load_pipeline_snapshot_for_metrics() -> tuple[dict[str, Any], list[dict]]:
    """
    Products keyed by id and global task list for dashboard counts.

    When ``USE_SQLITE`` is enabled and ``pipeline.db`` exists, SQLite is the
    source of truth (``pipeline.json`` is often empty or stale). Otherwise
    read ``pipeline.json``.
    """
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        try:
            from core.pipeline_database import create_sync_pipeline_manager

            sm = create_sync_pipeline_manager()
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

    pipeline_file = pipeline_json_path()
    pipeline_data: dict[str, Any] = {"products": {}, "task_queue": []}
    if pipeline_file.exists():
        try:
            with open(pipeline_file, "r") as f:
                pipeline_data = json.load(f)
        except Exception:
            log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)
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
# Not agent execution logs — use GET /admin/llm/logs for llm_calls.jsonl.
_AGENT_LOG_JSONL_SKIP = frozenset({"llm_calls"})


def agent_log_entry_time(entry: dict[str, Any]) -> float:
    t = entry.get("time", 0)
    try:
        return float(t)
    except (TypeError, ValueError):
        return 0.0


def load_agent_execution_logs(
    *,
    agent: str | None = None,
    limit: int = 200,
    since: float | None = None,
    until: float | None = None,
) -> dict[str, Any]:
    """Tail-bounded read of per-agent ``*.jsonl`` under ``logs_dir()`` (excludes ``llm_calls``)."""
    logs_dir_path = logs_dir()
    if not logs_dir_path.exists():
        return {"logs": [], "count": 0, "total": 0}

    all_logs: list[dict[str, Any]] = []
    agent_files = sorted(logs_dir_path.glob("*.jsonl"))
    if agent:
        agent_files = [f for f in agent_files if f.stem == agent]

    for log_file in agent_files:
        if log_file.stem in _AGENT_LOG_JSONL_SKIP:
            continue
        try:
            entries = _read_jsonl_entries_for_agent_log(log_file)
        except Exception as exc:
            logger.warning("Failed to read agent log %s: %s", log_file, exc)
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_agent = str(entry.get("agent") or log_file.stem)
            if agent and entry_agent != agent:
                continue
            row = dict(entry)
            if not row.get("agent"):
                row["agent"] = entry_agent
            all_logs.append(row)

    if since is not None:
        all_logs = [x for x in all_logs if agent_log_entry_time(x) >= since]
    if until is not None:
        all_logs = [x for x in all_logs if agent_log_entry_time(x) <= until]

    all_logs.sort(key=agent_log_entry_time)
    window_total = len(all_logs)
    tail = all_logs[-limit:] if all_logs else []
    return {"logs": tail, "count": len(tail), "total": window_total}


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
    log_dir = logs_dir()
    agents: dict[str, Any] = {}
    if log_dir.exists():
        for log_file in sorted(log_dir.glob("*.jsonl")):
            if log_file.stem in _AGENT_LOG_JSONL_SKIP:
                continue
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
    reports_dir = director_reports_dir()
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
                log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

    # Check pending decisions
    decisions_file = director_decisions_path()
    pending_count = 0
    if decisions_file.exists():
        try:
            with open(decisions_file, "r") as f:
                data = json.load(f)
            pending_count = len(data.get("pending", []))
        except Exception:
            log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

    benchmark_scorecard = None
    benchmark_alert_count = 0
    if include_benchmark_payload and benchmark_scorecard_path().exists():
        try:
            benchmark_scorecard = json.loads(benchmark_scorecard_path().read_text(encoding="utf-8"))
        except Exception:
            log_suppressed(logger, "dashboard: benchmark scorecard read failed", exc_info=True)
            benchmark_scorecard = None
    if benchmark_alerts_path().exists():
        try:
            alerts_doc = json.loads(benchmark_alerts_path().read_text(encoding="utf-8"))
            benchmark_alert_count = len(alerts_doc.get("alerts") or [])
        except Exception:
            log_suppressed(logger, "dashboard: benchmark alerts read failed", exc_info=True)
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
    log_file = escalations_log_path()
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
                            except json.JSONDecodeError as _suppressed_exc:
                                log_suppressed(logger, "non-fatal (web/backend/api/admin/dashboard.py)", exc_info=_suppressed_exc)
        except Exception:
            log_suppressed(logger, "dashboard: non-fatal error", exc_info=True)

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


def _circuit_breaker_provider_names() -> list[str]:
    names: list[str] = []
    try:
        path = model_providers_path()
        ensure_model_providers_file(path)
        if path.is_file():
            import yaml

            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            names = sorted((cfg.get("providers") or {}).keys())
    except Exception:
        log_suppressed(logger, "circuit_breaker: load provider names", exc_info=True)
    return names


def _circuit_breakers_metrics(provider_names: list[str] | None = None) -> dict[str, Any]:
    """Shared circuit breaker snapshot for SSE / WebSocket / dashboard."""
    try:
        from llm.circuit_breaker import get_circuit_store, sync_prometheus_from_snapshot

        names = provider_names if provider_names is not None else _circuit_breaker_provider_names()
        snap = get_circuit_store().snapshot(names or None)
        sync_prometheus_from_snapshot(snap)
        return snap
    except Exception as e:
        logger.warning("circuit_breakers metrics failed: %s", e)
        return {"providers": {}, "config": {}, "updated_at": time.time()}


async def _build_full_metrics_async(*, include_product_pulses: bool = False) -> dict:
    """Build the complete metrics payload (async-safe SQLite aggregates)."""
    pipeline_counts, state_distribution = await _fast_pipeline_metrics_async()

    storefront_visible: int | None = None
    try:
        storefront_visible = count_showcase_listable_products()
    except Exception as e:
        logger.warning("Dashboard metrics: storefront visible count failed (%s)", e)

    # Resource metrics
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.05)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except ImportError:
        cpu = memory = disk = 0

    esc_summary = _collect_escalation_summary()

    product_pulses: dict[str, Any] = {}
    if include_product_pulses:
        try:
            products, task_queue = _load_pipeline_snapshot_for_metrics()
            product_pulses = build_product_pulses_for_metrics(
                products,
                task_queue,
                data_root=factory_data_root(),
            )
        except Exception as e:
            logger.warning("Dashboard metrics: product_pulses failed (%s)", e)

    failed_alerts: list[dict[str, Any]] = []
    try:
        if int(pipeline_counts.get("failed_products") or 0) > 0:
            failed_alerts = _pipeline_failed_alerts(limit=12)
    except Exception as e:
        logger.debug("dashboard failed_alerts: %s", e)

    circuit_snap = _circuit_breakers_metrics()
    factory_floor: dict[str, Any] = {}
    try:
        factory_floor = build_factory_floor_slice(
            sqlite_path=_admin_sqlite_db_path(),
            circuit_breakers=circuit_snap,
        )
    except Exception as e:
        logger.warning("factory_floor metrics: %s", e)

    cost_heatmap: dict[str, Any] = {"name": "factory", "value": 0, "children": []}
    try:
        from orchestrator.sqlite_manager import SQLiteManager

        sm = SQLiteManager(str(_admin_sqlite_db_path()))
        sm.connect()
        rows = sm.conn.execute(
            """
            SELECT id, state, idea FROM products
            WHERE workspace_id = ? AND upper(state) IN ('COMPLETED', 'DEPLOYED_PRODUCTION')
            LIMIT 200
            """,
            (sm.workspace_id,),
        ).fetchall()
        sm.close()
        products = [dict(r) for r in rows]
        cost_heatmap = build_cost_outcome_heatmap(products=products)
    except Exception as e:
        logger.debug("cost heatmap metrics: %s", e)

    return {
        "pipeline": {
            **pipeline_counts,
            "storefront_visible_products": storefront_visible,
            "state_distribution": state_distribution,
            "failed_alerts": failed_alerts,
        },
        "resources": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
        },
        "revenue": compute_dashboard_revenue(str(factory_data_root()), time.time()),
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
        "circuit_breakers": circuit_snap,
        "factory_floor": factory_floor,
        "cost_outcome_heatmap": cost_heatmap,
    }


def _build_full_metrics(*, include_product_pulses: bool = False) -> dict:
    """Sync entry (tests/CLI). Prefer ``_build_full_metrics_async`` inside the web app."""
    return asyncio.run(_build_full_metrics_async(include_product_pulses=include_product_pulses))


def _build_degraded_dashboard_metrics() -> dict:
    """Last-resort dashboard when builders throw (disk full, SQLite lock). Never raises."""
    pipeline_counts: dict[str, int] = {
        "total_products": 0,
        "active_products": 0,
        "completed_products": 0,
        "failed_products": 0,
        "pending_tasks": 0,
        "running_tasks": 0,
        "timed_out_tasks": 0,
    }
    state_distribution: dict[str, int] = {}
    try:
        pipeline_counts, state_distribution = _fast_pipeline_metrics()
    except Exception as e:
        logger.warning("Degraded dashboard: pipeline aggregates failed (%s)", e)

    storefront_visible: int | None = None
    try:
        storefront_visible = count_showcase_listable_products()
    except Exception as e:
        logger.warning("Degraded dashboard: storefront count failed (%s)", e)

    resources = {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0}
    try:
        import psutil

        resources = {
            "cpu_percent": float(psutil.cpu_percent(interval=0.05)),
            "memory_percent": float(psutil.virtual_memory().percent),
            "disk_percent": float(psutil.disk_usage("/").percent),
        }
    except Exception:
        pass

    empty_esc = {
        "total_all_time": 0,
        "recent_1h": 0,
        "by_agent": {},
        "recent_events": [],
    }
    revenue = {"last_24h": 0.0, "last_7d": 0.0, "last_30d": 0.0}
    try:
        revenue = compute_dashboard_revenue(str(factory_data_root()), time.time())
    except Exception as e:
        logger.warning("Degraded dashboard: revenue failed (%s)", e)

    return {
        "pipeline": {
            **pipeline_counts,
            "storefront_visible_products": storefront_visible,
            "state_distribution": state_distribution,
            "failed_alerts": [],
        },
        "resources": resources,
        "revenue": revenue,
        "security": {"status": "healthy", "failed_logins_15min": 0},
        "agent_metrics": {},
        "director_status": {
            "report_count": 0,
            "last_report_time": None,
            "pending_decisions": 0,
            "status": "unknown",
        },
        "escalations": empty_esc,
        "escalation_summary": empty_esc,
        "collected_at": time.time(),
        "demo_replay": metrics_demo_replay_slice(),
        "dashboard_partial": True,
        "dashboard_build_degraded": True,
    }


def _build_quick_dashboard_metrics() -> dict:
    """Lightweight dashboard payload for first paint (SQL aggregates only)."""
    pipeline_counts, state_distribution = _fast_pipeline_metrics()

    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.05)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except ImportError:
        cpu = memory = disk = 0

    empty_esc = {
        "total_all_time": 0,
        "recent_1h": 0,
        "by_agent": {},
        "recent_events": [],
    }

    failed_alerts: list[dict[str, Any]] = []
    try:
        if int(pipeline_counts.get("failed_products") or 0) > 0:
            failed_alerts = _pipeline_failed_alerts(limit=12)
    except Exception as e:
        logger.debug("dashboard quick failed_alerts: %s", e)

    revenue = {"last_24h": 0.0, "last_7d": 0.0, "last_30d": 0.0}
    try:
        revenue = compute_dashboard_revenue(str(factory_data_root()), time.time())
    except Exception as e:
        logger.warning("Quick dashboard: revenue metrics failed (%s)", e)

    director_status = {
        "report_count": 0,
        "last_report_time": None,
        "pending_decisions": 0,
        "status": "unknown",
    }
    try:
        director_status = _collect_director_status(include_benchmark_payload=False)
    except Exception as e:
        logger.warning("Quick dashboard: director_status failed (%s)", e)

    return {
        "pipeline": {
            **pipeline_counts,
            "storefront_visible_products": None,
            "state_distribution": state_distribution,
            "failed_alerts": failed_alerts,
        },
        "resources": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
        },
        "revenue": revenue,
        "security": {
            "status": "healthy",
            "failed_logins_15min": 0,
        },
        "agent_metrics": {},
        "director_status": director_status,
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


def _unlink_path_quiet(p: str) -> None:
    try:
        Path(p).unlink(missing_ok=True)
    except OSError:
        log_suppressed(logger, "dashboard: temp file cleanup failed", exc_info=True)


# ── Enhanced Dashboard Endpoint ─────────────────────────────────────────────

