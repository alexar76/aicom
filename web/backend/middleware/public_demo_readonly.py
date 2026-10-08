"""Public demo: an admin mutation runs only when it is on the guest allow-list.

On the shared demo (``AIFACTORY_DEMO_READONLY=1``) the admin login is passwordless, so
"admin" is every visitor. The per-route ``require_not_public_demo`` calls were a deny-list,
and a deny-list misses whatever nobody thought of: provider ``base_url`` (which sends the
factory's provider key to the new host), LLM routing, outreach sends, blog edits,
storefront prices, prompt rewrites, 2FA enrolment on the shared account. Here the default
is refusal, and the routes a guest is meant to use are named.

Also refused on the demo: reads that hand a visitor other people's personal data or a
stored secret (leads, outreach channel credentials, support escalations).

Paths are canonicalised first: ``/api/v1/admin/...`` reaches the same routes, and a guard
that matched the raw path would be bypassed by it.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from web.backend.middleware.api_version import canonical_api_path
from web.backend.services.public_demo_guard import is_public_demo

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: What a guest may change on the shared demo (docs/security.md, "Public demo mode"):
#: sign in and out, toggle the soft hold (the route itself refuses every other settings
#: key), and create a product within the normal limits.
DEMO_ADMIN_MUTATIONS_ALLOWED = frozenset({
    ("POST", "/api/admin/auth/login"),
    ("POST", "/api/admin/auth/logout"),
    ("POST", "/api/admin/auth/verify-2fa"),
    ("POST", "/api/admin/auth/webauthn/login/options"),
    ("POST", "/api/admin/settings"),
    ("POST", "/api/admin/products/create"),
})

#: Reads that return personal data of other visitors or stored credentials.
DEMO_ADMIN_READS_REFUSED = (
    "/api/admin/funnel",
    "/api/admin/outreach",
    "/api/admin/support-queue",
)


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def demo_refusal(method: str, path: str) -> str | None:
    """Why the demo refuses this request, or None when it may run."""
    path = canonical_api_path(path).rstrip("/") or "/"
    if not _under(path, "/api/admin"):
        return None
    method = method.upper()
    if method in _SAFE_METHODS:
        if any(_under(path, p) for p in DEMO_ADMIN_READS_REFUSED):
            return "this page holds visitors' personal data or stored credentials"
        return None
    if (method, path) in DEMO_ADMIN_MUTATIONS_ALLOWED:
        return None
    return "changes to the shared factory are limited to the soft hold and product creation"


async def public_demo_readonly_middleware(request: Request, call_next):
    if is_public_demo():
        reason = demo_refusal(request.method, request.url.path)
        if reason:
            logger.warning("public demo refused %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"Public demo mode: {reason}. "
                        "Self-host your own instance for full owner controls."
                    )
                },
            )
    return await call_next(request)
