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

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from web.backend.middleware.api_version import canonical_api_path
from web.backend.core.security import get_current_admin, security_scheme
from web.backend.services.public_demo_guard import DEMO_ROUTING_OWNER_CLAIM, is_public_demo

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_ROUTING_RULES_PATH = "/api/admin/providers/routing-rules"

#: What a guest may change on the shared demo (docs/security.md, "Public demo mode"):
#: sign in and out, toggle the soft hold (the route itself refuses every other settings
#: key), and create a product within the normal limits.
DEMO_ADMIN_MUTATIONS_ALLOWED = frozenset({
    ("POST", "/api/admin/auth/login"),
    ("POST", "/api/admin/auth/logout"),
    ("POST", "/api/admin/auth/webauthn/login/options"),
    ("POST", "/api/admin/settings"),
    ("POST", "/api/admin/products/create"),
})

#: Reads that return personal data of other visitors or stored credentials.
DEMO_ADMIN_READS_REFUSED = (
    "/api/admin/action-log",
    "/api/admin/security",
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


async def _is_owner_routing_save(request: Request) -> bool:
    if request.method != "PUT" or canonical_api_path(request.url.path).rstrip("/") != _ROUTING_RULES_PATH:
        return False
    try:
        admin = await get_current_admin(request, await security_scheme(request))
    except HTTPException:
        return False
    return admin.get(DEMO_ROUTING_OWNER_CLAIM) is True and admin.get("role") in {"admin", "super_admin"}


async def public_demo_readonly_middleware(request: Request, call_next):
    if is_public_demo():
        reason = demo_refusal(request.method, request.url.path)
        if reason and not await _is_owner_routing_save(request):
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
