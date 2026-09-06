"""Double-submit CSRF and Origin checks for cookie-authenticated and public mutation APIs."""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from web.backend.cors_settings import get_cors_allow_origins
from web.backend.middleware.api_version import canonical_api_path

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


def _allowed_origins() -> set[str]:
    origins = set(get_cors_allow_origins())
    site = (os.environ.get("NEXT_PUBLIC_SITE_URL") or "").strip().rstrip("/")
    if site:
        origins.add(site)
    return origins


def _origin_allowed(request: Request) -> bool:
    """Reject cross-site browser mutations when Origin/Referer do not match the site."""
    allowed = _allowed_origins()
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        return origin.rstrip("/") in allowed

    referer = (request.headers.get("referer") or "").strip()
    if referer:
        try:
            ref_origin = f"{urlparse(referer).scheme}://{urlparse(referer).netloc}"
        except Exception:
            return False
        return ref_origin.rstrip("/") in allowed

    # Non-browser clients (curl, workers) typically omit Origin — allow.
    return True


def _requires_origin_check(path: str) -> bool:
    return path.startswith("/api/customer/") or path.startswith("/api/support/")


def _requires_admin_csrf(path: str, request: Request) -> bool:
    _ = path  # Credential source, not route naming, defines the trust boundary.
    return bool(
        (request.cookies.get("access_token") or "").strip()
        or (request.cookies.get("aif_admin_session") or "").strip()
    )


def _requires_customer_csrf(path: str, request: Request) -> bool:
    _ = path
    # A simultaneous Bearer header does not neutralize ambient cookie authority;
    # stale clients can carry both, while a cross-site attacker controls neither.
    return bool((request.cookies.get("customer_token") or "").strip())


async def csrf_protect_middleware(request: Request, call_next):
    if not csrf_enabled():
        return await call_next(request)

    # Canonicalize BEFORE any prefix match. This middleware runs outside the /api/v1 ->
    # /api rewrite, so `POST /api/v1/admin/settings` used to match none of the prefixes
    # below -- needs_csrf came out False -- and then executed as /api/admin/settings with
    # the caller's admin session cookie. That is a full CSRF bypass on every
    # cookie-authenticated admin and customer mutation, reachable from any origin.
    path = canonical_api_path(request.url.path)
    if request.method not in _UNSAFE or _path_exempt(path):
        return await call_next(request)

    needs_csrf = _requires_admin_csrf(path, request) or _requires_customer_csrf(path, request)

    if (_requires_origin_check(path) or needs_csrf) and not _origin_allowed(request):
        logger.warning("Origin check failed for %s %s", request.method, path)
        return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})

    if not needs_csrf:
        return await call_next(request)

    cookie_token = (request.cookies.get(CSRF_COOKIE) or "").strip()
    header_token = (request.headers.get(CSRF_HEADER) or request.headers.get("x-csrf-token") or "").strip()
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        logger.warning("CSRF validation failed for %s %s", request.method, path)
        return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})

    return await call_next(request)
