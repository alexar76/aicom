"""Platform introspection: service domains, LLM cost summary."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.cost_outcome_heatmap import build_cost_outcome_heatmap
from web.backend.services.registry import list_service_domains
from .helpers import _admin_sql_store_available, _admin_use_sqlite_pipeline
from ._router import router


def _products_light_for_cost() -> list[dict[str, Any]]:
    """Product rows only (no full task queue) — keeps llm-cost endpoint responsive."""
    if _admin_use_sqlite_pipeline() and _admin_sql_store_available():
        from core.pipeline_database import create_sync_pipeline_manager

        sm = create_sync_pipeline_manager()
        try:
            return [dict(p) for p in sm.get_all_products()]
        finally:
            sm.close()
    from core.paths import pipeline_json_path
    import json

    path = pipeline_json_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    products = data.get("products") or {}
    if isinstance(products, dict):
        return [dict(v) | {"id": k} if isinstance(v, dict) else {"id": k} for k, v in products.items()]
    if isinstance(products, list):
        return [dict(p) for p in products if isinstance(p, dict)]
    return []


@router.get("/platform/service-domains")
async def get_service_domains(_admin: dict = Depends(require_admin_with_rbac)) -> dict[str, Any]:
    _ = _admin
    domains = list_service_domains()
    return {"domains": domains, "count": len(domains)}


@router.get("/metrics/llm-cost-by-product")
async def get_llm_cost_by_product(_admin: dict = Depends(require_admin_with_rbac)) -> dict[str, Any]:
    """Unified per-product LLM spend (treemap + flat rows) for Dashboard / Pipeline."""
    _ = _admin
    products = _products_light_for_cost()
    heatmap = build_cost_outcome_heatmap(products=products)
    rows = []
    for child in heatmap.get("children") or []:
        if not isinstance(child, dict):
            continue
        pid = str(child.get("product_id") or "")
        rows.append(
            {
                "product_id": pid,
                "title": child.get("name"),
                "state": child.get("state"),
                "llm_cost_usd": child.get("llm_cost_usd", 0),
                "llm_call_count": child.get("llm_call_count", 0),
                "agents": child.get("agents") or [],
            }
        )
    return {
        "total_usd": heatmap.get("value", 0),
        "product_count": heatmap.get("product_count", 0),
        "heatmap": heatmap,
        "rows": rows,
    }
