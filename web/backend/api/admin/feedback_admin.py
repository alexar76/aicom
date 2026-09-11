"""
Admin feedback + telemetry summary endpoints
===========================================
Aggregates feedback and telemetry into small dashboard-friendly payloads.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from web.backend.core.admin_roles import require_admin_with_rbac

router = APIRouter(prefix="/api/admin", tags=["admin-feedback"], dependencies=[Depends(require_admin_with_rbac)])


def _load_feedback_items(limit: int = 5000) -> list[dict[str, Any]]:
    from core.paths import feedback_dir

    fb_dir = feedback_dir()
    if not fb_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for p in sorted(fb_dir.glob("fb-*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


@router.get("/feedback/summary")
async def feedback_summary(
    window_hours: int = Query(168, ge=1, le=24 * 30),
    limit: int = Query(5000, ge=1, le=20000),
):
    now = time.time()
    cutoff = now - (window_hours * 3600)
    items = [x for x in _load_feedback_items(limit=limit) if float(x.get("created_at") or 0) >= cutoff]

    by_class = Counter(str(x.get("classification") or "unknown") for x in items)
    by_product = defaultdict(list)
    for x in items:
        pid = str(x.get("product_id") or "")
        if pid:
            by_product[pid].append(x)

    top_products = []
    for pid, rows in by_product.items():
        ratings = [int(r.get("rating") or 0) for r in rows if isinstance(r.get("rating"), int)]
        avg = (sum(ratings) / max(1, len(ratings))) if ratings else 0.0
        top_products.append(
            {
                "product_id": pid,
                "count": len(rows),
                "avg_rating": round(avg, 2),
                "bugs": sum(1 for r in rows if r.get("classification") == "bug"),
            }
        )
    top_products.sort(key=lambda r: (r["bugs"], r["count"]), reverse=True)

    return {
        "window_hours": window_hours,
        "count": len(items),
        "by_classification": dict(by_class),
        "top_products": top_products[:20],
        "updated_at": now,
    }


@router.get("/telemetry/summary/{product_id}")
async def telemetry_summary_product(product_id: str):
    # Uses TelemetryCollector storage conventions; summarize by reading jsonl via collector when available
    from web.backend.core.telemetry import TelemetryCollector

    tc = TelemetryCollector()
    return tc.get_product_summary(product_id)


@router.get("/telemetry/summary")
async def telemetry_summary_all(limit: int = Query(200, ge=1, le=5000)):
    from web.backend.core.telemetry import TelemetryCollector

    tc = TelemetryCollector()
    all_summ = tc.get_all_products_summary()
    rows = sorted(all_summ.values(), key=lambda x: float(x.get("last_event") or 0), reverse=True)
    return {"count": len(rows), "items": rows[:limit]}


@router.get("/telemetry/replay/{product_id}")
async def telemetry_replay_sessions(product_id: str, limit: int = Query(100, ge=1, le=1000)):
    """
    List session_ids available for replay timeline in this product.
    """
    from core.paths import telemetry_dir

    tdir = telemetry_dir(product_id)
    if not tdir.exists():
        return {"product_id": product_id, "count": 0, "sessions": []}
    sessions: dict[str, dict[str, Any]] = {}
    for f in sorted(tdir.glob("telemetry_*.jsonl"), reverse=True):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                sid = str(row.get("session_id") or "").strip()
                if not sid:
                    continue
                cur = sessions.get(sid) or {"session_id": sid, "event_count": 0, "first_ts": None, "last_ts": None}
                ts = float(row.get("timestamp") or 0)
                cur["event_count"] += 1
                cur["first_ts"] = ts if cur["first_ts"] is None else min(cur["first_ts"], ts)
                cur["last_ts"] = ts if cur["last_ts"] is None else max(cur["last_ts"], ts)
                sessions[sid] = cur
        except Exception:
            continue
    arr = sorted(sessions.values(), key=lambda x: float(x.get("last_ts") or 0), reverse=True)[:limit]
    return {"product_id": product_id, "count": len(arr), "sessions": arr}


@router.get("/telemetry/replay/{product_id}/{session_id}")
async def telemetry_replay_timeline(
    product_id: str,
    session_id: str,
    limit: int = Query(2000, ge=1, le=10000),
):
    """
    Return a timeline of telemetry events for a session (session replay without video).
    """
    from core.paths import telemetry_dir

    tdir = telemetry_dir(product_id)
    if not tdir.exists():
        return {"product_id": product_id, "session_id": session_id, "count": 0, "events": []}
    events: list[dict[str, Any]] = []
    for f in sorted(tdir.glob("telemetry_*.jsonl")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if str(row.get("session_id") or "") != session_id:
                    continue
                events.append(
                    {
                        "timestamp": row.get("timestamp"),
                        "event_type": row.get("event_type"),
                        "data": row.get("data") or {},
                    }
                )
        except Exception:
            continue
    events.sort(key=lambda x: float(x.get("timestamp") or 0))
    if len(events) > limit:
        events = events[-limit:]
    return {"product_id": product_id, "session_id": session_id, "count": len(events), "events": events}

