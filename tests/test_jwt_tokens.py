"""PyJWT token helpers (supply-chain migration off python-jose)."""

from __future__ import annotations

import time

from core.jwt_tokens import decode_hs256_optional, encode_hs256


def test_encode_decode_roundtrip():
    secret = "0" * 48
    now = int(time.time())
    payload = {"sub": "cust-1", "exp": now + 3600, "iat": now}
    token = encode_hs256(payload, secret)
    out = decode_hs256_optional(token, secret)
    assert out is not None
    assert out["sub"] == "cust-1"


def test_expired_token_returns_none():
    secret = "0" * 48
    now = int(time.time()) - 7200
    token = encode_hs256({"sub": "x", "exp": now, "iat": now}, secret)
    assert decode_hs256_optional(token, secret) is None
