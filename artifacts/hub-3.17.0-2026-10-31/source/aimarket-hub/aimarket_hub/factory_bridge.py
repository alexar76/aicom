"""AI-Factory ↔ AIMarket Hub integration bridge.

Connects the existing AI-Factory (closed core) with the hub (open federation).
The factory's products are automatically exposed as capabilities in the hub,
and the hub's federated catalog appears in the factory's storefront.

Architecture:
    ┌─────────────────────────────────────────┐
    │ AI-Factory (closed core, MIT shell)     │
    │                                         │
    │  ┌──────────┐    ┌──────────────────┐   │
    │  │ 13 agent │    │ aimarket-hub     │◄──┼── crawl other hubs
    │  │ pipeline │───►│ (embedded mode)  │   │
    │  └──────────┘    └────────┬─────────┘   │
    │                           │             │
    │  storefront               │             │
    │  ┌──────────────┐         │             │
    │  │ aimarket-    │◄────────┘             │
    │  │ widget       │                       │
    │  └──────────────┘                       │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from typing import Any

from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import has_execution_path
from aimarket_hub.models import Capability

# `logger` was used at the bottom of import_factory_products and never defined here, so the
# function raised NameError the instant it skipped its FIRST unfulfillable row — which is the
# normal case, not an edge one. create_app wraps the call in `except Exception: pass` and
# deploy_hub.sh degrades it to "WARN: hub import failed", so the failure was invisible from both
# sides, and the one message that would have told an operator *why* the hub has no capabilities
# ("skipped N capability(ies) with no invoke_url/static pack") could never be printed. The hub
# has been serving an empty catalogue with the explanation suppressed.
logger = logging.getLogger(__name__)


def import_factory_products(
    db: HubDatabase,
    pipeline_json_path: str = "pipeline.json",
) -> int:
    """Import AI-Factory shipped products into the hub as local capabilities.

    Reads COMPLETED/DEPLOYED products from SQLite (when available) and
    pipeline.json, then indexes capabilities in the hub database.

    Returns the number of capabilities imported.
    """
    from aimarket_hub.factory_products_loader import iter_shipped_factory_products

    try:
        products = iter_shipped_factory_products(pipeline_json_path)
    except ImportError:
        return 0

    if not products:
        return 0

    count = 0
    skipped = 0
    for pid, pdata in products.items():
        caps = _capability_rows_for_product(pid, pdata or {})
        for cap in caps:
            invoke_url = str(cap.get("invoke_url") or "").strip()
            prompt = str(cap.get("prompt_template") or "").strip()
            # Refuse to sell a capability that cannot execute. Shared with the search
            # and manifest gates via aimarket_hub.fulfillment so the ingest rule and the
            # serving rule cannot drift into disagreeing about the same row.
            if not has_execution_path(invoke_url, prompt):
                skipped += 1
                continue
            db.upsert_capability(Capability(
                capability_id=cap["capability_id"],
                product_id=cap["product_id"],
                name=cap["name"],
                version=cap["version"],
                description=cap["description"],
                input_schema=cap["input_schema"],
                output_schema=cap["output_schema"],
                price_per_call_usd=cap["price_per_call_usd"],
                p50_latency_ms=cap["p50_latency_ms"],
                success_rate_30d=cap["success_rate_30d"],
                source_hub="local",
                source_hub_name="AI-Factory",
                agent=cap.get("agent", ""),
                prompt_template=cap.get("prompt_template", ""),
                invoke_url=invoke_url,
                is_demo=bool(cap.get("demo") or cap.get("is_demo")),
            ))
            count += 1

    if skipped:
        logger.warning(
            "factory_bridge: skipped %d capability(ies) with no invoke_url/static pack",
            skipped,
        )
    return count


def _capability_rows_for_product(pid: str, pdata: dict[str, Any]) -> list[dict[str, Any]]:
    """Factory catalog synthesis when available; hub heuristics as fallback."""
    try:
        from web.backend.services.ai_market_protocol.catalog import _capability_defs_for_product

        return _capability_defs_for_product(pid, pdata)
    except Exception:
        from aimarket_hub.auto_listing import _generate_capabilities

        rows: list[dict[str, Any]] = []
        for cap in _generate_capabilities(pid, pdata):
            rows.append({
                "capability_id": cap.capability_id,
                "product_id": cap.product_id,
                "name": cap.name,
                "version": cap.version,
                "description": cap.description,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "price_per_call_usd": cap.price_per_call_usd,
                "p50_latency_ms": cap.p50_latency_ms,
                "success_rate_30d": cap.success_rate_30d,
                "demo": cap.is_demo,
                "agent": "",
                "prompt_template": "",
            })
        return rows


def export_hub_catalog_for_storefront(
    db: HubDatabase,
) -> list[dict[str, Any]]:
    """Export the federated catalog for the AI-Factory storefront.

    Returns capabilities formatted for the Next.js storefront to display
    alongside the factory's own products.

    .. note::
        **Currently unused (no HTTP route wires this).** It is exercised only
        indirectly via :func:`sync_factory_to_hub` (which is itself not yet
        wired to a caller). The companion ``/manifest`` route in
        ``aimarket_hub.api`` already serves the raw capability list publicly,
        so this storefront-shaped view is intentionally NOT auto-exposed to
        avoid shipping a second, unvetted public catalog endpoint.

        To wire it, add a read-only route to ``create_app`` in
        ``aimarket_hub/api.py`` (it owns the FastAPI ``app``/``router``)::

            @router.get("/storefront/catalog")
            def storefront_catalog():
                from aimarket_hub.factory_bridge import (
                    export_hub_catalog_for_storefront,
                )
                return {"catalog": export_hub_catalog_for_storefront(db)}

        Keep it GET-only and read-only; it returns public capability metadata
        already present in ``/manifest`` and must never accept input.
    """
    caps = db.list_capabilities(limit=500)
    result: list[dict[str, Any]] = []
    for c in caps:
        result.append({
            "id": f"{c.product_id}/{c.capability_id}",
            "name": c.name,
            "version": c.version,
            "description": c.description,
            "price_per_call_usd": c.price_per_call_usd,
            "p50_latency_ms": c.p50_latency_ms,
            "success_rate_30d": c.success_rate_30d,
            "demo": c.is_demo,
            "source_hub": c.source_hub,
            "source_hub_name": c.source_hub_name,
            "trust_score": c.trust_score,
            "is_federated": c.source_hub != "local",
            "routed_price_usd": c.routed_price_usd,
        })
    return result


def sync_factory_to_hub(
    db: HubDatabase | None = None,
) -> dict[str, Any]:
    """Full sync: import factory products + return catalog for storefront.

    Call this from the factory's startup or admin panel.
    """
    if db is None:
        db = HubDatabase()

    imported = import_factory_products(db)
    catalog = export_hub_catalog_for_storefront(db)
    stats = db.stats_summary()

    return {
        "imported_capabilities": imported,
        "total_catalog_size": len(catalog),
        "federated_count": sum(1 for c in catalog if c["is_federated"]),
        "hub_stats": stats,
        "storefront_catalog": catalog,
    }
