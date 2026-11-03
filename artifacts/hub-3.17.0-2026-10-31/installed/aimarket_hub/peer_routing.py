"""Routing a call to a peer hub: where its invoke goes (cached per peer from its well-known),
whether its buyers pay it directly, the payment headers that travel back, the opaque ids a
peer and a provider are given instead of a buyer's address or channel, and the bounds on
numbers a peer reports. Moved out of api.py, which re-exports every name.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import secrets
import time
from typing import Any

from aimarket_hub.federation_transport import peer_is_aimarket_hub

logger = logging.getLogger(__name__)


# Upper bounds for peer-reported accounting numbers. Rejecting an out-of-range value
# outright would let a peer erase its own stats, so we clamp instead — but the clamp
# must exist: `int(1e30)` is a valid Python int and a fatal one for SQLite
# ("Python int too large to convert to SQLite INTEGER"), which turned a hostile
# latency_ms into an unhandled 500 on the federated invoke path.
_MAX_REPORTED_PRICE_USD = 1_000_000.0


_MAX_REPORTED_LATENCY_MS = 2_147_483_647  # int32, safely inside SQLite's 8-byte INTEGER


def _as_float(value: Any, *, max_value: float | None = None) -> float:
    """Coerce a peer-supplied number to a finite, non-negative float (0.0 otherwise).

    Federated accounting (routing fee, invocation stats) reads price/latency straight
    out of a remote hub's response body, which the hub does not control. A string,
    None, NaN or negative value there would either raise inside the fee arithmetic
    (surfacing as a 500) or record nonsense — so an unusable number bills nothing.
    ``max_value`` additionally clamps a merely absurd (but finite) number, because a
    finite value can still be fatal downstream — see _MAX_REPORTED_LATENCY_MS.
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(num) or num < 0:
        return 0.0
    if max_value is not None and num > max_value:
        return float(max_value)
    return num


#: A peer's payment headers that travel back to the buyer unchanged: the x402 V2 offer, the
#: settlement response of either dialect, and the invoice nonce a seller-direct door names.
_PEER_PAYMENT_HEADERS = ("payment-required", "payment-response", "x-payment-response",
                         "x-payment-nonce")


def _peer_payment_headers(resp: Any) -> dict[str, str]:
    """The peer's payment headers to forward, plus the CORS exposure a browser buyer needs."""
    out = {k: v for k, v in resp.headers.items() if k.lower() in _PEER_PAYMENT_HEADERS}
    if out:
        out["Access-Control-Expose-Headers"] = ", ".join(sorted(out))
    return out


# ── Federated transport resolution ─────────────────────────────
#
# Which URL a routed invoke is POSTed to. A peer that publishes `mcp_endpoint` in
# its `/.well-known/ai-market.json` is telling us where to send invokes; a peer
# that does not gets the legacy `/capabilities/{product}/{cap}/invoke` path.
#
# This used to be decided by matching the peer's self-declared categories against a
# hardcoded list — ("oracle", "simulation", "math-viz", "randomness-beacon") — and
# only those four peers were asked for their endpoint. Every other peer got the
# legacy path regardless of what it advertised. GAIA, the physical-world sensor
# gateway, declares `["iot", "sensors", "physical-data", "verification"]` and
# advertises `mcp_endpoint: https://iot.modelmarket.dev/ai-market/v2/invoke`; the
# hub POSTed the legacy path instead, that path answers 405, and every routed
# invoke of a live, priced, signed sensor reading came back as
# `502 Provider returned 405`. A category string is a label a peer chose for
# discovery; the endpoint it publishes is an instruction. Read the instruction.
_PEER_ENDPOINT_TTL_S = 300.0


_peer_endpoint_cache: dict[str, tuple[float, str | None]] = {}


# Read from the same well-known fetch: does the peer declare that buyers pay its listings
# directly (payment_rails.seller_direct.enabled)? Decides the routing fee — see invoke.
_peer_seller_direct: dict[str, bool] = {}


# The rule itself lives in `federation_transport` because the admission assay needs the
# same answer: it kept its own copy, read `mcp_endpoint` verbatim, and could never
# sandbox-probe a hub peer. Re-exported under the old name so this module's callers and
# tests are unaffected.
_peer_is_aimarket_hub = peer_is_aimarket_hub


# The salt is per process unless AIMARKET_BUYER_SALT pins it: a peer needs a buyer id that is
# stable for as long as its rate window, not forever, and an id that cannot be linked across hubs
# or back to an address.
_BUYER_SALT = (os.environ.get("AIMARKET_BUYER_SALT") or "").encode() or secrets.token_bytes(32)


def _opaque_buyer(rate_key: str | None) -> str:
    """An opaque, stable id for one buyer as seen by THIS hub, sent to peers on routed invokes.

    It is an HMAC of the key this hub rate-limits the buyer by (their address, or their sandbox
    visitor id) — never the address, channel or account itself, which are this hub's business.
    A peer can give each buyer their own quota with it; it cannot tell who they are.
    """
    import hmac as _hmac

    digest = _hmac.new(_BUYER_SALT, (rate_key or "anonymous").encode(), hashlib.sha256).hexdigest()
    return "b-" + digest[:20]


def _provider_channel_ref(channel_id: str | None) -> str:
    """What a provider this hub executes is told about the buyer's payment channel.

    The raw channel id used to be forwarded as X-Payment-Channel. It is the ledger's handle
    for hold/debit/close. Before the fail-closed secret check, a secretless channel's id
    alone authorized those calls — every provider a buyer called learned enough to spend
    that buyer's balance on its own listings. Secretless channels are now frozen. No
    provider needs the id itself: the oracles read the header's PRESENCE (a trusted proxy
    forwarding a paying call, oracle_core/tiers.py), the attested apps hash it into an
    actor id, and the factory's channels live in a different ledger that never held it.

    So the provider gets an HMAC reference: present exactly when the buyer sent a channel,
    the same for every call on that channel, and not a channel id any ledger will find.
    """
    raw = (channel_id or "").strip()
    if not raw:
        return ""
    import hmac as _hmac

    digest = _hmac.new(
        _BUYER_SALT, b"provider-channel-ref\x00" + raw.encode(), hashlib.sha256,
    ).hexdigest()
    return "chref-" + digest[:24]


async def _peer_invoke_endpoint(peer: Any, *, now: float | None = None) -> str | None:
    """The peer's advertised invoke endpoint, or None to use the legacy path.

    Cached per peer URL: resolving it costs a well-known fetch, and doing that on
    every routed invoke would add a round trip to each call. A negative result is
    cached too, so a peer with no `mcp_endpoint` is not re-probed per invoke.
    """
    key = getattr(peer, "url", "") or ""
    stamp = time.time() if now is None else now
    hit = _peer_endpoint_cache.get(key)
    if hit is not None and stamp - hit[0] < _PEER_ENDPOINT_TTL_S:
        return hit[1]

    endpoint: str | None = None
    well_known = getattr(peer, "well_known_url", "") or ""
    if well_known:
        try:
            from aimarket_hub.outbound_http import safe_get

            resp = await safe_get(well_known, timeout=10)
            if resp.status_code == 200:
                doc = resp.json() or {}
                rails = doc.get("payment_rails") if isinstance(doc, dict) else None
                direct = rails.get("seller_direct") if isinstance(rails, dict) else None
                _peer_seller_direct[key] = bool(isinstance(direct, dict) and direct.get("enabled") is True)
                # An AIMarket hub is NOT reachable at its own `mcp_endpoint` with this
                # envelope: that endpoint speaks MCP JSON-RPC over SSE, so posting
                # `{capability_id, input}` there returns `Method not found` inside a
                # text/event-stream body and the routed call dies as "provider returned a
                # non-JSON body". Hub-to-hub routing was therefore impossible — which is
                # why every peer in the live federation is an oracle or a satellite and
                # never another hub. A peer that declares itself a hub gets its v2 invoke
                # route, which speaks exactly the envelope we are about to send.
                if _peer_is_aimarket_hub(doc):
                    base = str(getattr(peer, "url", "") or "").rstrip("/")
                    endpoint = f"{base}/ai-market/v2/invoke" if base else None
                else:
                    advertised = doc.get("mcp_endpoint")
                    if isinstance(advertised, str) and advertised.strip():
                        candidate = advertised.strip()
                        # A peer names WHERE ON ITSELF to send, never where to send. The
                        # crawler, reading this same field, keeps it "only when it is safe
                        # and same-origin: a peer that could store an arbitrary URL here
                        # would have a stored SSRF pointer" — and this is the reader that
                        # actually POSTs, with the caller's `input` in the body and the
                        # response handed back. Same rule here, or the careful one upstream
                        # was protecting the display copy and nothing else.
                        from aimarket_hub.federation_assay import same_origin

                        # SAME-ORIGIN is the whole rule, and deliberately not also
                        # `_url_is_safe`. The peer's own URL was already address-checked when
                        # it was admitted, and `safe_post` pins the resolved IP at send time,
                        # so a same-origin endpoint is the destination we would have used
                        # anyway — no reachability is gained. Adding a DNS-dependent check
                        # here instead made TRANSPORT SELECTION depend on whether the peer
                        # resolved at that instant: an unresolvable-but-legitimate host got
                        # silently rerouted to a different path. The address question belongs
                        # where the connection is made, not where the route is chosen.
                        peer_url = str(getattr(peer, "url", "") or "")
                        if same_origin(peer_url, candidate):
                            endpoint = candidate
                        else:
                            logger.warning(
                                "invoke: peer %s advertised an mcp_endpoint we will not "
                                "follow (%r); using its own invoke route instead",
                                peer_url, candidate[:200],
                            )
                            base = peer_url.rstrip("/")
                            endpoint = f"{base}/ai-market/v2/invoke" if base else None
        except Exception as exc:  # unreachable well-known → legacy path, not an error
            logger.warning("invoke: well-known lookup failed for %s: %s", key, exc)
            # Do NOT cache a transport decision made from a failed lookup: the peer
            # may be momentarily down while still being a v2 peer, and caching the
            # fallback would pin it to the wrong transport for the whole TTL.
            return None

    _peer_endpoint_cache[key] = (stamp, endpoint)
    return endpoint


async def _peer_sells_direct(peer: Any) -> bool:
    """True when the peer's own well-known says its buyers pay its listings directly.

    Resolved by the same cached well-known read as the invoke endpoint, so it costs no
    extra fetch per call. An unreadable well-known is False: the old fee rule applies.
    """
    await _peer_invoke_endpoint(peer)
    return _peer_seller_direct.get(getattr(peer, "url", "") or "", False)
