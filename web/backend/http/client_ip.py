"""Resolve client IP behind trusted reverse proxies (nginx, Caddy, etc.)."""

from __future__ import annotations

import os

from fastapi import Request


def trusted_proxy_ips() -> frozenset[str]:
    raw = (os.environ.get("AIFACTORY_TRUSTED_PROXY_IPS") or "127.0.0.1,::1").strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else ""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded and peer in trusted_proxy_ips():
        return forwarded.split(",")[0].strip()
    if peer:
        return peer
    return "unknown"
