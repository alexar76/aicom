"""Hub-driven federation discovery for the Alien Monitor.

The monitor used to render a hand-written node list and only polled the hub's
``/ai-market/v2/stats/live``. New ecosystem nodes (e.g. Platon) never appeared
unless someone edited the topology by hand. This module closes that gap: it asks
the AIMarket Hub for its federation peers, reads each peer's self-declared
``/.well-known/ai-market.json`` categories, and — for nodes that advertise a
relevant capability (oracle / simulation / math-viz / randomness-beacon) — emits
a graph node hydrated with live metrics from the peer's protocol-native health
endpoint (or ``/api/health`` for a capability service). Nothing is hardcoded;
a node appears the moment the hub knows about it.

Security (the monitor fetches URLs the hub hands it, so they are untrusted):
  * SSRF guard — private/loopback/link-local/metadata ranges are blocked by
    default (opt in with allow_private for local universe sims). DNS is resolved,
    every returned IP is checked, and IPv6-embedded IPv4 forms (mapped, 6to4,
    NAT64, v4-compatible) are decoded and re-checked. For plain-HTTP peers the
    connection is **pinned to the vetted IP** (Host header preserved) so a
    rebind between the check and httpx's own resolution cannot reach an internal
    address (closes the classic getaddrinfo/connect TOCTOU for the http path).
  * Hard per-request and per-peer wall-clock deadlines (asyncio.wait_for) on top
    of httpx's per-read timeout, so a slowloris peer dribbling bytes can never
    hang the monitor tick or hold the state lock.
  * Response-size caps, JSON content-type required, redirects disabled, bounded
    fan-out + concurrency, a (url, allow_private)-keyed TTL cache, and strict
    numeric coercion (only finite, magnitude-bounded scalars reach node.metrics,
    which the frontend types as Record<string, number>).
  * Fault isolation — one bad/slow/malicious peer can never break the graph.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import socket
import threading
import time
from ipaddress import ip_address, ip_network
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

import foreign_contracts

logger = logging.getLogger(__name__)

USER_AGENT = "AlienMonitor-Discovery/1.0"

# Categories that make a federation peer worth rendering as a node.
_DEFAULT_CATEGORIES = {"oracle", "simulation", "math-viz", "randomness-beacon", "beacon"}

def _reserved_ids() -> frozenset[str]:
    """Node ids a discovered peer may never claim — DERIVED from the map, not transcribed.

    The hand-written copy of this set stopped at `percola` and so left six real oracle ids
    (sortes, gauss, aestus, betti, kantor, fourier) claimable by any peer that named itself
    after one. A list that has to be edited when the map grows is a list that will be out of
    date exactly when it matters: reading the map itself cannot drift.
    """
    from ecosystem_layout import NODE_POSITIONS
    from oracle_family import ORACLE_FAMILY, oracle_node_id

    return frozenset(NODE_POSITIONS) | {
        oracle_node_id(str(o.get("slug") or "")) for o in ORACLE_FAMILY if o.get("slug")
    } | {
        # Named here because they are not positions on the map: the cave is a scene, and
        # `signal_hunt` is the game beside the hub that carries its name.
        "oracle-cave-platon", "signal_hunt",
    }


_RESERVED_IDS = _reserved_ids()

# The 3D anchor of the "federation" node in build_topology()/seed_entities().
_FED_ANCHOR = (-2.0, 5.0, 1.0)

_MAX_RESPONSE_BYTES = 512_000  # 0.5 MB cap for well-known / health
_METRIC_MAGNITUDE_CAP = 1_000_000_000_000  # clamp peer-supplied numbers

# Blocked IP ranges (RFC1918, loopback, link-local, cloud metadata, multicast).
_BLOCKED_NETS = [
    ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"), ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"), ip_network("0.0.0.0/8"),
    ip_network("100.64.0.0/10"), ip_network("224.0.0.0/4"),
    ip_network("fc00::/7"), ip_network("fe80::/10"), ip_network("::1/128"),
]
_NAT64 = ip_network("64:ff9b::/96")


# ── SSRF guard ──────────────────────────────────────────────────────


def _embedded_ipv4(addr):
    """Decode an embedded IPv4 from IPv4-mapped / 6to4 / NAT64 / v4-compatible IPv6."""
    for attr in ("ipv4_mapped", "sixtofour"):
        v = getattr(addr, attr, None)
        if v is not None:
            return v
    if getattr(addr, "version", 4) == 6:
        try:
            if addr in _NAT64:
                return ip_address(int(addr) & 0xFFFFFFFF)
            packed = int(addr)
            if packed >> 32 == 0 and (packed & 0xFFFFFFFF) > 1:  # ::a.b.c.d (not ::/::1)
                return ip_address(packed & 0xFFFFFFFF)
        except ValueError:
            return None
    return None


def _blocked_ip(addr) -> bool:
    """True if an IP (or its embedded IPv4) falls in a blocked network."""
    if any(addr in net for net in _BLOCKED_NETS):
        return True
    emb = _embedded_ipv4(addr)
    if emb is not None and any(emb in net for net in _BLOCKED_NETS):
        return True
    return False


def _resolved_ips(hostname: str) -> list:
    """Return parsed IPs for a hostname (literal or DNS), or [] if unresolvable."""
    try:
        return [ip_address(hostname)]
    except ValueError:
        pass
    try:
        out = []
        for info in socket.getaddrinfo(hostname, None):
            try:
                out.append(ip_address(info[4][0]))
            except ValueError:
                continue
        return out
    except (socket.gaierror, UnicodeError, ValueError):
        return []


def _is_private_host(hostname: str) -> bool:
    """True if a hostname is (or resolves to) a blocked network. Fail-closed."""
    if not hostname:
        return True
    ips = _resolved_ips(hostname)
    if not ips:
        return True  # unresolvable → unsafe
    return any(_blocked_ip(a) for a in ips)


def _displayable_url(url: str) -> bool:
    """An http(s) URL with a host and nothing a link should not carry."""
    if not url or any(ch.isspace() or ord(ch) < 0x20 or ch in "<>\"'`" for ch in url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def url_is_safe(url: str, *, allow_private: bool | str = False) -> bool:
    """Reject non-http(s) schemes, header-injection chars, and internal hosts.

    ``allow_private`` has three settings, and the middle one is why:

    * ``False`` — the default. Resolve, refuse anything private/loopback/link-local.
    * ``"loopback"`` — resolve, and permit ONLY loopback. This is what a PEER-supplied URL
      gets in UNI mode: the sim legitimately talks to hubs it spawned on 127.0.0.1, and
      nothing else about a stranger's document earns a private-network exemption.
    * ``True`` — no resolution at all, any http(s) URL passes. Reserved for the
      operator-configured hub, which ``discover_async`` names explicitly.

    ``True`` used to be what every peer fetch got, because one flag on
    ``DiscoveryConfig`` covered both the trusted hub and everything the hub told us about.
    With it set, this function returned True unresolved and ``_pin_http_target`` skipped the
    re-vet — so both the private-range check and the DNS-rebinding defence were off for
    addresses a third party chose. A peer entry needs no operator: open federation
    auto-admits, and the hub republishes the announcer's own well_known_url verbatim.
    """
    if not url or not isinstance(url, str):
        return False
    if not url.startswith(("https://", "http://")):
        return False
    if any(c in url for c in "\r\n\t"):
        return False
    if allow_private is True:
        return True
    try:
        host = urlparse(url).hostname or ""
        if not host:
            return False
        if not _is_private_host(host):
            return True
        return allow_private == "loopback" and _is_loopback_host(host)
    except Exception:
        return False


def _is_loopback_host(host: str) -> bool:
    """Does every address this host resolves to sit on loopback?

    Every one, not any: a name that answers with both 127.0.0.1 and a routable address is
    not a local sim hub, it is a name that would let one resolution stand in for the other.
    """
    import ipaddress

    addrs = _resolved_ips(host)
    if not addrs:
        # An unresolvable name cannot be shown to be local, so it is not.
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    for addr in addrs:
        try:
            if not ipaddress.ip_address(addr).is_loopback:
                return False
        except ValueError:
            return False
    return True


def _health_url(base_url: str, *, is_hub: bool) -> str:
    """Return the health endpoint for the peer shape we already verified.

    AIMarket hubs expose the v2 protocol endpoint. Capability services in this
    ecosystem conventionally expose ``/api/health``. Treating every peer like a
    service made healthy subpath hubs (notably ``independentai.network/hub``)
    look idle and generated a permanent 404 in both Alien Monitor deployments.
    """
    path = "/ai-market/v2/health" if is_hub else "/api/health"
    return f"{base_url.rstrip('/')}{path}"


def _pin_http_target(url: str, *, allow_private: bool) -> tuple[str, dict[str, str]] | None:
    """For plain-HTTP, pin the connection to a freshly re-vetted IP (Host header
    preserved) to defeat DNS rebinding between the guard check and httpx's own
    resolution. Returns (request_url, extra_headers) or None if unsafe.

    HTTPS keeps the hostname (IP-pinning would break TLS SNI/cert validation);
    the pre-flight guard + the operator-trusted hub relay bound that residual.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # `is True` on purpose: the "loopback" allowance still gets resolved and pinned below,
    # because permitting loopback is not the same as declining to look.
    if allow_private is True or parsed.scheme != "http" or not host:
        return url, {}
    ips = _resolved_ips(host)
    if not ips:
        return None
    if any(_blocked_ip(a) for a in ips):
        # The "loopback" allowance is exactly the exception to this: resolved, pinned, and
        # permitted only because every address came back on loopback.
        if not (allow_private == "loopback" and _is_loopback_host(host)):
            return None
    chosen = ips[0]
    if str(chosen) == host:
        return url, {}
    netloc = f"[{chosen}]" if chosen.version == 6 else str(chosen)
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl(), {"Host": parsed.netloc}


# ── numeric coercion ────────────────────────────────────────────────


def _num(value: Any) -> float | int | None:
    """Return a finite, magnitude-bounded number, or None. Bools are not numbers.

    Ints are short-circuited before float() so huge JSON integers cannot raise
    OverflowError (which would otherwise drop the whole peer node)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        return max(-_METRIC_MAGNITUDE_CAP, min(value, _METRIC_MAGNITUDE_CAP))
    if math.isnan(value) or math.isinf(value):
        return None
    return round(max(-1e18, min(value, 1e18)), 6)



#: Cards show a peer's own description, and peers write long ones. A bare slice ends a card
#: mid-word - CHARON's read "...would actually have to sel", which looks like a broken feed
#: rather than a long description. Cut on a word boundary and SAY that it was cut.
#:
#: One function rather than a slice at each site: the polite version already existed on the
#: declared-name path in main.py while the discovery path that actually feeds the card kept
#: its hard `[:240]`, so the fix was live and invisible.
DESCRIPTION_LIMIT = 240


def clip_description(text, limit: int = DESCRIPTION_LIMIT) -> str:
    """`text`, trimmed to `limit` on a word boundary, with an ellipsis when it was cut."""
    out = str(text or "").strip()
    if len(out) <= limit:
        return out
    head = out[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    # A single word longer than the limit has no boundary to cut on; take the hard slice
    # rather than return an empty string.
    return (head or out[:limit]) + "\u2026"


def _scalar_metrics(health: dict[str, Any], *, limit: int = 16) -> dict[str, float | int]:
    """Pull finite top-level numeric fields (κ, order_parameter, tick, …)."""
    out: dict[str, float | int] = {}
    if not isinstance(health, dict):
        return out
    for key, val in health.items():
        if len(out) >= limit:
            break
        if not isinstance(key, str) or len(key) > 48:
            continue
        n = _num(val)
        if n is not None:
            out[key] = n
    return out


# ── id / position helpers ───────────────────────────────────────────


def _slugify(value: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in value.lower()).strip("-")
    return s[:48] or "peer"


def _node_id(well_known: dict[str, Any], base_url: str) -> str:
    eco = well_known.get("ecosystem") if isinstance(well_known.get("ecosystem"), dict) else {}
    candidate = ""
    if isinstance(eco, dict) and isinstance(eco.get("project"), str):
        candidate = eco["project"]
    if not candidate and isinstance(well_known.get("name"), str):
        candidate = well_known["name"]
    if not candidate:
        candidate = urlparse(base_url).hostname or base_url
    slug = _slugify(candidate)
    return f"fed-{slug}" if slug in _RESERVED_IDS else slug


def _position_for(node_id: str) -> dict[str, float]:
    h = sum(ord(ch) for ch in node_id) or 1
    ang = (h % 360) * math.pi / 180.0
    radius = 3.2
    ax, ay, az = _FED_ANCHOR
    return {
        "x": round(ax + radius * math.cos(ang), 3),
        "y": round(ay + ((h % 5) - 2) * 0.55, 3),
        "z": round(az + radius * math.sin(ang), 3),
    }


# ── HTTP ────────────────────────────────────────────────────────────


async def _get_json(
    client: httpx.AsyncClient, url: str, *, allow_private: bool, timeout: float,
) -> Any | None:
    """Fetch JSON with SSRF guard, IP-pinning, hard deadline, size cap, JSON-only."""
    if not url_is_safe(url, allow_private=allow_private):
        return None
    pinned = _pin_http_target(url, allow_private=allow_private)
    if pinned is None:
        return None
    req_url, extra_headers = pinned
    headers = {"User-Agent": USER_AGENT, **extra_headers}

    async def _do() -> Any | None:
        async with client.stream("GET", req_url, follow_redirects=False, headers=headers) as resp:
            if resp.status_code != 200:
                return None
            # JSON-only — default-closed: a peer that omits Content-Type is rejected.
            ctype = resp.headers.get("content-type", "").lower()
            if "json" not in ctype:
                return None
            clen = resp.headers.get("content-length")
            if clen and clen.isdigit() and int(clen) > _MAX_RESPONSE_BYTES:
                return None
            body = b""
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                body += chunk
                if len(body) > _MAX_RESPONSE_BYTES:
                    return None
        import json
        return json.loads(body)

    try:
        # Hard wall-clock deadline on top of httpx's per-read timeout — a slowloris
        # drip cannot exceed this even if every single read stays under read-timeout.
        return await asyncio.wait_for(_do(), timeout=max(0.5, timeout))
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 - degrade, never raise
        logger.debug("discovery fetch failed for %s: %s", url[:80], exc)
        return None


def _matches(categories: Any, wanted: set[str]) -> bool:
    if not isinstance(categories, list):
        return False
    return any(isinstance(c, str) and c.strip().lower() in wanted for c in categories)


# ── config ──────────────────────────────────────────────────────────


#: Identities that have actually TRANSACTED with this hub — the consumer side of the
#: economy. Fed from the hub live-event feed once per tick (`note_economy_participants`),
#: because "part of the system" is a two-sided question and a catalogue only answers one
#: side of it: a node that buys from us every hour and lists nothing is a participant, and
#: dropping it would hide our own customers.
_ECONOMY_PARTICIPANTS: set[str] = set()
_PSEUDONYMOUS_BUYER_PREFIXES = ("sandbox:", "channel:", "account:", "mcp:")


def note_economy_participants(identities: Iterable[str]) -> None:
    """Record who has bought from us. Normalised the same way peer URLs are.

    Deliberately additive: an identity that transacted an hour ago is still a participant
    when the event has scrolled out of the feed window. This set is a memory of the
    economy, not a snapshot of the last twenty events.
    """
    for raw in identities or ():
        text = str(raw or "").strip()
        if not text or text in ("anonymous", "local", "x402"):
            continue
        # A pseudonymous buyer label (the hub hashes these) can never name a node, and one
        # arrives per trial visitor — kept, they only grow this set without bound.
        if text.startswith(_PSEUDONYMOUS_BUYER_PREFIXES):
            continue
        normalized = _norm_url(text) if "://" in text else text.lower()
        if normalized:
            _ECONOMY_PARTICIPANTS.add(normalized)


def _is_economy_participant(node: dict[str, Any]) -> bool:
    """Has this node ever been on either side of a transaction with us?"""
    if not _ECONOMY_PARTICIPANTS:
        return False
    candidates = {str(node.get("id") or "").lower()}
    for key in ("url", "url_internal", "hub_url"):
        value = str(node.get(key) or "").strip()
        if value:
            candidates.add(_norm_url(value))
    return bool(candidates & _ECONOMY_PARTICIPANTS)


class DiscoveryConfig:
    """Resolved at call time so env changes / tests take effect immediately."""

    def __init__(self, *, allow_private: bool = False):
        self.enabled = os.getenv("ALIEN_DISCOVERY_ENABLED", "1").strip().lower() not in ("0", "false", "no")
        self.allow_private = allow_private or os.getenv("ALIEN_DISCOVERY_ALLOW_PRIVATE", "0").strip().lower() in ("1", "true", "yes")
        #: What a PEER-supplied URL is allowed to reach. Never the unconditional bypass:
        #: the trusted hub's own fetches name `allow_private=True` themselves in
        #: `discover_async`, so this flag only ever widened the peer path. In UNI mode a
        #: peer may resolve to loopback (hubs the sim spawned) and nothing else.
        self.peer_allow_private: bool | str = "loopback" if self.allow_private else False
        self.timeout = float(os.getenv("ALIEN_DISCOVERY_TIMEOUT_S", "4"))
        self.max_peers = max(1, int(os.getenv("ALIEN_DISCOVERY_MAX_PEERS", "25")))
        # Pending observations do not trigger outbound requests, so the monitor can safely
        # render the full gossip window rather than truncating new Hub visibility to the
        # approved-peer fetch budget.
        self.max_observed = max(1, int(os.getenv("ALIEN_DISCOVERY_MAX_OBSERVED", "2000")))
        self.concurrency = max(1, int(os.getenv("ALIEN_DISCOVERY_CONCURRENCY", "8")))
        self.refresh_s = max(2.0, float(os.getenv("ALIEN_DISCOVERY_REFRESH_S", "20")))
        # How many of a peer hub's own peers to draw around it. Bounded because the graph is
        # a map, not a crawler.
        try:
            self.max_hub_children = max(0, int(os.getenv("ALIEN_DISCOVERY_HUB_CHILDREN", "12")))
        except (TypeError, ValueError):
            self.max_hub_children = 12
        cats = os.getenv("ALIEN_DISCOVERY_CATEGORIES", "").strip()
        self.categories = (
            {c.strip().lower() for c in cats.split(",") if c.strip()} if cats else set(_DEFAULT_CATEGORIES)
        )

    @property
    def peer_deadline(self) -> float:
        """Wall-clock budget for one peer (well-known + health, sequential)."""
        return self.timeout * 2 + 1.0


# ── core ────────────────────────────────────────────────────────────


def _build_pending_node(peer: dict[str, Any], cfg: "DiscoveryConfig") -> dict[str, Any] | None:
    """A hub that knocked but was never approved, rendered from metadata alone.

    Deliberately makes NO outbound request — not to the peer's well-known, not to its
    health endpoint. An unapproved stranger should not be able to get this monitor to
    connect to it just by announcing itself to the hub; that would turn the navigator
    into a callback the stranger controls. Everything shown here is what our own hub
    already told us.

    These appear only on the LIVE map, which is the real universe. UNI builds its
    world from `tick_universe` and never calls discovery, so the simulation stays
    sealed off from strangers.
    """
    base_url = (peer.get("url") or "").rstrip("/")
    if not base_url or not url_is_safe(base_url, allow_private=cfg.peer_allow_private):
        return None
    node_id = f"pending:{base_url}"
    label = str(peer.get("name") or base_url)[:80]
    # The frontend dereferences node.position.{x,y,z} unconditionally — a node without one
    # does not render badly, it throws and takes the whole graph with it. Pushed onto a wider,
    # lower ring than admitted peers so a stranger is spatially separate, not just differently
    # coloured.
    # Laid out by the aggregation step, which is the only place that knows how many
    # strangers there are and can therefore keep them off each other.
    position = _position_for(node_id)
    metrics: dict[str, float | int] = {}
    previewed = _num(peer.get("preview_capabilities"))
    if previewed is not None:
        metrics["preview_capabilities"] = previewed
    return {
        "id": node_id,
        "label": label,
        "group": "pending_hub",
        "status": "pending",
        "color": node_palette.color_for("pending_hub"),
        # A stranger knocked on OUR door — that is one hop, same as an approved peer.
        # It sits outside the approved rings because it is unapproved, not because it
        # is further away.
        "hop": 1,
        "position": position,
        "description": "Unapproved hub — visible, indexed by nothing.",
        "url": base_url,
        "trusted": False,
        "categories": [str(c) for c in (peer.get("categories") or []) if isinstance(c, str)][:8],
        "metrics": metrics,
        "detail": {
            "first_seen": str(peer.get("first_seen") or ""),
            "discoverer": str(peer.get("discoverer") or ""),
            "note": (
                "Unapproved hub. A sandbox assay runs automatically; until it "
                "passes, nothing it offers is indexed, searchable or routable."
            ),
        },
    }


import node_palette


def _norm_url(url: Any) -> str:
    """One spelling for one host, so two peer lists agree about what is the same node."""
    text = str(url or "").strip().rstrip("/").lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text


def _estate(url: Any) -> str:
    """The registrable-ish domain of a URL: the last two labels of its host.

    Used for one question only — is this peer part of OUR estate or somebody else's.
    """
    host = _norm_url(url).split("/")[0].split(":")[0]
    labels = [l for l in host.split(".") if l]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host



def _is_peer_hub(well_known: dict[str, Any]) -> bool:
    """Does this peer run a hub, rather than being a single capability service?

    Read from what the peer publishes about itself — `hub_version`, or a v2 entry in
    `protocol_versions` — never inferred from its URL or its categories. A hub that
    advertises no oracle-ish category used to be dropped by the relevance filter, so the one
    kind of peer whose whole purpose is to have peers of its own was the one kind the map
    could not show.
    """
    if not isinstance(well_known, dict):
        return False
    if str(well_known.get("hub_version") or "").strip():
        return True
    versions = well_known.get("protocol_versions")
    if isinstance(versions, (list, tuple)):
        return any(str(v).strip().lower() in ("v2", "2", "2.0") for v in versions)
    return False


def _attach_declaration(
    node_id: str, declaration: Any, *node_lists: list[dict[str, Any]],
) -> bool:
    """Give `node_id` an on-chain declaration it does not already have.

    Used when a second-hop copy folds into a node the map already draws (or is about to):
    the copy is discarded, so anything it carried has to be moved across first. Never
    OVERWRITES — a node's own declaration, read from its own well-known, outranks a
    stranger's re-export of it.
    """
    if not isinstance(declaration, dict) or not declaration.get("entries"):
        return False
    for nodes in node_lists:
        for node in nodes:
            if node.get("id") == node_id:
                if not node.get("contracts"):
                    node["contracts"] = declaration
                    return True
                return False
    return False


def deserves_sphere(node: dict[str, Any], keep_anyway: frozenset[str] = frozenset()) -> bool:
    """Does this node earn a sphere on the map? The rule, in one place.

    Three tiers, and the line falls at the second hop:

      hop 0 — our own hub and our own providers. ALWAYS drawn: it is what this deployment
              runs, and we show what we run.
      hop 1 — a hub we federate with directly, or one knocking to be admitted. ALWAYS
              drawn. A hub is a routing relationship rather than a shop window; zero
              capabilities can be perfectly correct (an aggregator whose whole catalogue is
              re-exports is filtered to zero by the re-export rule); and a hub still
              waiting for admission has an empty catalogue BECAUSE it is waiting. "Who is
              out there" is the question this map exists to answer.
      hop 2 — inherited: somebody else's provider or peer, reached only through them. Drawn
              only if it is PART OF THIS ECONOMY, which is a three-way test — any ONE of:

                supplier — it offers at least one capability. The test is the CATALOGUE,
                           never the revenue: a node giving something away for free is as
                           much a participant as one charging for it.
                consumer — it has actually transacted with us (it appears as a
                           `consumer_hub` in our own invocation feed).
                on chain — it declared an escrow or settlement wallet AND we confirmed that
                           address against the chain ourselves (foreign_contracts). The
                           only one of the three that does not depend on our own books: a
                           hub nobody here has traded with, whose escrow holds code and has
                           transactions, is demonstrably running an economy — and its
                           sphere opens onto those transactions, so the reader can check
                           the claim too.

              None of the three means there is nothing to buy, no federation with it, no
              telemetry of our own, no money it can be seen to move, and no way to reach it
              except through a stranger — a name copied out of a stranger's document.
              `Competing Lab Hub` sat on `monitor.attestedmemory.net` exactly like that.

    This is the MAP's decision, not the hub's. A hub must declare everything it knows,
    faithfully; what deserves a sphere is the viewer's question.

    Lives here as a function, not inline, because the test suite has to be able to call the
    REAL rule. A test that re-implements it passes while production drifts away from it.
    """
    if int(node.get("hop") or 0) < 2:
        return True
    if node.get("id") in keep_anyway:
        return True
    if int((node.get("metrics") or {}).get("capabilities") or 0) > 0:
        return True
    if _is_economy_participant(node):
        return True
    return bool((node.get("contracts") or {}).get("verified"))


def _peer_hub_children(
    well_known: dict[str, Any], parent_id: str, cfg: "DiscoveryConfig",
    *, onchain: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A peer hub's own peers, as nodes hanging off it.

    Costs no extra request: a hub's `.well-known/ai-market.json` already carries its `peers`
    array (url, name, capabilities_count, trust_score), which is exactly what a second hop
    needs. One hop only, and bounded — the graph is a map, not a crawler, and a cycle in the
    federation must not become a cycle here.
    """
    raw = well_known.get("peers")
    raw = raw if isinstance(raw, list) else []
    ecosystem = well_known.get("ecosystem")
    declared_nodes = ecosystem.get("nodes") if isinstance(ecosystem, dict) else []
    declared_nodes = declared_nodes if isinstance(declared_nodes, list) else []
    # Federation peers and owned providers are different relationships, but both belong
    # spatially to this hub's star system.  The provider declaration is display metadata
    # from the already signed well-known; it never creates routing trust.
    # Owned providers are the Hub's actual local star system and must consume the
    # bounded child budget first. Federation peers are usually already first-class
    # Hub planets elsewhere in the graph; putting them first let twelve re-exported
    # peer addresses exhaust the budget and hid KOVA/Echo while only AEGIS survived.
    entries = [(entry, "provider") for entry in declared_nodes]
    entries.extend((entry, "peer") for entry in raw)
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for entry, relationship in entries:
        if len(nodes) >= cfg.max_hub_children:
            break
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").rstrip("/")
        normalized = _norm_url(url)
        if not url or normalized in seen_urls or not _displayable_url(url):
            # A child is only drawn, never fetched, so url_is_safe's DNS check is not run —
            # but its url becomes a clickable link in the node card, and it comes from a
            # stranger's well-known: javascript:/data: and the like never get that far.
            continue
        seen_urls.add(normalized)
        child_id = (
            f"provider:{parent_id}:{str(entry.get('id') or normalized)}"
            if relationship == "provider" else f"fedchild:{url}"
        )
        # No position yet: it depends on which slot the PARENT gets and on how many siblings
        # there are, and only the aggregation step knows both. Positioning here from the
        # child's own hash is what put every hub's peers in the same pile near the origin
        # instead of around their hub.
        metrics: dict[str, float | int] = {}
        caps = _num(entry.get("capabilities_count"))
        if caps is not None:
            metrics["capabilities"] = caps
        trust = _num(entry.get("trust_score"))
        if trust is not None:
            metrics["trust_score"] = trust
        # What this second-hop node says it has ON CHAIN, re-exported by its hub, checked
        # against the chain we read (never against its word). The one claim about a stranger
        # that a third party can falsify — see foreign_contracts.
        child_contracts = foreign_contracts.evidence_for(
            foreign_contracts.sanitize(entry.get("contracts")), onchain or {},
        )
        if child_contracts:
            metrics["onchain_addresses"] = len(child_contracts.get("entries") or [])
        nodes.append({
            "id": child_id,
            "label": str(entry.get("name") or url)[:80],
            "group": "peer_hub_provider" if relationship == "provider" else "peer_hub_node",
            "icon": "provider" if relationship == "provider" else "network",
            "role": relationship,
            "url": url,
            "description": (
                "Owned provider in this hub's signed ecosystem declaration."
                if relationship == "provider"
                else "Node of a federated hub — reached through that hub, not by us."
            ),
            "metrics": metrics,
            "status": "idle",
            "categories": [str(c) for c in (entry.get("categories") or []) if isinstance(c, str)][:8],
            "discovered": True,
            **({"contracts": child_contracts} if child_contracts else {}),
            "parent_id": parent_id,
            # Walked by sibling index from a per-hub start, so a hub's children can never
            # bunch into three shades of the same colour — see node_palette._fraction.
            "color": node_palette.color_for(
                "peer_hub_provider" if relationship == "provider" else "peer_hub_node",
                [str(c) for c in (entry.get("categories") or []) if isinstance(c, str)],
                node_id=child_id,
                sibling=len(nodes),
                sibling_seed=parent_id,
            ),
            # Hop 1 is a hub we federate with directly. Its own peers and providers are
            # hop 2 — reached only THROUGH it — and are drawn as planets in its
            # constellation, never as suns of their own. That is what bounds the graph:
            # the federation is cyclic, so "a peer's peers" has no natural end.
            "hop": 0 if parent_id == "hub" else 2,
        })
        links.append({
            "source": parent_id, "target": child_id,
            "label": "its provider" if relationship == "provider" else "its peer",
            "kind": "ecosystem" if relationship == "provider" else "federation",
        })

    # Everything the hub declared, unfiltered. WHO GETS A SPHERE is decided by
    # `deserves_sphere`, applied by the aggregation step (`discover_async`) — and it has to
    # be, because the answer needs knowledge only that step has.
    #
    # Filtering here dropped a child before anyone could see that it resolves to a node the
    # map ALREADY HAS. A stranger hub listing our own hub, ATLAS or MOMUS is not asking for
    # a new sphere: that child becomes an EDGE to the existing node — the edge that says
    # "they know us" and that stops our own hub being drawn twice, once as the centre and
    # once as somebody's moon. Zero capabilities is irrelevant to a relationship we can see
    # from both ends, so the rule must not be consulted about it at all.
    return nodes, links


def _explicitly_kept_nodes() -> frozenset[str]:
    """Second-hop nodes to draw even though they offer nothing.

    A rule needs a deliberate override, or the first legitimate exception becomes a reason
    to delete the rule. Comma-separated node ids, e.g.
    ``ALIEN_KEEP_SILENT_NODES=fedchild:https://example.dev``.
    """
    raw = (os.environ.get("ALIEN_KEEP_SILENT_NODES") or "").strip()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


async def _build_peer_node(
    client: httpx.AsyncClient, peer: dict[str, Any], cfg: DiscoveryConfig,
    *, hub_own_url: str = "", trust_declared_identity: bool = False,
) -> dict[str, Any] | None:
    """Resolve one peer into a graph node (or None if not a match / unsafe).

    ``trust_declared_identity`` says the peer dict came from OUR hub's own
    ``/ai-market/v2/federation/peers`` — the only source whose ``canonical_id`` may be
    believed, because that field is the operator's pin resolved by the hub we are pointed
    at. A peer list republished by ANOTHER hub is a stranger's claim about our naming and
    is never trusted for identity, which is why this is an argument and not a lookup.
    """
    base_url = (peer.get("url") or "").rstrip("/")
    if not base_url or not url_is_safe(base_url, allow_private=cfg.peer_allow_private):
        return None
    base = hub_own_url

    categories = peer.get("categories")
    well_known: dict[str, Any] = {}

    # If the hub didn't carry categories (older hub), fetch the peer's well-known.
    if not isinstance(categories, list) or not categories:
        wk_url = peer.get("well_known_url") or f"{base_url}/.well-known/ai-market.json"
        wk = await _get_json(client, wk_url, allow_private=cfg.peer_allow_private, timeout=cfg.timeout)
        if isinstance(wk, dict):
            well_known = wk
            categories = wk.get("categories")

    # A peer HUB is kept whatever its categories say. The relevance filter is about
    # capabilities — oracle, simulation, beacon — and a hub does not advertise one; it
    # advertises other people's. So the single kind of peer whose whole point is to have
    # peers of its own was the kind the map silently dropped.
    if not well_known:
        wk_url = peer.get("well_known_url") or f"{base_url}/.well-known/ai-market.json"
        wk = await _get_json(client, wk_url, allow_private=cfg.peer_allow_private, timeout=cfg.timeout)
        if isinstance(wk, dict):
            well_known = wk
    matched = _matches(categories, cfg.categories)
    is_hub = _is_peer_hub(well_known)
    own_peers = well_known.get("peers")
    has_own_peers = isinstance(own_peers, list) and len(own_peers) > 0
    if not (matched or is_hub):
        return None
    # `hub_version` alone over-matches: ATLAS reports 0.1.0 and GAIA reports one too, because
    # every satellite is built on the hub's manifest shape — so that field on its own would
    # turn the sensor gateway into a "hub" and throw away the classification that actually
    # tells an operator what the node does. Render as a hub only when there is something
    # hub-shaped to show: peers of its own, or a hub that the capability filter would have
    # dropped anyway.
    # ONLY when it has peers of its own. "hub_version and no matching category" looked like a
    # reasonable second signal and was not: ATLAS, GAIA, BASANOS and MOMUS all report a
    # hub_version and none of them match the oracle filter, so they were promoted to hubs and
    # lost the classification that says what they actually do. A hub with no peers has no
    # ecosystem to draw, which is the only reason this ring exists.
    #
    # OUR OWN satellites are already first-class nodes on this map — ATLAS, GAIA, MOMUS and
    # BASANOS each have their own seeded entity and layer — and every one of them reports a
    # hub_version, because they are built on the hub's manifest shape. Promoting those to the
    # hub ring throws away what they are. But a stranger's hub is on nobody's map: if it is
    # not drawn as a hub it is not drawn at all, and a NEWLY deployed hub has zero peers,
    # which is the whole case this feature exists for. So the rule splits by estate:
    #   * somebody else's domain + hub_version  -> a hub, peers or no peers;
    #   * our own domain + hub_version          -> a hub only if it federates with someone,
    #                                              otherwise it stays the satellite it is.
    ours = _estate(base) or _estate(hub_own_url)
    foreign = bool(ours) and _estate(base_url) != ours
    render_as_hub = is_hub and (foreign or has_own_peers)

    node_id = _node_id(well_known, base_url)
    label = str(well_known.get("name") or peer.get("name") or node_id)[:80]
    # `categories` reaches here as None for a peer that publishes none — which only became
    # possible once a hub could pass the gate without matching the filter. Iterating it threw
    # TypeError straight into the per-peer `except Exception` that exists so one bad peer
    # cannot break the graph, so the failure was not an error anywhere: the peer simply was
    # not on the map. The three real hubs in the live federation vanished exactly like this.
    if not isinstance(categories, list):
        categories = []
    cat_list = [str(c) for c in categories if isinstance(c, str)][:8]

    metrics: dict[str, float | int] = {}
    caps = _num(peer.get("capabilities_count"))
    if caps is not None:
        metrics["capabilities"] = caps
    trust = _num(peer.get("trust_score"))
    if trust is not None:
        metrics["trust_score"] = trust

    # Live health → κ / order_parameter / tick / viewers …
    # A Hub has a protocol health route; regular capability nodes keep the
    # ecosystem service convention. The distinction is already established
    # above from the peer's own well-known document.
    status = "idle"
    health = await _get_json(
        client, _health_url(base_url, is_hub=render_as_hub),
        allow_private=cfg.peer_allow_private, timeout=cfg.timeout,
    )
    if isinstance(health, dict):
        status = "active"
        for k, v in _scalar_metrics(health).items():
            metrics.setdefault(k, v)

    description = clip_description(
        well_known.get("description")
        or f"Federation peer — {', '.join(cat_list) or 'discovered node'}"
    )

    from canonical_peers import canonical_node_id_for_peer, SEEDED_HUB_IDS

    probe = {
        "id": node_id,
        "label": label,
        "url": base_url,
        "description": description,
    }
    if trust_declared_identity:
        # Resolved by our own hub from the operator's pinned seed list, so it beats every
        # host rule below — that is the whole point: the tables exist because nobody was
        # answering this question, and now somebody is.
        declared = str(peer.get("canonical_id") or "").strip()
        if declared:
            probe["canonical_id"] = declared
    # First-party satellites (MOMUS, GAIA, …) and the 17-oracle family already
    # have canonical map nodes. Emitting them here paints a second violet oracle.
    # Seeded hub suns are different: we still emit so their own peers become
    # orbiting moons, but under the canonical id so merge does not mint a twin.
    canon = canonical_node_id_for_peer(probe)
    if canon in ("hub", "factory"):
        return None
    if canon and canon not in SEEDED_HUB_IDS:
        return None
    if canon in SEEDED_HUB_IDS:
        node_id = canon

    # The answer travels WITH the node. The browser keeps its own copy of the host tables
    # (frontend/src/lib/ecoGraphSanitize.ts) to drop clones client-side, and a transcribed
    # copy of a table is a copy that drifts — it already had, missing the apex rule the
    # backend grew. Sending what was resolved here lets that copy wither into a fallback.
    resolved_identity = canon or ""

    if render_as_hub:
        for key in ("capabilities_count", "federated_capabilities_count", "products_count"):
            value = _num(well_known.get(key))
            if value is not None:
                metrics.setdefault(key, value)
        peers_seen = well_known.get("peers")
        if isinstance(peers_seen, list):
            metrics.setdefault("peers", len(peers_seen))
        # Verified HERE, in the same pass that read the declaration, rather than from a set
        # filled by a previous tick: the sphere rule below consumes the result, and a
        # decision that lags its evidence by one tick makes a legitimate node appear,
        # vanish and reappear while an operator watches.
        onchain = await foreign_contracts.verify(
            client, foreign_contracts.declarations_in(well_known),
        )
        own_declaration = foreign_contracts.evidence_for(
            foreign_contracts.sanitize(well_known.get("contracts")), onchain,
        )
        children, child_links = _peer_hub_children(
            well_known, node_id, cfg, onchain=onchain,
        )
        return {
            "id": node_id,
            "canonical_id": resolved_identity,
            "label": label,
            "group": "peer_hub",
            "icon": "hub",
            "role": "hub",
            "url": base_url,
            "description": clip_description(
                well_known.get("description")
                or f"Federated hub — {int(metrics.get('peers', 0))} peers of its own"
            ),
            "metrics": metrics,
            "status": status,
            "position": _position_for(node_id),
            "categories": cat_list,
            "discovered": True,
            "hub": True,
            # With its categories: a hub that says what it serves is coloured by that, and
            # only a hub that says nothing stays hub-cyan. See node_palette.
            "color": node_palette.color_for("peer_hub", cat_list, node_id=node_id),
            #: A hub OUR hub federates with: one hop out, drawn as a sun with its own
            #: constellation. Anything reached only through it is hop 2.
            "hop": 1,
            **({"contracts": own_declaration} if own_declaration else {}),
            "children": children,
            "child_links": child_links,
        }

    return {
        "id": node_id,
        "canonical_id": resolved_identity,
        "label": label,
        "group": "oracle",
        "icon": "oracle",
        "url": base_url,
        "description": description,
        "metrics": metrics,
        "status": status,
        "position": _position_for(node_id),
        "categories": cat_list,
        "discovered": True,
        "hop": 1,
        # What it does, not whose it is — see node_palette. Stamped here so the LIVE and UNI
        # paths cannot disagree about the colour of the same node.
        "color": node_palette.color_for("oracle", cat_list, node_id=node_id),
    }


async def discover_async(hub_url: str, *, allow_private: bool = False) -> dict[str, Any]:
    """Query the hub's federation peers and return discovered nodes + links.

    hub_url is the operator-configured (trusted) hub address — it is NOT
    SSRF-checked. Every peer/well-known/health URL the hub hands back IS checked.
    """
    cfg = DiscoveryConfig(allow_private=allow_private)
    result: dict[str, Any] = {
        "nodes": [], "links": [], "events": [], "peer_count": 0,
        "pending_count": 0, "pending_observations": [], "errors": [],
    }
    pending_nodes: list[dict[str, Any]] = []
    own_ecosystem_nodes: list[dict[str, Any]] = []
    own_declared_url = ""
    own_identity = ""
    if not cfg.enabled or not hub_url:
        return result

    base = hub_url.rstrip("/")
    timeout = httpx.Timeout(cfg.timeout, connect=cfg.timeout)
    limits = httpx.Limits(max_connections=cfg.concurrency, max_keepalive_connections=cfg.concurrency)
    try:
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            payload = await _get_json(
                client, f"{base}/ai-market/v2/federation/peers",
                allow_private=True,  # the hub itself is trusted/operator-configured
                timeout=cfg.timeout,
            )
            if not isinstance(payload, dict):
                result["errors"].append("federation/peers: no JSON")
                return result
            # Our own public name, asked of the hub itself while the session is open — the
            # aggregation below runs after this client is closed.
            own_manifest = await _get_json(
                client, f"{base}/.well-known/ai-market.json",
                allow_private=True, timeout=cfg.timeout,
            )
            if isinstance(own_manifest, dict):
                own_declared_url = _norm_url(
                    own_manifest.get("hub_url") or own_manifest.get("base_url") or ""
                )
                # Draw only the deployment's declared provider ecosystem here.  Its
                # federation peers are already first-hop nodes and must not be copied as
                # children of the centre.
                ecosystem = own_manifest.get("ecosystem")
                if isinstance(ecosystem, dict) and isinstance(ecosystem.get("nodes"), list):
                    own_only = {"ecosystem": ecosystem, "peers": []}
                    own_ecosystem_nodes, _ = _peer_hub_children(own_only, "hub", cfg)

            # Which estate is OURS. The monitor dials the hub over loopback, so the address
            # we called it on says nothing about who we are: `_estate("127.0.0.1:9083")` is
            # "0.1", every real peer differs from it, and the estate rule then declared every
            # satellite a foreign hub. The hub's own declared name is the identity that means
            # something.
            own_identity = own_declared_url or _norm_url(
                os.getenv("ALIEN_PUBLIC_HUB_URL", "") or os.getenv("AIMARKET_HUB_URL", "")
            ) or _norm_url(base)

            peers = payload.get("peers")
            if not isinstance(peers, list):
                return result
            peers = peers[: cfg.max_peers]
            result["peer_count"] = len(peers)

            sem = asyncio.Semaphore(cfg.concurrency)

            async def _one(p: dict[str, Any]) -> dict[str, Any] | None:
                if not isinstance(p, dict):
                    return None
                async with sem:
                    try:
                        # Per-peer wall-clock budget: a slow peer is dropped, the
                        # rest still render (and the tick is never held hostage).
                        return await asyncio.wait_for(
                            _build_peer_node(
                                client, p, cfg, hub_own_url=own_identity,
                                # These came from the hub this monitor is pointed at.
                                trust_declared_identity=True,
                            ),
                            timeout=cfg.peer_deadline,
                        )
                    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
                        logger.debug("peer node build failed: %s", exc)
                        return None

            nodes = [n for n in await asyncio.gather(*(_one(p) for p in peers)) if n]

            # Strangers that announced themselves or crawled us. Rendered so the map
            # shows the real universe — including the parts of it we have not vouched
            # for — but visibly separate from the federation we did approve.
            raw_pending = payload.get("pending")
            if isinstance(raw_pending, list):
                for entry in raw_pending[: cfg.max_observed]:
                    if not isinstance(entry, dict):
                        continue
                    pending_node = _build_pending_node(entry, cfg)
                    if pending_node:
                        pending_nodes.append(pending_node)
            result["pending_count"] = len(pending_nodes)
    except Exception as exc:
        logger.warning("federation discovery failed: %s", exc)
        result["errors"].append(str(exc))
        return result

    # Dedupe by id; link each discovered node to the federation hub-node.
    from canonical_peers import FIRST_PARTY_URLS, SEEDED_HUB_IDS
    from ecosystem_layout import (
        discovered_peer_position,
        node_position as layout_node_position,
        peer_hub_child_position,
        peer_hub_cluster_radius,
        peer_hub_position,
        peer_hub_ring_radius,
    )

    seen: set[str] = set()
    # Hubs get laid out as CLUSTERS, and a cluster's slot has to be decided where every hub is
    # visible at once — a per-peer decision cannot keep two hubs off each other. Slots are
    # assigned over the sorted id list so the same peer set always produces the same map;
    # a new hub joining can shift the slot of one that sorts after it, which is the price of
    # not having a persistent slot registry, and it is paid once per new peer rather than
    # every tick.
    # Everything the map already has, by URL. Our own hub is in here as the `hub` node: these
    # peers federate WITH us, so our address is in their peer lists, and without this our hub
    # renders twice — once as the centre and once as a planet orbiting a stranger.
    # Both spellings of our own hub. The monitor talks to it over loopback
    # (HUB_URL=http://127.0.0.1:9083) while every peer lists it by its public name, so
    # matching on the address we dialled is not enough — and the symptom is our own hub
    # rendered as a moon orbiting a stranger, which is what happened on the live map.
    known_by_url: dict[str, str] = {_norm_url(base): "hub"}
    for env_name in ("ALIEN_PUBLIC_HUB_URL", "AIMARKET_HUB_URL", "ALIEN_HUB_PUBLIC_URL"):
        public = _norm_url(os.getenv(env_name, ""))
        if public:
            known_by_url[public] = "hub"
    # And whatever the hub calls itself, read from the hub itself rather than configured
    # twice: an operator who renames the deployment should not have to remember this file.
    if own_declared_url:
        known_by_url[own_declared_url] = "hub"
    from competing_lab_layers import competing_hub_api_url, competing_hub_url, signal_hunt_url

    from deployment_profile import owns_builtin_shelf

    shelf_is_ours = owns_builtin_shelf()
    # Only a Monitor that DRAWS the AICOM shelf may fold a peer onto it. Elsewhere these
    # are twelve URLs belonging to a stranger, and folding turns their hub into an edge
    # pointing at a node the graph does not contain.
    if shelf_is_ours:
        for public, canonical_id in FIRST_PARTY_URLS:
            known_by_url.setdefault(_norm_url(public), canonical_id)
        known_by_url.setdefault(_norm_url(signal_hunt_url()), "signal_hunt_hub")
        known_by_url.setdefault(_norm_url(competing_hub_url()), "competing_hub")
        known_by_url.setdefault(_norm_url(competing_hub_api_url()), "competing_hub")
    # Our own hub is always known — it is the centre of this map, whoever runs it.
    seeded_ids = SEEDED_HUB_IDS if shelf_is_ours else frozenset({"hub"})
    for node in nodes:
        url = _norm_url(node.get("url"))
        if url:
            known_by_url.setdefault(url, node["id"])

    # First-hop peers are slotted for the same reason hubs are: a hash spreads without
    # separating. Sorted so the same peer set always yields the same map.
    peer_slot = {
        node["id"]: index
        for index, node in enumerate(sorted(
            (n for n in nodes if n.get("group") != "peer_hub" and n["id"] not in seeded_ids),
            key=lambda n: n["id"],
        ))
    }
    # Seeded suns already sit in the competing galaxy. Putting them on this ring
    # minted a second Signal Hunt / Competing Lab sphere next to the real one.
    hub_nodes = sorted(
        (n for n in nodes if n.get("group") == "peer_hub" and n["id"] not in seeded_ids),
        key=lambda n: n["id"],
    )
    hub_slot = {node["id"]: index for index, node in enumerate(hub_nodes)}
    # The universe expands to fit what is in it. Cluster widths are known before anything is
    # placed — each hub arrived carrying its own peers — so the ring is sized once, from the
    # widest ecosystem and the number of hubs, and every hub moves outward together. A fixed
    # radius works right up until one hub grows, and then two ecosystems occupy the same
    # space with no warning.
    widest_cluster = max(
        (peer_hub_cluster_radius(len(n.get("children") or [])) for n in hub_nodes),
        default=0.0,
    )
    hub_ring = peer_hub_ring_radius(len(hub_nodes), widest_cluster)
    for node in nodes:
        if node["id"] in seen:
            continue
        seen.add(node["id"])
        # A peer hub arrives carrying its own peers. They are unpacked here rather than in the
        # builder so the dedupe below is the ONE place that decides what enters the graph —
        # two hubs that peer with each other name the same nodes, and a duplicate id renders
        # as a node fighting itself for a position.
        children = node.pop("children", None) or []
        child_links = node.pop("child_links", None) or []
        seeded_sun = node["id"] in seeded_ids
        if seeded_sun:
            try:
                node["position"] = layout_node_position(node["id"])
            except Exception:
                pass
        elif node["id"] in hub_slot:
            # No fixed radius: hubs fill a BALL, and which shell a slot lands on is the
            # layout's decision. Pinning them all to one radius is the ring that could not
            # hold more than nine.
            node["position"] = peer_hub_position(
                hub_slot[node["id"]], len(hub_nodes), max_cluster_radius=widest_cluster,
            )
        elif node["id"] in peer_slot:
            node["position"] = discovered_peer_position(peer_slot[node["id"]], _FED_ANCHOR)
        result["nodes"].append(node)
        if not seeded_sun:
            result["links"].append({
                "source": "federation", "target": node["id"], "label": "Federation peer",
            })
        # A hub's peer list overlaps ours: the same ATLAS, the same MOMUS, and — since these
        # hubs peer with US — our own hub. Drawing those again as "their" planets puts two
        # objects on the map for one thing and makes our hub a moon of somebody else's. So a
        # peer we already know becomes an EDGE from their hub to the node that already
        # exists; only genuinely new ones become planets.
        kept: list[dict[str, Any]] = []
        silent: list[str] = []
        keep_anyway = _explicitly_kept_nodes()
        # Hubs still KNOCKING are drawn further down this same pass, so they are not in
        # `known_by_url` yet — and a second-hop copy of one must fold into the sphere that
        # is about to exist, exactly like a copy of a peer we already draw. Measured on
        # `monitor.attestedmemory.net`: `modelmarket.dev` is a pending hub there AND a peer
        # of Signal Hunt, so its second-hop copy carried no capability count, failed the
        # participation test, and was dropped — losing the edge that shows the two hubs
        # know each other, about a node the map was drawing anyway.
        pending_by_url = {
            url: pending["id"]
            for pending in pending_nodes
            if (url := _norm_url(pending.get("url"))) and url not in known_by_url
        }
        for child in children:
            if child["id"] in seen:
                continue
            child_url = _norm_url(child.get("url"))
            existing = known_by_url.get(child_url) or pending_by_url.get(child_url)
            if existing:
                result["links"].append({
                    "source": node["id"], "target": existing,
                    "label": "shared peer", "kind": "shared",
                })
                # …and the on-chain declaration goes with it. This copy is where the
                # declaration ARRIVED — a hub re-exports what its peers declared, so a
                # second-hop sighting is often the only route by which an address reaches
                # this map at all. Folding the copy into the node that already exists and
                # discarding what it carried threw the evidence away at the exact moment
                # the node was being drawn: `modelmarket.dev` reached
                # `monitor.attestedmemory.net` through Signal Hunt with three addresses
                # verified against Base, folded into its pending sphere, and showed none.
                _attach_declaration(existing, child.get("contracts"),
                                    result["nodes"], pending_nodes)
                continue
            # A genuinely new node, so now the question is whether it earns a sphere. Asked
            # HERE and not in `_peer_hub_children` because only this loop knows the child is
            # new: asking earlier also silenced the children that were about to become edges
            # to nodes we already draw, including our own hub.
            if not deserves_sphere(child, keep_anyway):
                silent.append(child["id"])
                continue
            kept.append(child)
        if silent:
            # Never silently. Every omission in this codebase that nobody could see turned
            # into "the map is lying" sooner or later — so the count reaches the log.
            logger.info(
                "%s: %d inherited node(s) neither supply, buy, nor hold a verified "
                "contract — not drawn (%s)",
                node["id"], len(silent), ", ".join(sorted(silent)[:5]),
            )
        for index, child in enumerate(kept):
            seen.add(child["id"])
            child["position"] = peer_hub_child_position(node["position"], index, len(kept))
            known_by_url[_norm_url(child.get("url"))] = child["id"]
            result["nodes"].append(child)
        kept_ids = {c["id"] for c in kept}
        for link in child_links:
            if link.get("target") in kept_ids:
                result["links"].append(link)

    from ecosystem_layout import pending_hub_position, pending_hub_ring_radius

    # The primary hub's own providers form its local star system.  They do not pass through
    # federation discovery and do not receive federation trust; their declaration was read
    # from the primary Hub itself and is retained under an explicit relationship.
    from ecosystem_layout import primary_hub_child_position

    for index, node in enumerate(own_ecosystem_nodes):
        normalized = _norm_url(node.get("url"))
        existing = known_by_url.get(normalized)
        if existing:
            result["links"].append({
                "source": "hub", "target": existing,
                "label": "owned provider", "kind": "ecosystem",
            })
            continue
        if node["id"] in seen:
            continue
        seen.add(node["id"])
        node["position"] = primary_hub_child_position(index, len(own_ecosystem_nodes))
        result["nodes"].append(node)
        result["links"].append({
            "source": "hub", "target": node["id"],
            "label": "owned provider", "kind": "ecosystem",
        })
        if normalized:
            known_by_url[normalized] = node["id"]

    # Strangers stay outside whatever the approved rings grew to, not outside what they used
    # to be — otherwise an expanding federation swallows its own quarantine ring.
    pending_ring = pending_hub_ring_radius(hub_ring, widest_cluster)
    for slot, node in enumerate(sorted(pending_nodes, key=lambda n: n["id"])):
        normalized = _norm_url(node.get("url"))
        existing = known_by_url.get(normalized)
        if existing:
            # The Hub retains this observation in its pending ledger.  The Monitor retains
            # it too, but as metadata rather than minting a second yellow sphere for the
            # same public address.  This is what previously drew Independent AI Hub twice
            # and Signal Hunt two/three times depending on refresh order.
            observation = {
                "url": node.get("url"),
                "label": node.get("label"),
                "status": "pending",
                "matched_node_id": existing,
                "detail": node.get("detail") or {},
                "metrics": node.get("metrics") or {},
            }
            result["pending_observations"].append(observation)
            for rendered in result["nodes"]:
                if rendered.get("id") == existing:
                    rendered["pending_observation"] = observation
                    break
            continue
        if node["id"] in seen:
            continue
        seen.add(node["id"])
        node["position"] = pending_hub_position(
            slot, len(pending_nodes), radius=pending_ring,
        )
        result["nodes"].append(node)
        result["links"].append({
            "source": "federation", "target": node["id"],
            "label": "Unapproved contact", "kind": "pending",
        })
        result["events"].append({
            "kind": "federation",
            "text": f"Unapproved hub visible: {node['label']} — awaiting operator approval",
            "level": "info",
        })
    return result


async def fetch_neighborhood_async(
    hub_url: str, *, limit: int = 2000, cursor: int = 0,
    allow_private: bool = False,
) -> dict[str, Any]:
    """Load one graph window from a Hub when the navigator moves to it.

    The caller must first verify that ``hub_url`` belongs to an approved node in the
    current graph. This function still applies the normal SSRF and response-size guards.
    It returns metadata only and never invokes a capability.
    """
    cfg = DiscoveryConfig(allow_private=allow_private)
    base = str(hub_url or "").strip().rstrip("/")
    limit = max(1, min(int(limit or 2000), 2000))
    cursor = max(0, int(cursor or 0))
    if not url_is_safe(base, allow_private=cfg.peer_allow_private):
        return {"neighbors": [], "count": 0, "next_cursor": None, "error": "unsafe hub URL"}
    timeout = httpx.Timeout(cfg.timeout, connect=cfg.timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        payload = await _get_json(
            client, f"{base}/ai-market/v2/federation/peers",
            allow_private=cfg.peer_allow_private, timeout=cfg.timeout,
        )
    if not isinstance(payload, dict):
        return {"neighbors": [], "count": 0, "next_cursor": None, "error": "hub unavailable"}
    approved = payload.get("peers") if isinstance(payload.get("peers"), list) else []
    pending = payload.get("pending") if isinstance(payload.get("pending"), list) else []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for trusted, entries in ((True, approved), (False, pending)):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url") or "").strip().rstrip("/")
            if not url or url in seen or not url_is_safe(url, allow_private=cfg.peer_allow_private):
                continue
            seen.add(url)
            rows.append({
                "url": url,
                "name": str(entry.get("name") or url)[:80],
                "trusted": trusted and bool(entry.get("trusted", True)),
                "status": str(entry.get("status") or ("active" if trusted else "pending")),
                "capabilities_count": int(entry.get("capabilities_count") or 0),
                "categories": [str(c) for c in (entry.get("categories") or []) if isinstance(c, str)][:8],
            })
    rows.sort(key=lambda row: row["url"])
    window = rows[cursor:cursor + limit]
    next_cursor = cursor + len(window) if cursor + len(window) < len(rows) else None
    return {"neighbors": window, "count": len(rows), "next_cursor": next_cursor, "hub_url": base}


# ── TTL cache + sync wrapper ────────────────────────────────────────

_cache_lock = threading.Lock()
# Keyed by (hub_url, allow_private) so a private-allowed UNI result is never
# served to the SSRF-guarded REAL path, and vice-versa.
_cache: dict[tuple[str, bool], tuple[float, dict[str, Any]]] = {}
_seen_peers: set[str] = set()


def _empty() -> dict[str, Any]:
    return {"nodes": [], "links": [], "events": [], "peer_count": 0, "errors": []}


def _with_events(data: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the graph data with a specific events list (shares nodes/links)."""
    return {**data, "events": events}


async def discover_from_sources(
    primary: str = "", *, allow_private: bool = False
) -> dict[str, Any]:
    """Ask each known map source in turn until one answers with a federation.

    A hub deployed on a new server has an empty federation of its own and drew an empty
    universe because the only address it knew to ask was itself. The committed list in
    `map_sources` is the bootstrap: somebody already has the map, and a new deployment
    should be able to find it without being told. See backend/map_sources.py for why the
    list is a seed rather than an authority.
    """
    from map_sources import map_sources

    errors: list[str] = []
    last: dict[str, Any] | None = None
    for source in map_sources(primary):
        found = await discover_async(source, allow_private=allow_private)
        last = found
        errors.extend(f"{source}: {e}" for e in (found.get("errors") or []))
        if found.get("nodes") or found.get("peer_count"):
            if source != (primary or "").rstrip("/"):
                found.setdefault("map_source", source)
            return found
    result = last or {
        "nodes": [], "links": [], "events": [], "peer_count": 0,
        "pending_count": 0, "errors": [],
    }
    result["errors"] = errors
    return result


async def discover_cached_async(hub_url: str, *, allow_private: bool = False) -> dict[str, Any]:
    """Cached variant for the async (real-mode) path. Events are delivered ONLY on
    the refresh that discovers a peer — cache hits carry no events (no replay)."""
    cfg = DiscoveryConfig(allow_private=allow_private)
    key = (hub_url.rstrip("/"), bool(cfg.allow_private))
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < cfg.refresh_s:
            return _with_events(hit[1], [])
    # Its own hub first; the committed map sources when that has nothing to show.
    fresh = await discover_from_sources(hub_url, allow_private=allow_private)
    events = _new_peer_events(fresh)
    with _cache_lock:
        _cache[key] = (now, fresh)  # stored without delivered events
    return _with_events(fresh, events)


def discover_cached_sync(hub_url: str, *, allow_private: bool = False) -> dict[str, Any]:
    """Cached variant for the sync (universe-mode worker-thread) path.

    Safe to call from a worker thread (no running event loop); mirrors the
    asyncio.run usage already in universe_layers.fetch_layers_sync.
    """
    cfg = DiscoveryConfig(allow_private=allow_private)
    key = (hub_url.rstrip("/"), bool(cfg.allow_private))
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < cfg.refresh_s:
            return _with_events(hit[1], [])
    try:
        fresh = asyncio.run(discover_async(hub_url, allow_private=allow_private))
    except Exception as exc:
        logger.warning("sync discovery failed: %s", exc)
        return _empty()
    events = _new_peer_events(fresh)
    with _cache_lock:
        _cache[key] = (now, fresh)
    return _with_events(fresh, events)


def _new_peer_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Emit a one-off activity event the first time each peer is discovered."""
    events: list[dict[str, Any]] = []
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _cache_lock:
        for node in result.get("nodes", []):
            nid = node.get("id")
            if nid and nid not in _seen_peers:
                _seen_peers.add(nid)
                events.append({
                    "id": f"disco_{nid}_{int(time.time())}",
                    "ts": ts,
                    "agent": str(node.get("label") or nid)[:32],
                    "action": "federation_join",
                    "target": "federation",
                    "amount": 0,
                    "token": "",
                    "onchain": False,
                })
    return events
