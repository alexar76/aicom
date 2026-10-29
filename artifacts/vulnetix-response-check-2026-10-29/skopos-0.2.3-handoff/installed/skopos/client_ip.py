"""Resolve the CALLER's address — never a value the caller chose.

Both of SKOPOS's per-address budgets were keyed on an attacker-controlled string. The nginx
in front of the service sets both headers:

    proxy_set_header X-Real-IP $remote_addr;                      # nginx overwrites this
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # APPENDS to the client's

``$proxy_add_x_forwarded_for`` appends the real peer to the RIGHT of whatever arrived, so the
LEFT-most hop is whatever the client typed. Reading it left-first meant:

* the DB-persisted login lockout (5 attempts / 300 s) could be given a fresh bucket per
  guess, leaving the operator dashboard password open to unmetered online guessing;
* the ``/agent/chat`` LLM-spend limiter — which exists so a stolen agent token cannot burn
  unbounded paid calls — got a fresh empty bucket per request.

The shape here is the one ATLAS already uses (``atlas/atlas/main.py:_client_ip``): proxy
headers are evidence only when the direct peer IS our own proxy; otherwise they are a
stranger's claim. Then prefer ``X-Real-IP``, and fall back to counting ``X-Forwarded-For``
from the RIGHT, because our hop is the one on the right.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
import time

#: How many proxies sit in front of us. 1 = the local nginx. 0 disables header trust.
def trusted_proxy_hops() -> int:
    try:
        return max(0, int(os.environ.get("SKOPOS_TRUSTED_PROXY_HOPS", "1")))
    except (TypeError, ValueError):
        return 1


# Which TCP peers may name the caller through X-Real-IP / X-Forwarded-For. Loopback only by default:
# trusting every private address let any neighbour on the same docker network or LAN send its own
# (the class of Vulnetix GCVE-110-VULN-PYPI-2026-000636). SKOPOS_TRUSTED_PROXIES is a comma list of
# addresses, CIDRs, host names (a compose service such as the frontend's nginx, looked up again
# every minute) and `gateway` (this container's default route: the host's nginx, when the port is
# published on the host).
_TRUSTED_PROXIES_DEFAULT = "127.0.0.1/32,::1/128"
_PROXY_NAME_TTL = 60.0
_PROC_NET_ROUTE = "/proc/net/route"
_proxy_names: dict[str, tuple[float, tuple]] = {}


def _default_gateway() -> str | None:
    """The IPv4 default route's gateway, from /proc/net/route (Linux), or None."""
    try:
        with open(_PROC_NET_ROUTE, encoding="ascii", errors="replace") as fh:
            next(fh, None)  # the header line
            for line in fh:
                f = line.split()
                if len(f) > 2 and f[1] == "00000000":
                    raw = bytes.fromhex(f[2])
                    return str(ipaddress.IPv4Address(raw[::-1] if sys.byteorder == "little" else raw))
    except (OSError, ValueError):
        return None
    return None


def _proxy_name_addresses(name: str) -> tuple:
    now = time.monotonic()
    hit = _proxy_names.get(name)
    if hit and now - hit[0] < _PROXY_NAME_TTL:
        return hit[1]
    try:
        found = {ipaddress.ip_address(info[4][0].split("%")[0])
                 for info in socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)}
    except (OSError, ValueError):
        found = set()
    addrs = tuple(sorted(found, key=str))
    _proxy_names[name] = (now, addrs)
    return addrs


def _peer_is_trusted_proxy(peer: str) -> bool:
    """Is the TCP peer one of SKOPOS_TRUSTED_PROXIES?"""
    try:
        addr = ipaddress.ip_address((peer or "").split("%")[0])
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    raw = os.environ.get("SKOPOS_TRUSTED_PROXIES")
    for entry in (_TRUSTED_PROXIES_DEFAULT if raw is None else raw).split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry == "gateway":
            gateway = _default_gateway()
            if gateway and addr == ipaddress.ip_address(gateway):
                return True
            continue
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
            continue
        except ValueError:
            pass
        if addr in _proxy_name_addresses(entry):
            return True
    return False


def peer_is_local_proxy(peer: str) -> bool:
    """Is the direct TCP peer our own reverse proxy (SKOPOS_TRUSTED_PROXIES; loopback by default)?

    A direct caller's headers carry no authority. Trusting every private address let a neighbour on
    the same docker network or LAN name its own address."""
    return _peer_is_trusted_proxy((peer or "").strip())


def resolve(peer: str, get_header) -> str:
    """The address to key a budget on.

    ``get_header`` is a callable taking a header name (case-insensitive lookup is the
    caller's job — both Streamlit's header map and http.client's are case-insensitive).
    """
    if trusted_proxy_hops() > 0 and peer_is_local_proxy(peer):
        real = str(get_header("X-Real-IP") or "").strip()
        if real:
            return real[:64]
        forwarded = str(get_header("X-Forwarded-For") or "").strip()
        if forwarded:
            hops = [h.strip() for h in forwarded.split(",") if h.strip()]
            if hops:
                want = trusted_proxy_hops()
                return (hops[-want] if len(hops) >= want else hops[-1])[:64]
    return (peer or "unknown")[:64]
