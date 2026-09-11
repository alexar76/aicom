"""Aggregate public production metrics from Factory + Hub (+ optional peers)."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import httpx

from core.logging_utils import log_suppressed

logger = __import__("logging").getLogger(__name__)

_FACTORY_STARTED_AT = time.time()
_INCIDENTS_PATH = Path(__file__).resolve().parents[3] / "docs" / "production-incidents.json"


def factory_started_at() -> float:
    return _FACTORY_STARTED_AT


def factory_uptime_seconds() -> int:
    return int(time.time() - _FACTORY_STARTED_AT)


def _hub_public_url() -> str:
    return (
        os.getenv("AIMARKET_HUB_PUBLIC_URL")
        or os.getenv("HUB_PUBLIC_URL")
        or "https://modelmarket.dev"
    ).rstrip("/")


def _monitor_public_url() -> str:
    return (os.getenv("ALIEN_MONITOR_PUBLIC_URL") or "").rstrip("/")


def _parse_ts(iso: str) -> float | None:
    try:
        from datetime import datetime, timezone

        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return None


def enrich_hub_summary(summary: dict[str, Any], events: list[Any]) -> dict[str, Any]:
    """Backfill 1h/24h SLO fields when the hub DB schema predates windowed aggregates."""
    out = dict(summary)
    if out.get("invocations_24h"):
        return out
    now = time.time()
    latencies_24h: list[float] = []
    inv_1h = inv_24h = failed_24h = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ts = _parse_ts(str(ev.get("timestamp") or ""))
        if ts is None:
            continue
        age = now - ts
        if age > 86400:
            continue
        inv_24h += 1
        if not ev.get("success", 1):
            failed_24h += 1
        if age <= 3600:
            inv_1h += 1
        try:
            latencies_24h.append(float(ev.get("latency_ms") or 0))
        except (TypeError, ValueError):
            pass
    if inv_24h:
        out.setdefault("invocations_24h", inv_24h)
        out.setdefault("invocations_1h", inv_1h)
        out.setdefault("failed_invocations_24h", failed_24h)
        out.setdefault("rps_1h", round(inv_1h / 3600.0, 4) if inv_1h else 0.0)
        if latencies_24h:
            latencies_24h.sort()
            p50_i = max(0, int(math.ceil(len(latencies_24h) * 0.5)) - 1)
            p95_i = max(0, int(math.ceil(len(latencies_24h) * 0.95)) - 1)
            out.setdefault("p50_latency_ms_24h", round(latencies_24h[p50_i], 1))
            out.setdefault("p95_latency_ms_24h", round(latencies_24h[p95_i], 1))
    return out


def _load_incidents() -> list[dict[str, Any]]:
    if not _INCIDENTS_PATH.is_file():
        return []
    try:
        raw = json.loads(_INCIDENTS_PATH.read_text(encoding="utf-8"))
        items = raw.get("incidents") if isinstance(raw, dict) else raw
        return [i for i in (items or []) if isinstance(i, dict)]
    except Exception as exc:
        log_suppressed(logger, "load production incidents", exc_info=exc)
        return []


async def _fetch_json(client: httpx.AsyncClient, url: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        data = r.json()
        return data if isinstance(data, dict) else None, None
    except Exception as exc:
        return None, str(exc)[:200]


async def build_public_ecosystem_status() -> dict[str, Any]:
    """Return a single JSON document for docs, landing pages, and smoke checks."""
    hub_url = _hub_public_url()
    monitor_url = _monitor_public_url()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    out: dict[str, Any] = {
        "collected_at": now,
        "sources": {
            "factory": "local",
            "hub": hub_url,
        },
        "services": {},
        "hub": {},
        "pipeline": {},
        "incidents": _load_incidents(),
        "errors": [],
    }

    # Factory (local process)
    out["services"]["factory"] = {
        "status": "ok",
        "url": os.getenv("PUBLIC_SITE_URL", "https://magic-ai-factory.com"),
        "uptime_seconds": factory_uptime_seconds(),
    }

    try:
        from orchestrator.sqlite_manager import SQLiteManager
        from core.paths import pipeline_db_path

        db_path = pipeline_db_path()
        if db_path.is_file():
            sm = SQLiteManager(str(db_path))
            sm.connect()
            try:
                counts = sm.get_catalog_summary_counts()
                metrics = sm.get_metrics()
            finally:
                sm.close()
            out["pipeline"] = {
                "products_total": int(counts.get("total") or 0),
                "products_shipped": int(counts.get("shipped") or 0),
                "products_failed": int(counts.get("failed") or 0),
                "products_in_pipeline": max(
                    0,
                    int(counts.get("total") or 0) - int(counts.get("shipped") or 0),
                ),
                "pending_tasks": int(metrics.get("pending_tasks") or 0),
                "running_tasks": int(metrics.get("running_tasks") or 0),
                "timeout_tasks": int(metrics.get("timeout_tasks") or 0),
            }
    except Exception as exc:
        out["errors"].append(f"pipeline: {exc}")

    timeout = float(os.getenv("PUBLIC_METRICS_FETCH_TIMEOUT", "8"))
    factory_public = (os.getenv("PUBLIC_SITE_URL") or "https://magic-ai-factory.com").rstrip("/")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if not out.get("pipeline"):
            pipe, pipe_err = await _fetch_json(
                client, f"{factory_public}/api/public/pipeline-status"
            )
            if pipe and not pipe_err:
                shipped = int(pipe.get("products_shipped") or 0)
                in_pipe = int(pipe.get("products_in_pipeline") or 0)
                out["pipeline"] = {
                    "products_shipped": shipped,
                    "products_in_pipeline": in_pipe,
                    "products_total": shipped + in_pipe,
                }
            elif pipe_err:
                out["errors"].append(f"pipeline remote: {pipe_err}")

        hub_live, hub_err = await _fetch_json(
            client, f"{hub_url}/ai-market/v2/stats/live?limit=200"
        )
        hub_health, hub_health_err = await _fetch_json(
            client, f"{hub_url}/ai-market/v2/health"
        )
        if hub_err:
            out["errors"].append(f"hub stats: {hub_err}")
            out["services"]["hub"] = {"status": "degraded", "url": hub_url}
        else:
            summary = enrich_hub_summary(
                dict(hub_live.get("summary") or {}),
                list(hub_live.get("events") or []),
            )
            out["hub"] = summary
            out["services"]["hub"] = {
                "status": "ok",
                "url": hub_url,
                "uptime_seconds": (hub_health or {}).get("uptime_seconds"),
            }
            if hub_health_err:
                out["errors"].append(f"hub health: {hub_health_err}")

        if monitor_url:
            out["sources"]["monitor"] = monitor_url
            mon_health, mon_err = await _fetch_json(client, f"{monitor_url}/api/health")
            if mon_err:
                out["errors"].append(f"monitor: {mon_err}")
                out["services"]["monitor"] = {"status": "degraded", "url": monitor_url}
            else:
                out["services"]["monitor"] = {
                    "status": "ok",
                    "url": monitor_url,
                    "mode": mon_health.get("mode"),
                }

    # Derived SLO-style fields for docs
    hub = out.get("hub") or {}
    inv_24h = int(hub.get("invocations_24h") or 0)
    failed_24h = int(hub.get("failed_invocations_24h") or 0)
    out["slo"] = {
        "rps_1h": hub.get("rps_1h"),
        "p50_latency_ms_24h": hub.get("p50_latency_ms_24h"),
        "p95_latency_ms_24h": hub.get("p95_latency_ms_24h"),
        "success_rate_24h": round(1 - failed_24h / inv_24h, 6) if inv_24h else None,
        "open_incidents": sum(
            1 for i in out["incidents"] if str(i.get("status", "")).lower() == "open"
        ),
    }
    return out
