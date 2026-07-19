"""
API versioning: ``/api/v1/*`` rewrites to ``/api/*`` so clients can pin a major version.

Legacy unversioned ``/api/*`` routes remain unchanged for backward compatibility.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

_V1_PREFIX = "/api/v1"


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
