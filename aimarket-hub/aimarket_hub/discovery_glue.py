"""Discovery ↔ AIMarket glue.

Before launching the pipeline, the Discovery agent searches the hub for:
- Data-as-capability: market signals, trends, competitor info
- Existing capabilities that could be reused instead of built from scratch
- Reputation data on relevant providers

Returns enriched context for the pipeline — validated ideas produce better products.

This is the autonomous cycle:
    Discovery finds idea → hub validates with market data →
    pipeline produces product → auto-lists back to hub as capability
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_discovery_with_hub(
    idea: str,
    hub_url: str = "https://modelmarket.dev",
    budget_usd: float = 5.0,
) -> dict[str, Any]:
    """Search the hub for data and signals relevant to an idea.

    Called by the Discovery agent BEFORE launching the pipeline.
    Returns enriched context that helps validate and refine the idea.

    Args:
        idea: The product idea (e.g. "B2B invoice automation landing")
        hub_url: Hub URL to search
        budget_usd: Max budget for data purchases

    Returns:
        Dict with market_signals, reusable_capabilities, competitor_data
    """
    import httpx

    result: dict[str, Any] = {
        "idea": idea,
        "market_signals": [],
        "reusable_capabilities": [],
        "data_available": [],
        "recommendation": "proceed",
        "estimated_data_cost_usd": 0.0,
    }

    try:
        # 1. Search hub for relevant capabilities
        resp = httpx.get(
            f"{hub_url}/ai-market/v2/search",
            params={"intent": idea, "limit": 10},
            timeout=15,
        )
        resp.raise_for_status()
        matches = resp.json().get("matches", [])

        for m in matches:
            cap_id = m.get("capability_id", "")
            desc = m.get("description", "")
            price = m.get("price_per_call_usd", 0)

            # Data capabilities can validate market assumptions
            if "data" in cap_id.lower() or "search" in cap_id.lower():
                result["data_available"].append({
                    "capability_id": cap_id,
                    "description": desc,
                    "price_per_query_usd": price,
                })
                result["estimated_data_cost_usd"] += price

            # Existing capabilities that could be reused
            elif not ("[DEMO]" in desc):
                result["reusable_capabilities"].append({
                    "capability_id": cap_id,
                    "description": desc,
                    "price_per_call_usd": price,
                    "source_hub": m.get("source_hub_name", "unknown"),
                })

        # 2. Check if there's market signal data available
        data_caps = [c for c in result["data_available"] if c["capability_id"]]
        if data_caps:
            result["recommendation"] = "validate_with_data"
            result["suggested_actions"] = [
                f"Query {c['capability_id']} for market signals" for c in data_caps[:3]
            ]

        # 3. Check for competitor/overlap
        similar = [c for c in result["reusable_capabilities"] if any(
            kw in c.get("description", "").lower()
            for kw in idea.lower().split()[:5]
        )]
        if similar:
            result["recommendation"] = "review_overlap"
            result["existing_similar"] = similar[:3]
            result["suggested_actions"] = [
                "Similar capabilities found — review before building",
                *[f"Evaluate {c['capability_id']}" for c in similar[:2]],
            ]

    except Exception as exc:
        logger.warning("Discovery enrichment failed: %s", exc)
        result["recommendation"] = "proceed_without_enrichment"
        result["enrichment_error"] = str(exc)

    return result


def purchase_data_for_discovery(
    capability_id: str,
    query: str,
    hub_url: str = "https://modelmarket.dev",
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Purchase a data query from the hub to validate an idea.

    Uses the factory's channel balance. Returns the purchased data.

    Args:
        capability_id: Data capability to query
        query: What to search for
        hub_url: Hub URL
        channel_id: Factory's pre-funded channel

    Returns:
        Query result with cost breakdown
    """
    import httpx

    try:
        headers = {"Content-Type": "application/json"}
        if channel_id:
            headers["X-Payment-Channel"] = channel_id

        resp = httpx.post(
            f"{hub_url}/ai-market/v2/invoke",
            json={
                "product_id": f"data-{capability_id.split('@')[0]}",
                "capability_id": capability_id,
                "source_hub": "local",
                "input": {"query": query, "max_results": 5},
            },
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            return {
                "success": True,
                "data": data.get("result", {}),
                "cost_usd": data.get("price_usd", 0),
                "receipt": data.get("receipt"),
            }
        elif resp.status_code == 402:
            return {"success": False, "needs_payment": True, "detail": resp.json()}
        else:
            return {"success": False, "error": f"HTTP {resp.status_code}"}

    except Exception as exc:
        return {"success": False, "error": str(exc)}
