"""Double-submit CSRF protection for admin cookie sessions."""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_enabled() -> bool:
    v = (os.environ.get("AIFACTORY_CSRF_PROTECT") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _path_exempt(path: str) -> bool:
    if path.startswith("/api/admin/auth/login"):
        return True
    if path.startswith("/api/health"):
        return True
    if path.startswith("/api/payment/") and "webhook" in path:
        return True
    if path.startswith("/api/ai-market/") and "webhook" in path:
        return True
    return False


async def csrf_protect_middleware(request: Request, call_next):
    if not csrf_enabled():
        return await call_next(request)

    path = request.url.path
    if request.method not in _UNSAFE or _path_exempt(path):
        return await call_next(request)

    # Only protect admin routes that may use the HTTP-only access_token cookie.
    if not path.startswith("/api/admin"):
        return await call_next(request)

    session_cookie = (request.cookies.get("access_token") or "").strip()
    if not session_cookie:
        return await call_next(request)

    cookie_token = (request.cookies.get(CSRF_COOKIE) or "").strip()
    header_token = (request.headers.get(CSRF_HEADER) or request.headers.get("x-csrf-token") or "").strip()
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        logger.warning("CSRF validation failed for %s %s", request.method, path)
        return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})

    return await call_next(request)
