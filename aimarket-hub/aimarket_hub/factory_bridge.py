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

    Reads the factory's pipeline.json, extracts COMPLETED/DEPLOYED_PRODUCTION
    products, and indexes them as local capabilities in the hub database.

    Returns the number of capabilities imported.
    """
    import json
    from pathlib import Path

    try:
        from core.paths import pipeline_json_path as _factory_pipeline_path
    except ImportError:
        # Standalone hub without factory — no products to import
        return 0

    path = Path(pipeline_json_path) if pipeline_json_path else _factory_pipeline_path()
    if not path.exists():
        return 0

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    products = data.get("products") if isinstance(data, dict) else {}
    if not isinstance(products, dict):
        return 0

    count = 0
    for pid, pdata in products.items():
        state = str((pdata or {}).get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue

        # Use the catalog synthesis logic from the existing AI-Factory
        from web.backend.services.ai_market_protocol.catalog import _capability_defs_for_product

        caps = _capability_defs_for_product(pid, pdata or {})
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
