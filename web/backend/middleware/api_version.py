"""
API versioning: ``/api/v1/*`` rewrites to ``/api/*`` so clients can pin a major version.

Legacy unversioned ``/api/*`` routes remain unchanged for backward compatibility.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

_V1_PREFIX = "/api/v1"


def canonical_api_path(path: str) -> str:
    """The path routing will actually see, for middleware that matches on it.

    ``ApiVersionMiddleware`` is added FIRST in web/backend/main.py, which in Starlette
    makes it the INNERMOST middleware — so every middleware layered on top of it
    (CSRF, firewall, security headers) observes the un-rewritten ``/api/v1/...`` path
    while the route that eventually runs is ``/api/...``. Any guard that decides by
    prefix must canonicalize first, or ``/api/v1`` is a bypass of that guard.
    """
    if path == _V1_PREFIX or path.startswith(_V1_PREFIX + "/"):
        return f"/api{path[len(_V1_PREFIX):] or ''}"
    return path


class ApiVersionMiddleware:
    """Rewrite ``/api/v1/...`` → ``/api/...`` before routing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            if path == _V1_PREFIX or path.startswith(_V1_PREFIX + "/"):
                suffix = path[len(_V1_PREFIX) :] or ""
                scope = dict(scope)
                scope["path"] = f"/api{suffix}"
        await self.app(scope, receive, send)
