"""Cost-per-outcome aggregation for admin treemap (product → agent → phase)."""

from __future__ import annotations

import logging
from typing import Any

from web.backend.services.product_economics import get_product_llm_costs

logger = logging.getLogger(__name__)


def _product_title(row: dict[str, Any]) -> str:
    idea = str(row.get("idea") or row.get("name") or "").strip()
    if idea:
        return idea[:64]
    pid = str(row.get("id") or "")
    return f"Product {pid[:8]}" if pid else "Unknown"


def build_cost_outcome_heatmap(*, products: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Treemap-ready payload: each completed/shipped product is a top-level cell
    with children per agent_type.
    """
    shipped = [
        p
        for p in products
        if str(p.get("state") or "").upper() in ("COMPLETED", "DEPLOYED_PRODUCTION")
    ]
    ids = {str(p.get("id") or "") for p in shipped if p.get("id")}
    ids.discard("")
    eco = get_product_llm_costs(ids) if ids else {}

    children: list[dict[str, Any]] = []
    total_usd = 0.0
    for p in shipped:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        row = eco.get(pid) or {}
        cost = float(row.get("llm_cost_usd") or 0)
        total_usd += cost
        agent_children: list[dict[str, Any]] = []
        breakdown = row.get("llm_agent_breakdown") or {}
        if isinstance(breakdown, dict):
            for agent, stats in sorted(breakdown.items(), key=lambda x: -(float((x[1] or {}).get("cost_usd") or 0))):
                if not isinstance(stats, dict):
                    continue
                ac = float(stats.get("cost_usd") or 0)
                if ac <= 0:
                    continue
                agent_children.append(
                    {
                        "name": agent,
                        "value": round(ac, 4),
                        "calls": int(stats.get("calls") or 0),
                        "tokens": int(stats.get("tokens") or 0),
                    }
                )
        children.append(
            {
                "name": _product_title({**p, "id": pid}),
                "product_id": pid,
                "state": p.get("state"),
                "value": round(cost, 4),
                "llm_cost_usd": round(cost, 4),
                "llm_call_count": int(row.get("llm_call_count") or 0),
                "has_llm_data": int(row.get("llm_call_count") or 0) > 0,
                "agents": agent_children,
            }
        )

    children.sort(key=lambda x: -(x.get("value") or 0))
    return {
        "name": "factory",
        "value": round(total_usd, 4),
        "product_count": len(children),
        "children": children,
        "unit": "USD",
    }
