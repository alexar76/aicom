"""CORS for opaque-origin sandbox preview iframes (Origin: null).

Default preview iframe omits ``allow-same-origin``, so the document has an opaque
origin and browser fetches send ``Origin: null``. Global CORSMiddleware uses
``allow_credentials=True`` with an explicit allow-list and never reflects null —
those fetches fail with NetworkError.

Only sandbox file + reverse-proxy paths get ``Access-Control-Allow-Origin: null``,
never with credentials. Auth remains ``X-Sandbox-Preview-Token`` (fetch shim also
forces ``credentials: 'omit'``).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from web.backend.middleware.api_version import canonical_api_path

_SANDBOX_OPAQUE_CORS_PREFIXES = (
    "/api/sandbox/file/",
    "/api/sandbox/compose/",
    "/api/sandbox/backend/",
)


def sandbox_opaque_cors_path(path: str) -> bool:
    """Paths an opaque-origin preview iframe may fetch (not the viewer shell)."""
    path = canonical_api_path(path)
    return any(path.startswith(p) for p in _SANDBOX_OPAQUE_CORS_PREFIXES)


def apply_sandbox_opaque_cors(response: Response) -> Response:
    """Reflect ``Origin: null`` without credentials — preview token is the only auth."""
    response.headers["Access-Control-Allow-Origin"] = "null"
    response.headers["Vary"] = "Origin"
    if "access-control-allow-credentials" in response.headers:
        del response.headers["access-control-allow-credentials"]
    return response


async def sandbox_opaque_origin_cors(request: Request, call_next):
    origin = (request.headers.get("origin") or "").strip()
    if origin != "null" or not sandbox_opaque_cors_path(request.url.path):
        return await call_next(request)

    if request.method == "OPTIONS":
        requested = (request.headers.get("access-control-request-headers") or "").strip()
        allow_headers = requested or (
            "X-Sandbox-Preview-Token, Content-Type, Accept, Authorization"
        )
        return apply_sandbox_opaque_cors(
            Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Methods": (
                        "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"
                    ),
                    "Access-Control-Allow-Headers": allow_headers,
                    "Access-Control-Max-Age": "600",
                },
            )
        )

    return apply_sandbox_opaque_cors(await call_next(request))
