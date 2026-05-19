"""Authenticate admin WebSocket connections.

The JWT is accepted via, in priority order:
1. ``Authorization: Bearer <token>`` header (when the WS client supports custom headers).
2. ``Sec-WebSocket-Protocol`` subprotocol pair ``Bearer, <token>`` (browser-safe).
3. ``access_token`` cookie (same-site SSR clients).

The historical ``?token=<jwt>`` query parameter is no longer accepted because it
leaked tokens into reverse-proxy access logs and browser history.

When the subprotocol path is used, the selected subprotocol (``Bearer``) is
returned via :func:`selected_admin_subprotocol` so the caller can echo it back
on ``websocket.accept`` — required by the WebSocket handshake.
"""

from __future__ import annotations

from fastapi import WebSocket, WebSocketException, status


_BEARER_PROTOCOL = "Bearer"


def _extract_subprotocol_token(websocket: WebSocket) -> tuple[str, bool]:
    """Return ``(token, used_subprotocol)`` parsed from ``Sec-WebSocket-Protocol``.

    Browsers cannot set arbitrary headers on a WebSocket handshake, but they can
    declare subprotocols. By convention we send two values: the literal
    ``Bearer`` selector and the JWT itself. The server picks ``Bearer`` as the
    chosen subprotocol and consumes the JWT.
    """
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
    if not token:
        token = (websocket.cookies.get("access_token") or "").strip()

    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated")

    payload = security_manager.decode_token(token)
    if not payload or not payload.get("admin"):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")

    if used_subprotocol:
        # Stash on the connection so the caller can pass it to ``accept``.
        websocket.scope["_admin_ws_subprotocol"] = _BEARER_PROTOCOL
    return payload


def selected_admin_subprotocol(websocket: WebSocket) -> str | None:
    """Return the subprotocol to echo back on ``websocket.accept``, if any."""
    value = websocket.scope.get("_admin_ws_subprotocol") if websocket.scope else None
    return value if isinstance(value, str) else None
