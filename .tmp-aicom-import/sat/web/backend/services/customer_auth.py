"""Shared customer JWT helpers for storefront and AI Market APIs."""

from __future__ import annotations

from fastapi import Header, HTTPException

from web.backend.services.commerce import CommerceService

_commerce = CommerceService()


def decode_customer(authorization: str | None) -> dict | None:
    """Decode ``Authorization: Bearer`` JWT; ``None`` if absent."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    payload = _commerce.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired customer token")
    return payload


def require_customer(authorization: str | None = Header(default=None)) -> dict:
    payload = decode_customer(authorization)
    if not payload:
        raise HTTPException(status_code=401, detail="Missing customer token")
    customer_id = str(payload.get("sub") or "").strip()
    customer_email = str(payload.get("email") or "").strip()
    if not customer_id or not customer_email:
        raise HTTPException(status_code=401, detail="Customer token missing identity claims")
    return payload
