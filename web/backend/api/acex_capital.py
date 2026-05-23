"""ACEX capital markets API — Pulse Terminal pricing on the factory."""

from __future__ import annotations

from fastapi import APIRouter

from acex.integrations.pricing import build_pricing_snapshot
from web.backend.services.ai_market_protocol.catalog import list_factory_capabilities

router = APIRouter(prefix="/v2/capital", tags=["acex-capital"])


@router.get("/pricing")
async def capital_pricing(
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
):
    """Real-time capability revenue indices for Pulse Terminal."""
    caps = list_factory_capabilities()
    return build_pricing_snapshot(caps, chain=chain, listing_id=listing_id, limit=limit)
