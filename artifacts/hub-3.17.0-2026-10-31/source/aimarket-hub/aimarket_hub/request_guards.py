"""What the hub checks in a request before trusting it: the client address behind a declared
proxy, the in-memory rate-limit table's bound, per-subject token registries, path-segment ids
and caller-supplied money amounts. Moved out of api.py, which re-exports every name.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import os
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.@")


def _money_arg(value: Any, field: str, *, allow_zero: bool = True) -> float:
    """Parse a caller-supplied USD amount or raise HTTP 400.

    Guards the stake/bond routes. ``float()`` alone is not enough: JSON bodies reach
    these handlers as free-form dicts, and both ``"inf"`` and a bare ``Infinity``
    literal survive json.loads → float(). A non-finite stake credit is written to the
    ledger BEFORE the response is serialized, so it persisted an infinite stake (and an
    infinite hub trust-anchor edge) for an arbitrary publisher_id and only then failed
    with a 500 — i.e. the error surfaced after the damage, not instead of it.
    """
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be a number") from exc
    if not math.isfinite(num):
        raise HTTPException(status_code=400, detail=f"{field} must be a finite number")
    if num < 0 or (num == 0 and not allow_zero):
        raise HTTPException(status_code=400, detail=f"{field} must be positive")
    return num


def _trim_rate_buckets(
    buckets: dict[str, list[float]], window: float, max_keys: int, keep: str,
) -> None:
    """Bound the in-memory invoke-rate table in place.

    Expired buckets go first — they carry no state at all. Evicting only those is not
    a bound though: enough distinct client addresses inside a single window keeps every
    bucket live and the dict grows without limit (memory DoS via source rotation). So
    if the table is still over the cap we drop the least-recently-active buckets, which
    are the ones closest to expiring anyway. ``keep`` is the bucket we just charged; it
    must survive, otherwise the trim would hand the caller a fresh window.
    """
    for key in [k for k, v in buckets.items() if not v or v[-1] <= window]:
        if key != keep:
            buckets.pop(key, None)
    excess = len(buckets) - max_keys
    if excess <= 0:
        return
    for key in sorted(buckets, key=lambda k: buckets[k][-1]):
        if excess <= 0:
            break
        if key == keep:
            continue
        buckets.pop(key, None)
        excess -= 1


def _env_positive_int(name: str, default: int) -> int:
    """Non-negative int env knob; garbage keeps the default (0 = limiter disabled)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r, using %d", name, raw, default)
        return default
    return value if value >= 0 else default


def _parse_subject_tokens(raw: str, env_name: str) -> dict[str, str]:
    """Parse a per-subject credential registry ("subj-a:secretA,subj-b:secretB").

    Used for BOTH namespaced registries — ``AIMARKET_PUBLISHER_TOKENS`` (publisher ids)
    and ``AIMARKET_AGENT_TOKENS`` (agent ids). One parser, so the two registries cannot
    drift on what a malformed entry means. Malformed entries are dropped with a warning
    naming the registry rather than silently becoming a subject named "" — an empty id
    would match every unnamed caller.
    """
    out: dict[str, str] = {}
    for part in (raw or "").split(","):
        entry = part.strip()
        if not entry:
            continue
        subject, sep, token = entry.partition(":")
        subject, token = subject.strip(), token.strip()
        if not sep or not subject or not token:
            logger.warning("Ignoring malformed %s entry (want <id>:<token>)", env_name)
            continue
        out[subject] = token
    return out


def _parse_trusted_proxies(raw: str) -> frozenset[str]:
    """Addresses whose ``X-Forwarded-For`` this hub is willing to believe.

    Empty by default: a hub with no declared proxy trusts NOTHING and keys its rate
    limits on the raw peer address. ``*`` is rejected on purpose — blanket-trusting the
    header lets any client name its own IP and hand itself a fresh rate-limit bucket per
    request, which is strictly worse than the one-shared-bucket problem this exists to
    fix.
    """
    out: set[str] = set()
    for part in (raw or "").split(","):
        entry = part.strip()
        if not entry:
            continue
        if entry == "*":
            logger.error(
                "AIMARKET_TRUSTED_PROXIES=* is refused: blanket-trusting "
                "X-Forwarded-For lets every caller forge its own client address. "
                "List the proxy address(es) explicitly (e.g. 127.0.0.1)."
            )
            continue
        out.add(entry)
    return frozenset(out)


#: Where a scraper of /metrics may connect from directly: loopback, the RFC 1918 ranges a
#: container network or an operator's LAN uses, and IPv6 unique-local addresses.
_INTERNAL_NETS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7",
))


def _client_address(request: Any, trusted_proxies: frozenset[str]) -> str:
    """The client address rate limits key on, honouring a declared reverse proxy.

    Behind ``deploy/nginx/*.conf`` the hub's peer is always the proxy (127.0.0.1 for a
    same-host nginx, the bridge gateway from a container), so keying on
    ``request.client.host`` alone put THE WHOLE INTERNET IN ONE BUCKET — the per-IP
    channel cap became a global cap and the LRU eviction the ledger leans on had nothing
    left to bound.

    ``X-Forwarded-For`` is consulted ONLY when the immediate peer is a declared proxy
    (``AIMARKET_TRUSTED_PROXIES``); an unlisted peer's header is ignored outright, so a
    direct caller cannot forge a client address.

    The list is walked RIGHT TO LEFT and the first entry that is not itself a trusted
    proxy wins. nginx uses ``$proxy_add_x_forwarded_for``, which APPENDS the real peer to
    whatever the client sent, so a client that sends ``X-Forwarded-For: 1.2.3.4`` produces
    ``1.2.3.4, <real client>``: reading left-to-right would take the forged value, while
    the rightmost untrusted entry is the address nginx itself observed.
    """
    peer = ""
    client = getattr(request, "client", None)
    if client is not None:
        peer = str(getattr(client, "host", "") or "").strip()
    if not peer or peer not in trusted_proxies:
        return peer
    headers = getattr(request, "headers", None)
    raw = ""
    if headers is not None:
        try:
            raw = headers.get("x-forwarded-for") or ""
        except Exception:
            raw = ""
    for hop in reversed([h.strip() for h in str(raw).split(",")]):
        if hop and hop not in trusted_proxies:
            return hop
    # Every hop is a trusted proxy (or the header is absent): the proxy itself is the
    # only address we can attribute this request to. Not exempt — one shared bucket.
    return peer


def _announced_relay(peer: str, xff: str, trusted_proxies: frozenset[str]) -> bool:
    """A caller that is not our proxy but forwards for somebody else (it sent X-Forwarded-For).

    Careful with what uvicorn already did: with AIMARKET_TRUSTED_PROXIES set, its
    ProxyHeadersMiddleware replaces the socket peer by the rightmost untrusted X-Forwarded-For
    hop BEFORE the app runs, so every request nginx relays arrives with an untrusted "peer" and
    the header still present. That peer then EQUALS the header's rightmost untrusted hop; a real
    relay's own address does not. (X-Real-IP is no signal at all: nginx sets it on every call.)
    """
    if not xff or not peer or peer in trusted_proxies:
        return False
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        if hop not in trusted_proxies:
            return hop != peer
    return False


def _is_safe_path(segment: str) -> bool:
    """Reject path traversal in product/capability ids used in upstream URLs."""
    if not segment or len(segment) > 80:
        return False
    if ".." in segment or "/" in segment or "\\" in segment:
        return False
    return all(c in _SAFE_ID_CHARS for c in segment)
