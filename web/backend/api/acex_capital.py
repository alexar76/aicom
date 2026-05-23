"""ACEX capital markets API — Pulse Terminal pricing on the factory."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from acex.integrations.pricing import build_pricing_snapshot
from web.backend.services.ai_market_protocol.catalog import list_factory_capabilities

router = APIRouter(prefix="/v2/capital", tags=["acex-capital"])


def _pricing_snapshot(
    *,
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
) -> dict:
    caps = list_factory_capabilities()
    return build_pricing_snapshot(caps, chain=chain, listing_id=listing_id, limit=limit)


@router.get("/pricing")
async def capital_pricing(
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
):
    """Real-time capability revenue indices for Pulse Terminal."""
    return _pricing_snapshot(chain=chain, listing_id=listing_id, limit=limit)


@router.get("/pricing/stream")
async def capital_pricing_stream(
    chain: str = "any",
    listing_id: str | None = None,
    limit: int = 50,
):
    """SSE stream — refresh interval from pulse_terminal.refresh_ms in each payload."""

    async def gen():
        while True:
            snap = _pricing_snapshot(chain=chain, listing_id=listing_id, limit=limit)
            yield f"data: {json.dumps(snap, separators=(',', ':'))}\n\n"
            refresh_ms = int(snap.get("pulse_terminal", {}).get("refresh_ms") or 5000)
            await asyncio.sleep(max(refresh_ms, 1000) / 1000.0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/pricing/ws")
async def capital_pricing_ws(
    websocket: WebSocket,
    chain: str = Query(default="any"),
    listing_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """WebSocket feed for Pulse Terminal — server-driven refresh cadence."""
    await websocket.accept()
    try:
        while True:
            snap = _pricing_snapshot(chain=chain, listing_id=listing_id, limit=limit)
            await websocket.send_json(snap)
            refresh_ms = int(snap.get("pulse_terminal", {}).get("refresh_ms") or 5000)
            await asyncio.sleep(max(refresh_ms, 1000) / 1000.0)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close()
