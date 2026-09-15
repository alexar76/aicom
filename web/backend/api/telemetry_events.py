"""
Product telemetry events API
===========================
Public endpoint used by storefront pages and sandboxes to record
privacy-safe usage events into /app/data/telemetry/<product_id>/telemetry_YYYY-MM-DD.jsonl
via TelemetryCollector. Evolution/analyst agents merge ``evolution_signal`` rows from these JSONL files into prompts (see ``core.telemetry_signals``).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from core.telemetry_signals import EVOLUTION_SIGNAL_EVENT_TYPE
from web.backend.schemas.api_requests import EvolutionSignalRequest, TelemetryEventRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.post("/event")
async def record_event(request: Request, body: TelemetryEventRequest):
    """
    Public. Records one telemetry event.
    We intentionally keep it minimal and avoid PII. Client should not send emails, names, etc.
    """
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

