from __future__ import annotations

import time
from typing import Any

import httpx

from relay_scout.models import EndpointTarget, Snapshot, utc_now_iso


async def poll_endpoint(client: httpx.AsyncClient, target: EndpointTarget) -> Snapshot:
    started = time.perf_counter()
    try:
        response = await client.get(target.url, timeout=10.0)
        latency_ms = (time.perf_counter() - started) * 1000.0
        body: dict[str, Any] | None
        try:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            body = {"raw": response.text[:2000]}
        return Snapshot(
            endpoint_name=target.name,
            timestamp=utc_now_iso(),
            status_code=response.status_code,
            latency_ms=latency_ms,
            response_json=body,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return Snapshot(
            endpoint_name=target.name,
            timestamp=utc_now_iso(),
            status_code=0,
            latency_ms=latency_ms,
            response_json=None,
            error=str(exc),
        )
