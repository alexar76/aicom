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

from typing import Any

from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability


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
    for pid, pdata in products.items():
        caps = _capability_rows_for_product(pid, pdata or {})
        for cap in caps:
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
            ))
            count += 1

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
