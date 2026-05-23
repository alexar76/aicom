"""Real capability invocation — AIMarket Hub protocol or direct agent endpoint."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx


def response_is_demo_marked(data: dict, detail: str) -> bool:
    """Detect hub/factory demo execution — mesh treats this as failed invoke in production."""
    blob = detail or ""
    result = data.get("result")
    if isinstance(result, dict):
        out = result.get("output")
        if isinstance(out, str):
            blob += " " + out
    raw = data.get("raw")
    if isinstance(raw, str):
        blob += " " + raw
    return "[DEMO]" in blob.upper() or "demo execution" in blob.lower()


async def preflight_hub(hub_url: str) -> tuple[bool, int, str]:
    """Lightweight hub health check before routing paid hub invocations."""
    t0 = time.perf_counter()
    url = f"{hub_url.rstrip('/')}/ai-market/v2/manifest"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            resp = await client.get(url)
        latency = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return True, latency, "hub_manifest_ok"
        return False, latency, f"hub_status_{resp.status_code}"
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, latency, str(exc)[:160]


async def preflight_agent(endpoint_url: str) -> tuple[bool, int, str]:
    """Verify agent endpoint responds before routing a paid task."""
    t0 = time.perf_counter()
    url = f"{endpoint_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            resp = await client.get(url)
        latency = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return True, latency, "health_ok"
        return False, latency, f"health_status_{resp.status_code}"
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, latency, str(exc)[:160]


async def invoke_via_hub(
    hub_url: str,
    product_id: str,
    capability_id: str,
    intent: str,
    source_hub: str = "local",
    *,
    reject_demo_output: bool = True,
) -> tuple[bool, int, str, dict[str, Any]]:
    t0 = time.perf_counter()
    url = f"{hub_url.rstrip('/')}/ai-market/v2/invoke"
    body = {
        "product_id": product_id,
        "capability_id": capability_id,
        "source_hub": source_hub,
        "input": {"intent": intent, "query": intent},
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=body)
        latency = int((time.perf_counter() - t0) * 1000)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        if resp.status_code == 200 and data.get("success") is not False:
            detail = "invoke_ok"
            if isinstance(data.get("result"), dict) and data["result"].get("output"):
                detail = str(data["result"]["output"])[:160]
            if reject_demo_output and response_is_demo_marked(data, detail):
                return False, latency, "demo_output_rejected", data
            return True, latency, detail, data
        err = data.get("error") or data.get("reason") or resp.text[:120]
        return False, latency, str(err), data
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, latency, str(exc)[:160], {}


async def invoke_direct(endpoint_url: str, intent: str) -> tuple[bool, int, str, dict[str, Any]]:
    """POST /invoke on a registered agent endpoint (factory-style)."""
    t0 = time.perf_counter()
    url = f"{endpoint_url.rstrip('/')}/invoke"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json={"input": {"intent": intent, "query": intent}})
        latency = int((time.perf_counter() - t0) * 1000)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text[:500]}
        if resp.status_code == 200:
            return True, latency, "invoke_ok", data
        return False, latency, f"status_{resp.status_code}", data
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, latency, str(exc)[:160], {}
