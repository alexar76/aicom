"""Attach FirewallManager rate limits and optional ACL enforcement to HTTP requests."""

from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _request_port(request: Request) -> int:
    try:
        if request.url.port:
            return int(request.url.port)
    except (TypeError, ValueError):
        pass
    if request.url.scheme == "https":
        return 443
    return int(os.environ.get("AICOM_PORT_API", "9081") or 9081)


async def firewall_http_middleware(request: Request, call_next):
    fw = getattr(request.app.state, "firewall", None)
    if fw is None:
        return await call_next(request)

    ip = _client_ip(request)
    port = _request_port(request)
    allowed, reason = fw.http_request_allowed(ip, port)
    if not allowed:
        logger.warning("Firewall blocked %s %s from %s: %s", request.method, request.url.path, ip, reason)
        return JSONResponse(status_code=403, content={"detail": "Forbidden", "reason": reason})

    if request.method not in ("OPTIONS", "HEAD"):
        fw.record_request(ip)

    return await call_next(request)
