"""Security audit v3 fixes: WS Origin, Stripe webhook tolerance."""

from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import MagicMock

import pytest
from fastapi import WebSocketException

from web.backend.api.customer import _verify_stripe_signature
from web.backend.core import websocket_admin


def test_stripe_signature_rejects_stale_timestamp():
    secret = "whsec_test"
    body = b'{"id":"evt_1"}'
    old_ts = int(time.time()) - 400
    payload = f"{old_ts}.{body.decode()}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    header = f"t={old_ts},v1={sig}"
    assert _verify_stripe_signature(body, header, secret) is False


def test_stripe_signature_accepts_fresh_timestamp():
    secret = "whsec_test"
    body = b'{"id":"evt_1"}'
    ts = int(time.time())
    payload = f"{ts}.{body.decode()}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"
    assert _verify_stripe_signature(body, header, secret) is True


@pytest.mark.asyncio
async def test_ws_cookie_auth_rejects_foreign_origin(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    ws = MagicMock()
    ws.app.state.security_manager = MagicMock()
    ws.app.state.security_manager.decode_token.return_value = {"admin": True}
    ws.headers = {"origin": "https://evil.example"}
    ws.cookies = {"access_token": "tok"}
    with pytest.raises(WebSocketException) as exc:
        await websocket_admin.require_admin_websocket(ws)
    assert "Origin" in (exc.value.reason or "")


@pytest.mark.asyncio
async def test_ws_cookie_auth_allows_configured_origin(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    ws = MagicMock()
    ws.app.state.security_manager = MagicMock()
    ws.app.state.security_manager.decode_token.return_value = {"admin": True, "sub": "admin"}
    ws.headers = {"origin": "https://magic-ai-factory.com"}
    ws.cookies = {"access_token": "tok"}
    ws.scope = {}
    payload = await websocket_admin.require_admin_websocket(ws)
    assert payload.get("admin") is True
