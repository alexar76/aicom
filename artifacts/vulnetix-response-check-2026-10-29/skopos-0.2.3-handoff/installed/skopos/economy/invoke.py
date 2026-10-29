"""AIMarket invoke dispatcher."""

from __future__ import annotations

from typing import Any

from .capabilities import CAPABILITY_BY_ID
from .config import EconomyConfig


class InvokeError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def dispatch_invoke(
    body: dict[str, Any],
    *,
    cfg: EconomyConfig,
) -> dict[str, Any]:
    if not cfg.enabled:
        raise InvokeError("SKOPOS AIMarket economy is disabled", status=503)

    cap_id = (body.get("capability_id") or "").strip()
    if not cap_id:
        raise InvokeError("capability_id is required")
    if cap_id not in CAPABILITY_BY_ID:
        raise InvokeError(f"unknown capability: {cap_id}", status=404)

    raw_input = body.get("input")
    inp: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}

    handler = _get_handlers()[cap_id]
    try:
        result = handler(
            config_path=cfg.config_path,
            agent_yaml=cfg.agent_yaml_path,
            inp=inp,
        )
    except InvokeError:
        raise
    except Exception as exc:
        raise InvokeError(f"handler failed: {type(exc).__name__}", status=500) from exc

    return {
        "result": result,
        "product_id": body.get("product_id") or cfg.product_id,
        "capability_id": cap_id,
        "price_per_call_usd": CAPABILITY_BY_ID[cap_id].price_per_call_usd,
        "provider": "skopos",
    }


def _get_handlers():
    from .handlers import HANDLERS

    return HANDLERS
