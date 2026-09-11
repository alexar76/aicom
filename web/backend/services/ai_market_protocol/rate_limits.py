"""Sliding-window rate limits for AI Market invoke/discover endpoints."""

from __future__ import annotations

import os

from fastapi import HTTPException

from web.backend.services.shared_rate_limit import enforce_shared_rate_limit

_WINDOW_SEC = 60.0
_INVOKE_MAX_PER_CUSTOMER = max(
    1, int(os.environ.get("AIMARKET_INVOKE_MAX_PER_CUSTOMER_PER_MIN", "20") or "20")
)
_INVOKE_MAX_PER_IP = max(
    1, int(os.environ.get("AIMARKET_INVOKE_MAX_PER_IP_PER_MIN", "30") or "30")
)
_DISCOVER_MAX_PER_IP = max(
    1, int(os.environ.get("AIMARKET_DISCOVER_MAX_PER_IP_PER_MIN", "15") or "15")
)


def enforce_rate_limit(key: str, max_hits: int, *, detail: str | None = None) -> None:
    """Sliding-window throttle; raises HTTP 429 when exceeded."""
    enforce_shared_rate_limit(
        f"aimarket:{key}",
        max_hits=max_hits,
        window_seconds=_WINDOW_SEC,
        detail=detail or "Too many AI-market requests. Slow down and try again shortly.",
    )


def enforce_invoke_limits(request, authorization: str | None) -> None:
    """Throttle invoke per-customer (when authenticated) and per-IP (always)."""
    from web.backend.http.client_ip import client_ip
    from web.backend.services.customer_auth import decode_customer

    payload = None
    try:
        payload = decode_customer(authorization)
    except HTTPException:
        payload = None
    customer_id = str((payload or {}).get("sub") or "").strip()
    if customer_id:
        enforce_rate_limit(f"cust:{customer_id}", _INVOKE_MAX_PER_CUSTOMER)
    enforce_rate_limit(f"ip:{client_ip(request)}", _INVOKE_MAX_PER_IP)


def enforce_discover_limit(request) -> None:
    from web.backend.http.client_ip import client_ip

    enforce_rate_limit(
        f"discover:ip:{client_ip(request)}",
        _DISCOVER_MAX_PER_IP,
        detail="Too many AI-market discovery requests. Slow down and try again shortly.",
    )
