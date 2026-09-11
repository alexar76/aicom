"""Public API for factory-born agents: heartbeat in, roster out."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from web.backend.services.agent_registry import (
    check_agent_key,
    list_agents,
    record_heartbeat,
    registry_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/heartbeat")
async def agent_heartbeat(request: Request) -> dict[str, Any]:
    """Upsert a running agent. Called by agents the factory built."""
    ok, reason = check_agent_key(request.headers.get("X-Agent-Key"))
    if not ok:
        if reason == "registry_key_not_configured":
            raise HTTPException(
                status_code=503,
                detail="Agent registry is not accepting heartbeats: "
                "AIFACTORY_AGENT_REGISTRY_KEY is unset in production.",
            )
        raise HTTPException(status_code=401, detail="Invalid or missing X-Agent-Key")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    try:
        record = record_heartbeat(payload, verified=(reason == "verified"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "agent_id": record["agent_id"],
        "verified": record["verified"],
        "next_heartbeat_sec": 60,
    }


@router.get("")
async def agents_roster(include_offline: bool = True) -> dict[str, Any]:
    """Roster of factory-born agents with their economy counters."""
    return {
        "agents": list_agents(include_offline=include_offline),
        "summary": registry_summary(),
    }


@router.get("/summary")
async def agents_summary() -> dict[str, Any]:
    return registry_summary()
