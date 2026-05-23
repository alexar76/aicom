"""AI Market Protocol v2 compatibility layer for the embeddable widget.

The storefront widget calls GET /ai-market/v2/search and POST /ai-market/v2/invoke.
Search uses the real factory pipeline catalog (SQLite products with code on disk),
not federated modelmarket.dev demo capabilities unless explicitly enabled.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from web.backend.services.ai_market_protocol import discover_capabilities, invoke_capability_v1
from web.backend.services.ai_market_protocol.catalog import get_capability, list_factory_capabilities
from web.backend.services.ai_market_protocol.config import base_public_url

router = APIRouter(prefix="/v2", tags=["ai-market-v2"])


def _widget_federate_search() -> bool:
    return os.environ.get("AIMARKET_WIDGET_FEDERATE_SEARCH", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _federation_hub_url() -> str:
    return (
        os.environ.get("AIMARKET_FEDERATION_HUB_URL")
        or os.environ.get("NEXT_PUBLIC_AIMARKET_HUB_URL")
        or "https://modelmarket.dev"
    ).rstrip("/")


def _trust_for_state(state: str) -> float:
    s = (state or "").upper()
    if s in ("COMPLETED", "DEPLOYED_PRODUCTION"):
        return 0.92
    if s in ("SECURITY_SCANNED", "QA_TESTING", "QA_PASSED"):
        return 0.88
    if s in ("DEV_FIXING", "EVOLUTION_ANALYZING"):
        return 0.78
    return 0.72


def _cap_to_match(cap: dict[str, Any], score: float) -> dict[str, Any]:
    price = float(cap.get("price_per_call_usd") or 0)
    state = str(cap.get("pipeline_state") or "")
    display = str(cap.get("product_display_name") or cap["product_id"])
    status = state.replace("_", " ").title() if state else "Pipeline"
    return {
        "product_id": cap["product_id"],
        "capability_id": cap["capability_id"],
        "source_hub": "local",
        "source_hub_name": "AI-Factory",
        "name": cap.get("name") or cap.get("capability_id"),
        "description": cap.get("description") or "",
        "score": score,
        "price_per_call_usd": price,
        "routed_price_usd": price,
        "routing_fee_bps": 0,
        "trust_score": _trust_for_state(state),
        "p50_latency_ms": int(cap.get("p50_latency_ms") or 5000),
        "pipeline_state": state,
        "product_display_name": display,
        "status_label": status,
    }


def _enrich_from_discovery(raw: dict[str, Any]) -> dict[str, Any] | None:
    cap = get_capability(str(raw.get("product_id") or ""), str(raw.get("capability_id") or ""))
    if not cap:
        return None
    merged = dict(cap)
    merged["pipeline_state"] = merged.get("pipeline_state") or ""
    merged["product_display_name"] = merged.get("product_display_name") or merged["product_id"]
    return _cap_to_match(merged, float(raw.get("score") or 0.8))


class InvokeV2Body(BaseModel):
    product_id: str = Field(..., min_length=2, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    source_hub: str = Field("local", max_length=256)
    input: dict[str, Any] = Field(default_factory=dict)


@router.get("/search")
async def search_v2(
    request: Request,
    intent: str = "",
    budget: float | None = None,
    max_latency_ms: int | None = None,
    min_trust: float | None = None,
    hub: str = "any",
    limit: int = 6,
):
    """NL search over real factory pipeline products (code on disk), not hub demos by default."""
    limit = min(max(1, limit), 32)
    llm_router = getattr(request.app.state, "llm_router", None)
    factory_caps = list_factory_capabilities()

    disc = await discover_capabilities(
        query=intent,
        budget_usd=budget,
        constraints={},
        limit=limit,
        llm_router=llm_router,
        catalog="factory",
    )

    matches: list[dict[str, Any]] = []
    for raw in disc.get("matches") or []:
        if hub not in ("any", "local"):
            continue
        row = _enrich_from_discovery(raw)
        if not row:
            continue
        if min_trust is not None and row["trust_score"] < min_trust:
            continue
        if max_latency_ms is not None and row["p50_latency_ms"] > max_latency_ms:
            continue
        if budget is not None and row["routed_price_usd"] > budget:
            continue
        matches.append(row)
        if len(matches) >= limit:
            break

    if not matches and intent.strip() and _widget_federate_search():
        fed_url = _federation_hub_url()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{fed_url}/ai-market/v2/search",
                    params={"intent": intent, "budget": budget, "limit": limit},
                )
                if r.status_code == 200:
                    body = r.json()
                    body["catalog"] = "federated"
                    body["note"] = "Federated fallback; factory catalog had no matches."
                    return body
        except Exception:
            pass

    return {
        "query": intent,
        "matches": matches,
        "catalog": "factory",
        "factory_products_with_code": len({c["product_id"] for c in factory_caps}),
        "factory_capabilities": len(factory_caps),
        "total_hubs_searched": 1,
        "protocol_version": "v2",
        "empty_hint": (
            "No matching capabilities in the factory pipeline yet. "
            "Ship a product (COMPLETED) or refine your search."
            if not matches
            else ""
        ),
    }


@router.post("/invoke")
async def invoke_v2(
    body: InvokeV2Body,
    request: Request,
    x_payment_channel: str | None = Header(default=None, alias="X-Payment-Channel"),
    x_aimarket_affiliate: str | None = Header(default=None, alias="X-AIMarket-Affiliate"),
):
    """Invoke only factory capabilities unless federation is explicitly enabled."""
    if body.source_hub and body.source_hub not in ("local", "") and _widget_federate_search():
        fed_url = _federation_hub_url()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {"Content-Type": "application/json"}
                if x_payment_channel:
                    headers["X-Payment-Channel"] = x_payment_channel
                if x_aimarket_affiliate:
                    headers["X-AIMarket-Affiliate"] = x_aimarket_affiliate
                r = await client.post(
                    f"{fed_url}/ai-market/v2/invoke",
                    json=body.model_dump(),
                    headers=headers,
                )
                return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception as exc:
            return JSONResponse(
                status_code=502,
                content={"success": False, "error": "federation_unreachable", "detail": str(exc)},
            )

    if not get_capability(body.product_id, body.capability_id):
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "factory_capability_not_found",
                "detail": "This capability is not in the factory pipeline catalog.",
                "protocol_version": "v2",
            },
        )

    status, payload, extra_headers = await invoke_capability_v1(
        product_id=body.product_id,
        capability_id=body.capability_id,
        body_input=body.input,
        base_url=base_public_url(),
        x_payment_channel=x_payment_channel,
        llm_router=getattr(request.app.state, "llm_router", None),
    )

    if isinstance(payload, dict):
        payload.setdefault("safety_checked", True)
        payload["protocol_version"] = "v2"

    return JSONResponse(status_code=status, content=payload, headers=extra_headers)


# Root-level routes (/.well-known, /capabilities/.../invoke) shared with v1 implementation.
from web.backend.api.ai_market_protocol_v1 import (  # noqa: E402
    capabilities_router,
    wellknown_router,
)
