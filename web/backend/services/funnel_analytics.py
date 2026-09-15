"""Aggregate marketing funnel metrics from JSONL events, leads, orders."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.paths import marketing_logs_dir

logger = logging.getLogger(__name__)

FUNNEL_STAGES = (
    "page_view",
    "product_view",
    "sandbox_click",
    "checkout_click",
    "lead_submit",
    "waitlist_submit",
    "paid",
)


def _read_events_since(path: Path, since: float) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if float(row.get("ts") or 0) >= since:
                    rows.append(row)
    except OSError as e:
        logger.warning("funnel analytics read failed %s: %s", path, e)
    return rows


def _count_orders_since(since: float) -> int:
    try:
        from core.paths import data_root

        orders_file = data_root() / "orders.json"
        if not orders_file.is_file():
            return 0
        data = json.loads(orders_file.read_text(encoding="utf-8"))
        orders = data if isinstance(data, list) else data.get("orders") or []
        n = 0
        for o in orders:
            if not isinstance(o, dict):
                continue
            ts = float(o.get("created_at") or o.get("paid_at") or 0)
            if ts >= since and str(o.get("status") or "").lower() in ("paid", "completed", "confirmed"):
                n += 1
        return n
    except Exception:
        return 0


def _pipeline_counts() -> dict[str, int]:
    try:
        from core.pipeline_state_writer import read_pipeline_state
        from core.paths import pipeline_json_path

        state = read_pipeline_state(json_path=pipeline_json_path())
        products = state.get("products") or {}
        completed = sum(
            1
            for p in products.values()
            if str((p or {}).get("state") or "").upper() in ("COMPLETED", "DEPLOYED_PRODUCTION")
        )
        in_progress = sum(
            1
            for p in products.values()
            if str((p or {}).get("state") or "").upper() not in ("COMPLETED", "DEPLOYED_PRODUCTION", "FAILED", "CANCELLED")
        )
        failed = sum(1 for p in products.values() if str((p or {}).get("state") or "").upper() == "FAILED")
        return {"completed": completed, "in_progress": in_progress, "failed": failed, "total": len(products)}
    except Exception:
        return {"completed": 0, "in_progress": 0, "failed": 0, "total": 0}


def build_funnel_metrics(*, window_hours: int = 168) -> dict[str, Any]:
    """Public + admin funnel snapshot."""
    since = time.time() - max(1, window_hours) * 3600
    log_dir = marketing_logs_dir()
    events = _read_events_since(log_dir / "events.jsonl", since)

    stage_counts: dict[str, int] = {s: 0 for s in FUNNEL_STAGES}
    by_referral: dict[str, dict[str, int]] = {}
    product_views: dict[str, int] = {}

    for ev in events:
        name = str(ev.get("event") or "")
        if name in stage_counts:
            stage_counts[name] += 1
        ref = str(ev.get("referral") or "direct")
        by_referral.setdefault(ref, {})
        by_referral[ref][name] = by_referral[ref].get(name, 0) + 1
        pid = ev.get("product_id")
        if name == "product_view" and pid:
            product_views[str(pid)] = product_views.get(str(pid), 0) + 1

    paid = _count_orders_since(since)
    stage_counts["paid"] = paid

    leads_count = 0
    try:
        from web.backend.services.funnel_store import list_leads

        leads_count = sum(1 for l in list_leads(2000) if float(l.get("created_at") or 0) >= since)
    except Exception:
        pass

    pipeline = _pipeline_counts()
    pv = stage_counts.get("page_view") or 0
    checkout = stage_counts.get("checkout_click") or 0
    conversion_pct = round(100.0 * paid / checkout, 1) if checkout else None
    sandbox = stage_counts.get("sandbox_click") or 0
    sandbox_rate = round(100.0 * sandbox / max(1, stage_counts.get("product_view") or 0), 1)

    return {
        "window_hours": window_hours,
        "generated_at": time.time(),
        "stages": stage_counts,
        "leads_submitted": leads_count,
        "pipeline": pipeline,
        "rates": {
            "sandbox_from_product_view_pct": sandbox_rate,
            "paid_from_checkout_click_pct": conversion_pct,
        },
        "top_product_views": sorted(product_views.items(), key=lambda x: -x[1])[:10],
        "referrals": {k: v for k, v in sorted(by_referral.items(), key=lambda x: -sum(x[1].values()))[:15]},
    }


def public_trust_metrics() -> dict[str, Any]:
    """Homepage trust strip — safe to expose publicly."""
    metrics = build_funnel_metrics(window_hours=24 * 7)
    stages = metrics.get("stages") or {}
    pipeline = metrics.get("pipeline") or {}
    return {
        "products_shipped": int(pipeline.get("completed") or 0),
        "products_in_pipeline": int(pipeline.get("in_progress") or 0),
        "sandbox_sessions_7d": int(stages.get("sandbox_click") or 0),
        "storefront_views_7d": int(stages.get("product_view") or 0),
        "leads_7d": int(metrics.get("leads_submitted") or 0),
        "paid_orders_7d": int(stages.get("paid") or 0),
    }
