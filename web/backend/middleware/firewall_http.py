"""Attach FirewallManager rate limits and optional ACL enforcement to HTTP requests."""

from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


def _trusted_proxy_ips() -> frozenset[str]:
    raw = (os.environ.get("AIFACTORY_TRUSTED_PROXY_IPS") or "127.0.0.1,::1").strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else ""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded and peer in _trusted_proxy_ips():
        return forwarded.split(",")[0].strip()
    if peer:
        return peer
    return "unknown"


def _request_port(request: Request) -> int:
    try:
        if request.url.port:
            return int(request.url.port)
    except (TypeError, ValueError) as _suppressed_exc:
        log_suppressed(logger, "non-fatal (web/backend/middleware/firewall_http.py)", exc_info=_suppressed_exc)
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
