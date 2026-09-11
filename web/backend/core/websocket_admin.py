"""Authenticate admin WebSocket connections.

The JWT is accepted via, in priority order:
1. ``Authorization: Bearer <token>`` header (when the WS client supports custom headers).
2. ``Sec-WebSocket-Protocol`` subprotocol pair ``Bearer, <token>`` (browser-safe).
3. ``access_token`` cookie (same-site admin UI only — requires allowed ``Origin``).

The historical ``?token=<jwt>`` query parameter is no longer accepted because it
leaked tokens into reverse-proxy access logs and browser history.

Cross-site WebSocket hijacking: when the browser sends cookies, ``Origin`` must match
``AIFACTORY_CORS_ORIGINS`` / ``NEXT_PUBLIC_SITE_URL`` allowlist.
"""

from __future__ import annotations

from fastapi import WebSocket, WebSocketException, status

from web.backend.cors_settings import get_cors_allow_origins

_BEARER_PROTOCOL = "Bearer"


def _allowed_ws_origins() -> set[str]:
    return {o.strip().rstrip("/") for o in get_cors_allow_origins() if o.strip()}


def _normalize_origin(websocket: WebSocket) -> str:
    return (websocket.headers.get("origin") or "").strip().rstrip("/")


def _enforce_ws_origin(websocket: WebSocket, *, cookie_auth: bool) -> None:
    origin = _normalize_origin(websocket)
    allowed = _allowed_ws_origins()
    if cookie_auth:
        if not origin or origin not in allowed:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Cookie auth requires allowed Origin",
            )
        return
    if origin and origin not in allowed:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Origin not allowed",
        )


def _extract_subprotocol_token(websocket: WebSocket) -> tuple[str, bool]:
    """Return ``(token, used_subprotocol)`` parsed from ``Sec-WebSocket-Protocol``."""
    raw = websocket.headers.get("sec-websocket-protocol") or ""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) < 2:
        return "", False
    if parts[0] != _BEARER_PROTOCOL:
        return "", False
    return parts[1], True


async def require_admin_websocket(websocket: WebSocket) -> dict:
    security_manager = getattr(websocket.app.state, "security_manager", None)
    if security_manager is None:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="Security not initialized")

    used_subprotocol = False
    token = ""
    auth = (websocket.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token, used_subprotocol = _extract_subprotocol_token(websocket)

    cookie_auth = False
    if not token:
        token = (websocket.cookies.get("access_token") or "").strip()
        cookie_auth = bool(token)

    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated")

    _enforce_ws_origin(websocket, cookie_auth=cookie_auth)

    payload = security_manager.decode_token(token)
    if not payload or not payload.get("admin"):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")

    if used_subprotocol:
        websocket.scope["_admin_ws_subprotocol"] = _BEARER_PROTOCOL
    return payload


def selected_admin_subprotocol(websocket: WebSocket) -> str | None:
    """Return the subprotocol to echo back on ``websocket.accept``, if any."""
    value = websocket.scope.get("_admin_ws_subprotocol") if websocket.scope else None
    return value if isinstance(value, str) else None
