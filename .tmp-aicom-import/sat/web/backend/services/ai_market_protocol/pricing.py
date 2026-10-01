"""Dynamic per-call pricing quotes."""

from __future__ import annotations

from typing import Any

from web.backend.services.ai_market_protocol.catalog import get_capability


def quote_capability_price(
    *,
    product_id: str,
    capability_id: str,
    input_size: int = 0,
    input_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cap = get_capability(product_id, capability_id)
    if not cap:
        return {"error": "capability_not_found", "product_id": product_id, "capability_id": capability_id}
    base = float(cap["price_per_call_usd"])
    size = input_size
    if input_payload:
        text = str(input_payload.get("text") or input_payload.get("task") or "")
        if not size:
            size = len(text)
        for v in (input_payload.get("documents") or {}).values():
            if isinstance(v, str):
                size += len(v)
    # ~$0.05 per 1k chars above 2k
    extra = max(0, size - 2000) / 1000.0 * 0.05
    price = round(base + extra, 4)
    return {
        "product_id": product_id,
        "capability_id": capability_id,
        "price_usd": price,
        "price_per_call_usd": base,
        "input_size": size,
        "p50_latency_ms": cap["p50_latency_ms"],
        "success_rate_30d": cap["success_rate_30d"],
        "protocol_version": "v1",
    }
