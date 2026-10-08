"""
Product telemetry events API
===========================
Public endpoint used by storefront pages and sandboxes to record
privacy-safe usage events into /app/data/telemetry/<product_id>/telemetry_YYYY-MM-DD.jsonl
via TelemetryCollector. Evolution/analyst agents merge ``evolution_signal`` rows from these JSONL files into prompts (see ``core.telemetry_signals``).
"""

from __future__ import annotations

import os

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from core.telemetry_signals import EVOLUTION_SIGNAL_EVENT_TYPE
from web.backend.schemas.api_requests import EvolutionSignalRequest, TelemetryEventRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# Both routes are public and anonymous; every call is a disk write, and evolution signals are
# later read back into an agent prompt.
_EVENT_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_TELEMETRY_EVENTS_PER_HOUR", "1200"))
_SIGNAL_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_EVOLUTION_SIGNALS_PER_HOUR", "120"))


def _rate_limit(request: Request, bucket: str, max_per_hour: int) -> None:
    from web.backend.http.client_ip import client_ip
    from web.backend.services.shared_rate_limit import enforce_shared_rate_limit

    enforce_shared_rate_limit(
        f"telemetry:{bucket}:{client_ip(request)}",
        max_hits=max_per_hour,
        window_seconds=3600.0,
        detail="Too many requests. Please try again later.",
    )


@router.post("/event")
async def record_event(request: Request, body: TelemetryEventRequest):
    """
    Public. Records one telemetry event.
    We intentionally keep it minimal and avoid PII. Client should not send emails, names, etc.
    """
    _rate_limit(request, "event", _EVENT_MAX_PER_HOUR)
    pid = body.product_id

    telemetry = getattr(request.app.state, "telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="Telemetry unavailable")

    payload = dict(body.data or {})
    if body.page_url:
        payload["page_url"] = body.page_url
    if body.locale:
        payload["locale"] = body.locale

    try:
        telemetry.record_event(
            product_id=pid,
            event_type=body.event_type,
            data=payload,
            session_id=body.session_id,
        )
    except Exception as e:
        logger.warning("Telemetry record failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record telemetry")

    return {"ok": True}


@router.post("/evolution-signal")
async def record_evolution_signal(request: Request, body: EvolutionSignalRequest):
    """
    Public. Aggregates product-level evolution hints (NPS-style, churn risk, feature demand).
    Stored alongside sandbox telemetry; pipelines can aggregate ``event_type == evolution_signal``.
    """
    _rate_limit(request, "evolution", _SIGNAL_MAX_PER_HOUR)
    pid = body.product_id

    telemetry = getattr(request.app.state, "telemetry", None)
    if telemetry is None:
        raise HTTPException(status_code=503, detail="Telemetry unavailable")

    payload: dict[str, Any] = {
        "signal": body.signal.strip(),
        "weight": body.weight,
        **(body.context or {}),
    }

    try:
        telemetry.record_event(
            product_id=pid,
            event_type=EVOLUTION_SIGNAL_EVENT_TYPE,
            data=payload,
            session_id=body.session_id,
        )
    except Exception as e:
        logger.warning("Evolution signal record failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record evolution signal")

    return {"ok": True, "product_id": pid}

