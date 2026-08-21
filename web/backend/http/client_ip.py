"""Resolve client IP behind trusted reverse proxies (nginx, Caddy, etc.)."""

from __future__ import annotations

import os

from fastapi import Request


def trusted_proxy_ips() -> frozenset[str]:
    raw = (os.environ.get("AIFACTORY_TRUSTED_PROXY_IPS") or "127.0.0.1,::1").strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else ""
    trusted = trusted_proxy_ips()
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded and peer in trusted:
        # X-Forwarded-For is "client, proxy1, proxy2, ..." — each hop APPENDS the
        # address it saw. The LEFTMOST entry is therefore attacker-controlled: a
        # client can send its own X-Forwarded-For that the edge proxy merely
        # appends to (nginx proxy_add_x_forwarded_for = "$http_x_forwarded_for,
        # $remote_addr"). Trusting the leftmost lets any client forge its IP and
        # bypass per-IP rate limits or spoof trusted-network admin checks.
        # Walk from the RIGHT and return the first address that is not itself a
        # trusted proxy — that is the real client as seen by our trusted edge.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        for addr in reversed(parts):
            if addr not in trusted:
                return addr
        # Every hop in the chain was a trusted proxy → fall back to the peer.
    if peer:
        return peer
    return "unknown"
