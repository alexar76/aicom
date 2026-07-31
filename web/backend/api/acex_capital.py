"""ACEX capital markets API — Pulse Terminal pricing on the factory.

Hardened against:
- Cross-origin WebSocket hijacking (API2-2): Origin header verified
  against the same AIFACTORY_CORS_ORIGINS allowlist used by HTTP CORS.
- DoS via unbounded concurrent connections (API2-2): per-process
  semaphore caps the number of concurrent streaming clients.
- Per-tick DB query storm (API2-3): a single shared snapshot is
  computed every refresh interval and broadcast to all clients,
  not recomputed per-connection.
- Snapshot lock wedging (Pulse hang): catalog refresh runs outside the
  asyncio.Lock via an inflight Future, with a hard timeout so one stuck
  SQLite/`list_factory_capabilities` call cannot block every pricing
  client (HTTP/SSE/WS) indefinitely on the single uvicorn worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

from acex.integrations.pricing import build_pricing_snapshot
from web.backend.cors_settings import get_cors_allow_origins
from web.backend.services.ai_market_protocol.catalog import list_factory_capabilities

router = APIRouter(prefix="/v2/capital", tags=["acex-capital"])
logger = logging.getLogger(__name__)


# ── Bounded concurrent streamers (API2-2 DoS guard) ────────────────────────

_MAX_STREAM_CLIENTS = int(os.environ.get("ACEX_MAX_STREAM_CLIENTS", "200"))
_stream_semaphore = asyncio.Semaphore(_MAX_STREAM_CLIENTS)


# ── Shared snapshot cache (API2-3 query-storm guard) ───────────────────────

_SNAPSHOT_TTL_SEC = max(
    float(os.environ.get("ACEX_SNAPSHOT_TTL_SEC", "1.0")),
    0.25,
)
_SNAPSHOT_BUILD_TIMEOUT_SEC = max(
    float(os.environ.get("ACEX_SNAPSHOT_BUILD_TIMEOUT_SEC", "12.0")),
    2.0,
)
# Serve slightly-stale data rather than hang when a refresh times out.
_SNAPSHOT_STALE_SEC = max(
    float(os.environ.get("ACEX_SNAPSHOT_STALE_SEC", "60.0")),
    _SNAPSHOT_TTL_SEC,
)
_snapshot_cache: dict[tuple, tuple[float, dict]] = {}
_snapshot_lock = asyncio.Lock()
_snapshot_inflight: dict[tuple, asyncio.Future] = {}


async def _compute_pricing_snapshot(
    *,
    chain: str,
    listing_id: Optional[str],
    limit: int,
) -> dict:
    caps = await asyncio.wait_for(
        asyncio.to_thread(list_factory_capabilities),
        timeout=_SNAPSHOT_BUILD_TIMEOUT_SEC,
    )
    return build_pricing_snapshot(
        caps, chain=chain, listing_id=listing_id, limit=limit
    )


async def _get_pricing_snapshot(
    *,
    chain: str,
    listing_id: Optional[str],
    limit: int,
) -> dict:
    """Return a snapshot, refreshing the cache at most once per TTL.

    Different (chain, listing_id, limit) combinations get separate cache
    entries; identical requests within TTL share the same computation.

    Refresh does **not** hold ``_snapshot_lock`` across the catalog DB
    call — waiters share one inflight Future instead. That prevents a
    single stuck ``list_factory_capabilities`` from wedging every Pulse
    client behind the lock on ``--workers 1``.
    """
    key = (chain, listing_id, limit)
    now = time.monotonic()

    cached = _snapshot_cache.get(key)
    if cached and (now - cached[0]) < _SNAPSHOT_TTL_SEC:
        return cached[1]

    leader = False
    async with _snapshot_lock:
        cached = _snapshot_cache.get(key)
        if cached and (time.monotonic() - cached[0]) < _SNAPSHOT_TTL_SEC:
            return cached[1]

        inflight = _snapshot_inflight.get(key)
        if inflight is None:
            loop = asyncio.get_running_loop()
            inflight = loop.create_future()
            _snapshot_inflight[key] = inflight
            leader = True

    if not leader:
        return await inflight

    try:
        snap = await _compute_pricing_snapshot(
            chain=chain, listing_id=listing_id, limit=limit
        )
        _snapshot_cache[key] = (time.monotonic(), snap)
        if not inflight.done():
            inflight.set_result(snap)
        return snap
    except Exception as exc:
        logger.warning("pricing snapshot refresh failed for %s: %s", key, exc)
        stale = _snapshot_cache.get(key)
        if stale and (time.monotonic() - stale[0]) < _SNAPSHOT_STALE_SEC:
            if not inflight.done():
                inflight.set_result(stale[1])
            return stale[1]
        if not inflight.done():
            inflight.set_exception(exc)
        raise
    finally:
        async with _snapshot_lock:
            if _snapshot_inflight.get(key) is inflight:
                _snapshot_inflight.pop(key, None)


# ── Origin allowlist for WebSocket (API2-2) ────────────────────────────────


def _ws_origin_allowed(origin: str) -> bool:
    """Compare WS Origin header to the HTTP CORS allowlist.

    Empty origin (some native clients) is rejected unless the allowlist
    contains "*" (which the operator must set deliberately).
    """
    allowed = get_cors_allow_origins()
    if "*" in allowed:
        return True
    if not origin:
        return False
    return origin in allowed


# ── HTTP endpoints ─────────────────────────────────────────────────────────


@router.get("/pricing")
async def capital_pricing(
    chain: str = "any",
    listing_id: Optional[str] = None,
    limit: int = 50,
):
    """Real-time capability revenue indices for Pulse Terminal."""
    limit = max(1, min(limit, 200))
    try:
        return await _get_pricing_snapshot(chain=chain, listing_id=listing_id, limit=limit)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pricing catalog refresh timed out; retry shortly.",
        ) from exc
    except Exception as exc:
        logger.exception("pricing snapshot failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pricing temporarily unavailable.",
        ) from exc


@router.get("/pricing/stream")
async def capital_pricing_stream(
    chain: str = "any",
    listing_id: Optional[str] = None,
    limit: int = 50,
):
    """SSE stream — capped concurrent clients, cached snapshot."""
    limit = max(1, min(limit, 200))

    if _stream_semaphore.locked():
        # Fail fast rather than queue indefinitely.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Too many concurrent stream clients; try again shortly.",
        )

    async def gen():
        async with _stream_semaphore:
            while True:
                snap = await _get_pricing_snapshot(
                    chain=chain, listing_id=listing_id, limit=limit
                )
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
    listing_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    """WebSocket feed for Pulse Terminal.

    - Origin must match AIFACTORY_CORS_ORIGINS (API2-2 anti-CSWSH).
    - Concurrent clients capped via ACEX_MAX_STREAM_CLIENTS (API2-2 DoS).
    - Snapshot computed at most once per ACEX_SNAPSHOT_TTL_SEC, shared
      across all clients with the same params (API2-3).
    """
    origin = websocket.headers.get("origin", "")
    if not _ws_origin_allowed(origin):
        # 1008 Policy Violation — close without accepting.
        await websocket.close(code=1008, reason="origin not allowed")
        logger.warning("WS rejected: origin not in allowlist: %r", origin[:80])
        return

    # Try to acquire a streamer slot without blocking forever.
    try:
        await asyncio.wait_for(_stream_semaphore.acquire(), timeout=0.5)
    except asyncio.TimeoutError:
        await websocket.close(code=1013, reason="too many clients")
        logger.warning("WS rejected: concurrent stream limit reached")
        return

    limit = max(1, min(limit, 200))
    try:
        await websocket.accept()
        while True:
            snap = await _get_pricing_snapshot(
                chain=chain, listing_id=listing_id, limit=limit
            )
            await websocket.send_json(snap)
            refresh_ms = int(snap.get("pulse_terminal", {}).get("refresh_ms") or 5000)
            await asyncio.sleep(max(refresh_ms, 1000) / 1000.0)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.warning("WS pricing stream error: %s", exc)
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        _stream_semaphore.release()
