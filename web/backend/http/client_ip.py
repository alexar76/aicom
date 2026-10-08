"""Resolve client IP behind trusted reverse proxies (nginx, Caddy, etc.)."""

from __future__ import annotations

import ipaddress
import logging
import os

from fastapi import Request

logger = logging.getLogger(__name__)
_warned_untrusted_peer = False


def trusted_proxy_ips() -> frozenset[str]:
    """Addresses or CIDR networks whose X-Forwarded-For is believed.

    Behind a published container port the backend's peer is the docker bridge gateway
    (e.g. 172.18.0.1), not 127.0.0.1 — with only the loopback default every visitor shares
    that one address, so per-IP limits become global (5 bad passwords lock out every admin).
    Name the gateway (or the edge proxy) here; a network such as 172.18.0.0/16 also works.
    """
    raw = (os.environ.get("AIFACTORY_TRUSTED_PROXY_IPS") or "127.0.0.1,::1").strip()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _is_trusted(addr: str, trusted: frozenset[str]) -> bool:
    if addr in trusted:
        return True
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for entry in trusted:
        if "/" in entry:
            try:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
    return False


def _warn_untrusted_private_peer(peer: str) -> None:
    global _warned_untrusted_peer
    if _warned_untrusted_peer:
        return
    try:
        private = ipaddress.ip_address(peer).is_private
    except ValueError:
        return
    if private:
        _warned_untrusted_peer = True
        logger.warning(
            "X-Forwarded-For arrives from %s, which is not in AIFACTORY_TRUSTED_PROXY_IPS: "
            "every client is keyed on that one address, so per-IP limits are global", peer)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else ""
    trusted = trusted_proxy_ips()
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded and peer and not _is_trusted(peer, trusted):
        _warn_untrusted_private_peer(peer)
    if forwarded and _is_trusted(peer, trusted):
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
            if not _is_trusted(addr, trusted):
                return addr
        # Every hop in the chain was a trusted proxy → fall back to the peer.
    if peer:
        return peer
    return "unknown"
