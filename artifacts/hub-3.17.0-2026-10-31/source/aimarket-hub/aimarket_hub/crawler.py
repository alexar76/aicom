"""Federation crawler — discovers peer hubs via .well-known/ai-market.json.

Implements BFS crawl: seed list → discover peers → crawl their manifests.
SSRF-hardened, response-size-limited, validates prices, pins public keys.
"""

from __future__ import annotations

import json
import contextlib
import logging
import math
import os
import time
from collections import deque
from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlparse

import httpx

from aimarket_hub.config import HubConfig
from aimarket_hub.federation_transport import peer_tool_endpoint
from aimarket_hub.database import HubDatabase
from aimarket_hub import contracts_declaration, realm
from aimarket_hub import __version__ as _HUB_VERSION
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import PQ_MISSING_ADVICE, Signer, pq_unverifiable, same_key
from aimarket_hub.trust import TrustScorer
from aimarket_hub.discovery_names import (
    DRAFT_CRAWLER_HEADER,
    DRAFT_WELL_KNOWN_PATH,
    LEGACY_CRAWLER_HEADER,
    normalize_discovery_document,
)
from aimarket_hub.validator import validate_manifest, validate_well_known

logger = logging.getLogger(__name__)

# The protocol's crawler token (spec §2: `AIMarketHub/2.0.0`) stays first, unchanged, so every
# matcher on it keeps working; the comment says which implementation and version is calling.
# Without it every hub's knock looked the same in a neighbour's `federation_inbound`, and an
# operator could not tell which hubs ran an outdated build (seen 2026-10-12).
USER_AGENT = f"AIMarketHub/2.0.0 (aimarket-hub {_HUB_VERSION})"

# Max response body size for well-known and manifest fetches
MAX_RESPONSE_BYTES = 2_000_000  # 2 MB

# Blocked IP ranges (RFC1918, link-local, loopback, metadata services).
#
# This list is the SECOND line of defence now, not the first: `_addr_is_blocked` rejects any
# address that is not globally routable, which covers every current and future
# special-purpose range without anyone having to remember to add it here. The list survives
# because two things slip past `is_global`: multicast (224.0.0.0/4 reports global) and the
# NAT64 well-known prefix (64:ff9b::/96 likewise), and because naming the common ranges
# explicitly makes a refusal legible in a log.
_BLOCKED_NETS = [
    ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"), ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"), ip_network("0.0.0.0/8"),
    ip_network("100.64.0.0/10"), ip_network("224.0.0.0/4"),
    ip_network("fc00::/7"), ip_network("fe80::/10"),
    ip_network("::1/128"), ip_network("::/128"),
    ip_network("ff00::/8"),          # IPv6 multicast
    ip_network("64:ff9b::/96"),      # NAT64: carries an IPv4 address in its low 32 bits
    ip_network("2002::/16"),         # 6to4: carries an IPv4 address in bits 16..48
]

#: Prefixes that TUNNEL an IPv4 address inside an IPv6 one. `ipv4_mapped` covers
#: ::ffff:0:0/96 and was already handled; these two were not, so `[64:ff9b::7f00:1]` and
#: `[2002:7f00:0001::]` were two more spellings of 127.0.0.1 that the blocklist waved through.
_NAT64_PREFIX = ip_network("64:ff9b::/96")
_SIXTO4_PREFIX = ip_network("2002::/16")


def _embedded_ipv4(addr):
    """The IPv4 address tunnelled inside an IPv6 one, or None.

    Covers ::ffff:0:0/96 (IPv4-mapped), 64:ff9b::/96 (NAT64) and 2002::/16 (6to4). Each is
    a different way to write an IPv4 destination, and a guard that understands only the
    first is a guard with two spellings of `127.0.0.1` still open.
    """
    if getattr(addr, "version", 4) != 6:
        return None
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        return mapped
    try:
        if addr in _NAT64_PREFIX:
            return ip_address(int(addr) & 0xFFFFFFFF)
        if addr in _SIXTO4_PREFIX:
            return ip_address((int(addr) >> 80) & 0xFFFFFFFF)
    except ValueError:
        return None
    return None


def _addr_is_blocked(addr) -> bool:
    """Is this resolved address one we refuse to fetch from?

    Allow-list shaped on purpose: anything not globally routable is refused, so a range
    nobody thought of (the IPv6 unspecified address was one) is refused by default rather
    than allowed by omission. The explicit `_BLOCKED_NETS` then catches the handful that
    `is_global` calls global anyway, and any IPv4 tunnelled inside the address is re-checked
    on its own terms.
    """
    try:
        if not addr.is_global:
            return True
    except (AttributeError, ValueError):
        return True
    for net in _BLOCKED_NETS:
        try:
            if addr in net:
                return True
        except TypeError:
            continue  # mixed address families never match
    inner = _embedded_ipv4(addr)
    if inner is not None:
        return _addr_is_blocked(inner)
    return False

# Price/latency/success bounds for imported capabilities
MIN_PRICE_USD = 0.0
MAX_PRICE_USD = 1000.0
MIN_LATENCY_MS = 0
MAX_LATENCY_MS = 300_000   # 5 minutes
MIN_SUCCESS_RATE = 0.0
MAX_SUCCESS_RATE = 1.0
MAX_CAPABILITIES_PER_MANIFEST = 1000


def _is_private_url(url: str) -> bool:
    """Check if URL resolves to a private/blocked network.

    Resolves DNS names via getaddrinfo and checks ALL resolved IPs against the
    blocklist. NOTE: this is a point-in-time check only — a caller that then
    connects by hostname re-resolves at connect time, so on its own this does NOT
    stop DNS rebinding. For rebinding-resistant fetches use
    outbound_http.safe_get / safe_post, which pin the validated IP (http + https).
    """
    import socket

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True

        # Try parsing as literal IP first
        try:
            addr = ip_address(hostname)
        except ValueError:
            pass  # not an IP literal, fall through to DNS resolution
        else:
            return _addr_is_blocked(addr)

        # DNS name — resolve and check ALL returned IPs
        try:
            addrinfos = socket.getaddrinfo(hostname, None)
        except (socket.gaierror, UnicodeError):
            # Can't resolve — treat as unsafe (don't fetch unresolvable hosts)
            return True
        for _family, _, _, _, sockaddr in addrinfos:
            ip_str = sockaddr[0]
            try:
                addr = ip_address(ip_str.split("%")[0])  # strip any zone id
            except ValueError:
                # An address we cannot even parse is not one to connect to.
                return True
            if _addr_is_blocked(addr):
                return True
        return False
    except Exception:
        # Defense in depth: if anything goes wrong, treat as unsafe
        return True


def _url_is_safe(url: str) -> bool:
    """Reject dangerous URL schemes and internal hosts."""
    if not url:
        return False
    if not url.startswith(("https://", "http://")):
        return False
    if any(c in url for c in "\r\n\t"):
        return False
    return not _is_private_url(url)


def _coerce_categories(value: Any) -> list[str]:
    """Sanitize a peer's self-declared categories — bounded count, strings only."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:32]:
        if isinstance(item, str):
            s = item.strip()[:64]
            if s:
                out.append(s)
    return out


def _coerce_count(value: Any) -> int:
    """Clamp a peer-advertised count to a sane non-negative range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, 1_000_000_000))



def _canonical_base_from_manifest_url(value: Any) -> str:
    """The hub base a `manifest_url` implies, or "" when it implies nothing usable.

    Strips the protocol's own suffix rather than taking the URL's origin, because a hub may
    be mounted under a path: `https://independentai.network/hub/ai-market/v2/manifest` is the
    hub at `https://independentai.network/hub`, not at the apex.
    """
    text = str(value or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return ""
    marker = "/ai-market/v2/manifest"
    if not text.endswith(marker):
        return ""
    return text[: -len(marker)].rstrip("/")


def _safe_tool_endpoint(tool: Any, base_url: str) -> str:
    """`peer_tool_endpoint`, and only if the SSRF guard would let us call it."""
    url = peer_tool_endpoint(tool, base_url)
    return url if url and _url_is_safe(url) else ""


def _norm_hub(value: Any) -> str:
    """One spelling for one hub, so "is this row the peer's own" has a stable answer."""
    text = str(value or "").strip().rstrip("/").lower()
    if text in ("", "local"):
        return text
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text



def _self_description(wk: dict[str, Any], base_url: str) -> dict[str, str]:
    """The four things a peer already publishes about itself, clamped.

    Read on every successful crawl, stored, and served back under a `declared` envelope —
    because the alternative is what happened: the monitor kept hand-written tables of the
    same facts, and they drifted from the peers they described.

    `declared_id` reads `ecosystem.product` first and `ecosystem.project` second, which is
    the whole reason peer identity never worked from this field: publishers write
    ``product`` and the reader looked for ``project``. It is a CLAIM either way — the hub
    resolves identity from the operator's own pin (aimarket_hub/peer_identity.py) and never
    from this string.

    `mcp_endpoint` is kept for display only, and only when it is safe and same-origin: a
    peer that could store an arbitrary URL here would have a stored SSRF pointer, and a
    stored endpoint is a stale endpoint the moment the peer moves — routing re-resolves it
    per invoke through federation_transport.
    """
    eco = wk.get("ecosystem") if isinstance(wk.get("ecosystem"), dict) else {}
    declared_id = str(eco.get("product") or eco.get("project") or "").strip()[:64]

    endpoint = str(wk.get("mcp_endpoint") or "").strip()[:500]
    if endpoint:
        from urllib.parse import urlparse

        try:
            base = urlparse(base_url)
            target = urlparse(endpoint)
            # `.port` RAISES on a port that is not a number in range — and this string came
            # from an untrusted document, so an unhandled ValueError here would abort the
            # whole crawl cycle for every peer, not just this one.
            same_origin = (
                target.scheme in ("http", "https")
                and (target.hostname or "").lower() == (base.hostname or "").lower()
                and (target.port or (443 if target.scheme == "https" else 80))
                == (base.port or (443 if base.scheme == "https" else 80))
            )
        except ValueError:
            same_origin = False
        if not (same_origin and _url_is_safe(endpoint)):
            endpoint = ""

    return {
        "description": str(wk.get("description") or "").strip()[:500],
        "hub_version": str(wk.get("hub_version") or "").strip()[:32],
        "declared_id": declared_id,
        "mcp_endpoint": endpoint,
    }


def _pq_ratchet_enabled() -> bool:
    """Whether a pinned post-quantum key is enforced against regression. ON unless opted out.

    `AIMARKET_PQ_RATCHET=0` disables it, which downgrades the rule to recording the change and
    letting the peer through. Kept as an escape hatch rather than a feature flag: the ratchet
    rejects peers, and an operator whose fleet regenerated a key must be able to stop the
    rejections while they re-pin, without waiting for a deploy.
    """
    raw = (os.environ.get("AIMARKET_PQ_RATCHET") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")



def _provider_pubkey(raw: Any) -> str:
    """An Ed25519 public key as base64 of its 32 bytes, or "" for anything else."""
    import base64
    text = str(raw or "").strip()
    if not text or len(text) > 64:
        return ""
    try:
        return text if len(base64.b64decode(text, validate=True)) == 32 else ""
    except Exception:
        return ""

#: Draft-path discovery URIs remembered per crawler instance; the map is advisory (a miss
#: means the legacy path is dialled), so clearing it on overflow costs one extra 404 at most.
_PEER_DISCOVERY_URLS_MAX = 4096


class Crawler:
    """BFS federation crawler — SSRF-hardened, key-pinning, bounded."""

    def __init__(
        self,
        config: HubConfig | None = None,
        db: HubDatabase | None = None,
        signer: Signer | None = None,
        trust_scorer: TrustScorer | None = None,
        slash_registry: Any = None,
    ):
        self.config = config or HubConfig()
        # base → draft-path discovery URI, learned from peers that advertise one.
        self._peer_discovery_urls: dict[str, str] = {}
        self.db = db or HubDatabase(self.config.db_path)
        self.signer = signer or Signer(self.config.signing_key_path)
        self.trust_scorer = trust_scorer or TrustScorer(self.db)
        self.slash_registry = slash_registry  # optional slash_sync.SlashRegistry for federated pull
        self._http = httpx.AsyncClient(
            timeout=self.config.request_timeout_s,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
            ),
        )

    async def _safe_get(self, url: str) -> httpx.Response:
        """Fetch a URL with size limits and SSRF protection.

        Disables redirects (each redirect target must pass _url_is_safe).
        Validates Content-Type is JSON-like.
        """
        # Import lazily: outbound_http delegates URL policy back to this module.
        # The helper pins the validated public IP, closing the check/connect DNS
        # rebinding window that a second hostname lookup would leave open.
        from aimarket_hub.outbound_http import prepare_safe_request_async

        target, pin_headers, extensions = await prepare_safe_request_async(url)
        # Both spellings of the reciprocal-identification header: the legacy one every
        # peer reads today, and the draft's (aimarket-protocol/ietf). Same value.
        headers = {
            "User-Agent": USER_AGENT,
            LEGACY_CRAWLER_HEADER: self.config.hub_url,
            DRAFT_CRAWLER_HEADER: self.config.hub_url,
            **pin_headers,
        }

        # follow_redirects=False — each hop would need its own _url_is_safe check.
        # If the server returns 3xx, the caller can re-fetch with the new URL
        # explicitly (after re-running _url_is_safe).
        request = self._http.build_request("GET", target, headers=headers)
        request.extensions.update(extensions)
        resp = await self._http.send(request, stream=True, follow_redirects=False)
        try:
            # Check Content-Length before reading body. Invalid values are refused
            # instead of accidentally disabling the limit.
            content_length = resp.headers.get("content-length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length") from exc
                if declared_length < 0 or declared_length > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Response too large: {content_length} bytes")
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").lower()
            if ctype and "json" not in ctype:
                raise ValueError(f"Unexpected Content-Type: {ctype[:60]}")
            body = bytearray()
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("Response body exceeds 2 MB limit")
            resp._content = bytes(body)
            return resp
        finally:
            await resp.aclose()

    async def crawl(self, *, clear_first: bool = True) -> dict[str, Any]:
        """Run a full crawl cycle. Returns summary dict.

        ``clear_first`` is accepted and ignored, and has been since the "clear before" logic
        was removed to close the empty-catalogue window (EXP-34). Stale rows are dropped
        PER PEER instead, right after that peer is successfully re-indexed — a peer that
        failed this cycle keeps its catalogue rather than being emptied by somebody else's
        outage.
        """
        # Don't clear before crawl — clear + repopulate atomically after success.
        # This prevents the empty-catalog DoS window (EXP-34).
        self.db.count_federated()

        logger.info("Crawler starting with %d seeds", len(self.config.seed_list))
        visited: set[str] = set()
        queue: deque[tuple[str, int, str]] = deque()

        # Validate seed URLs. A hub's own address is dropped here rather than at the
        # funnel in _crawl_one: the funnel returns None, which the drain loop counts as an
        # error, so a self-seed would post one phantom error per cycle forever. The funnel
        # check stays as the backstop for the paths that do not pass through here.
        safe_seeds = []
        for seed in self.config.seed_list:
            if not _url_is_safe(seed):
                continue
            if _norm_hub(seed.rsplit("/.well-known/", 1)[0]) == _norm_hub(self.config.hub_url):
                logger.warning(
                    "Seed %s is this hub's own address — skipping. A hub cannot be its "
                    "own peer; remove it from AIMARKET_SEED_LIST.", seed,
                )
                continue
            safe_seeds.append(seed)
        for seed_url in safe_seeds:
            queue.append((seed_url, 0, "seed"))

        # PENDING peers are enqueued too — and only pending. Without this the announce door
        # led nowhere: a peer known only from an announcement or an inbound crawl was never
        # fetched, so its catalogue was never previewed and approving it never led to
        # indexing. The whole documented join path stopped at its first step.
        #
        # Deliberately NOT every peer in the database. Already-active peers are reachable
        # through the BFS from the operator's seeds, and adding them here made each cycle
        # re-resolve and re-dial every peer the hub had ever heard of, dead ones included —
        # measured as seconds of DNS and connect timeouts per stale row. Pending peers have
        # no other path in, and their number is bounded by federation_open_max_pending.
        seeded = set(safe_seeds)
        pending: list = []
        with contextlib.suppress(Exception):
            pending = list(self.db.list_pending_peers())
        for peer in pending:
            wk_url = peer.well_known_url or f"{peer.url.rstrip('/')}/.well-known/ai-market.json"
            if wk_url in seeded or not _url_is_safe(wk_url):
                continue
            # A self row already in the table (written before the guards existed) would
            # otherwise be re-dialled every cycle and counted as an error every cycle.
            if _norm_hub(peer.url) == _norm_hub(self.config.hub_url):
                continue
            seeded.add(wk_url)
            queue.append((wk_url, 1, peer.discoverer or "pending"))

        stats = {"discovered": 0, "indexed": 0, "errors": 0, "peers_found": 0}

        async def drain() -> None:
            while queue:
                url, depth, discoverer = queue.popleft()
                if url in visited:
                    continue
                # SSRF guard: reject internal URLs discovered mid-crawl
                if not _url_is_safe(url):
                    logger.warning("Skipping unsafe peer URL: %s", url[:60])
                    continue
                # The realm seal: every path onto the frontier (seed, pending, gossip,
                # refresh) passes here, so a bubble never dials a host outside itself.
                if not realm.peer_inside(url):
                    logger.warning("Skipping peer outside the realm: %s", url[:60])
                    continue
                visited.add(url)

                if depth > self.config.max_crawl_depth:
                    continue

                result = await self._crawl_one(url, depth, discoverer)
                if result is None:
                    stats["errors"] += 1
                    continue

                stats["discovered"] += 1
                stats["indexed"] += result["capabilities_count"]
                stats["peers_found"] += len(result.get("new_peer_urls", []))

                for peer_url in result.get("new_peer_urls", []):
                    peer_base = str(peer_url).rstrip("/")
                    # A peer listed by its draft-path discovery URI is dialled there;
                    # everyone else at the legacy path, which is all they serve.
                    peer_wk = self._peer_discovery_urls.get(peer_base) or (
                        f"{peer_base}/.well-known/ai-market.json"
                    )
                    if (
                        not peer_base
                        or _norm_hub(peer_base) == _norm_hub(self.config.hub_url)
                        or peer_wk in visited
                        or not _url_is_safe(peer_wk)
                        or not realm.peer_inside(peer_wk)
                    ):
                        continue
                    # A trusted Hub told us this address exists. Persist that knowledge
                    # before dialing it: an offline new Hub should still be visible in the
                    # federation/Alien Monitor, exactly like an observed blockchain address.
                    # announce_peer never rewrites an existing pin or upgrades trust.
                    self.db.announce_peer(
                        Peer(
                            url=peer_base,
                            name=peer_base,
                            well_known_url=peer_wk,
                            depth=depth + 1,
                            discoverer=f"gossip:{url.rsplit('/.well-known/', 1)[0]}",
                        ),
                        max_pending=self.config.federation_gossip_max_observed,
                    )
                    queue.append((peer_wk, depth + 1, url))

        await drain()

        # Approved peers that this cycle never reached. The frontier deliberately carries
        # only seeds and pending peers, on the assumption that "already-active peers are
        # reachable through the BFS from the operator's seeds" — and that assumption is false
        # the moment a peer is not linked from any seed. Live proof: hunt.modelmarket.dev was
        # an APPROVED peer with five capabilities of its own, last crawled 2026-08-11, and
        # none of them had ever reached the catalogue seventeen days later. Approving a hub
        # tells the operator its capabilities will be "indexed on the next crawl", and for a
        # hub nobody links to there was no next crawl.
        #
        # Bounded and stalest-first rather than "every row every cycle", which is the cost
        # the original comment was avoiding: a handful of dead rows must not turn each cycle
        # into minutes of DNS and connect timeouts.
        try:
            refresh_max = max(0, int(os.getenv("AIMARKET_CRAWL_REFRESH_MAX", "25")))
        except (TypeError, ValueError):
            refresh_max = 25
        if refresh_max:
            unreached = []
            with contextlib.suppress(Exception):
                for peer in self.db.list_peers():
                    if str(getattr(peer, "status", "active")) != "active":
                        continue
                    wk_url = peer.well_known_url or f"{peer.url.rstrip('/')}/.well-known/ai-market.json"
                    if wk_url in visited or wk_url in seeded or not _url_is_safe(wk_url):
                        continue
                    unreached.append((str(getattr(peer, "last_crawl", "") or ""), wk_url, peer))
            unreached.sort(key=lambda row: row[0])
            for _stamp, wk_url, peer in unreached[:refresh_max]:
                seeded.add(wk_url)
                queue.append((wk_url, 1, peer.discoverer or "refresh"))
            if unreached:
                logger.info(
                    "crawler: refreshing %d approved peer(s) no seed links to (of %d)",
                    min(len(unreached), refresh_max), len(unreached),
                )
            await drain()

        slashes_pulled = 0
        for peer in self.db.list_peers():
            score = self.trust_scorer.compute_score(peer.url)
            peer.trust_score = score
            # Preserve the status. upsert_peer defaults to "active" because a successful crawl
            # is what normally calls it — but this loop is a trust-score refresh, not a crawl,
            # and defaulting here silently cleared a peer's key_mismatch flag (and its
            # pin_reject_reason) on every cycle, un-rejecting a takeover the crawler had caught.
            self.db.upsert_peer(peer, status=peer.status or "active")
            # Federated reputation (F2): pull the peer's signed slash log, bound to its key.
            if self.slash_registry is not None and getattr(peer, "public_key", ""):
                slashes_pulled += await self._pull_peer_slashes(
                    peer.url, peer.public_key, trusted=bool(getattr(peer, "trusted", False)),
                )

        if slashes_pulled:
            stats["slashes_pulled"] = slashes_pulled
        if getattr(self.config, "federation_assay", True):
            try:
                from aimarket_hub.federation_assay import assay_pending_peers
                dossiers = await assay_pending_peers(
                    self.db,
                    config=self.config,
                    signer=self.signer,
                    crawler=self,
                    limit=3,
                )
                if dossiers:
                    stats["assayed"] = len(dossiers)
            except Exception as exc:
                logger.warning("pending assay cycle failed: %s", exc)
        logger.info(
            "Crawl complete: %d discovered, %d indexed, %d errors, %d slashes",
            stats["discovered"], stats["indexed"], stats["errors"], slashes_pulled,
        )
        return stats

    async def _proves_same_key(self, base: str, expected_key: str) -> bool:
        """Does `base` answer its own well-known with exactly `expected_key`?

        This is the whole safety of the supersede path. A claim to live somewhere else is
        just a string in a stranger's document until that somewhere signs for it, so the
        claimed home is fetched through the same SSRF-hardened door as any other peer and
        must present the identical key. Any failure - unreachable, malformed, different key -
        is a NO: the row stays where it is and the assay's off-origin check still flags it.
        """
        if not base or not expected_key:
            return False
        try:
            resp = await self._safe_get(f"{base}/.well-known/ai-market.json")
            if getattr(resp, "status_code", 0) not in (200, 304):
                return False
            wk = resp.json()
        except Exception as exc:
            logger.debug("supersede probe of %s failed: %s", base, exc)
            return False
        if not isinstance(wk, dict):
            return False
        return str(wk.get("signer_public_key") or "").strip() == expected_key

    async def _pull_peer_slashes(self, peer_url: str, peer_pubkey: str, *, trusted: bool = False) -> int:
        """Fetch and ingest a peer's signed slash log, binding issuer identity to the peer's
        published key (a peer may only vouch for slashes it signed). Fault-tolerant: a failing
        peer is skipped, never aborting the crawl.

        F6 anti-poisoning: the weak tier (no consumer PoM) is only accepted from
        **operator-TRUSTED** peers. From a first-contact / unapproved peer we accept
        only STRONG (consumer-signed) attestations — those are independently verifiable
        and cannot be forged without a real wronged consumer, so an untrusted peer can
        never manufacture a federated penalty. Without this gate, two throwaway Sybil
        hubs could weak-slash a competitor (the very attack ``require_pom`` prevents).
        """
        url = peer_url.rstrip("/") + "/ai-market/v2/reputation/slashes"
        try:
            if not _url_is_safe(url):
                return 0
            resp = await self._safe_get(url)
            if resp.status_code != 200:
                return 0
            envelopes = resp.json().get("slashes", [])
            # Weak tier is opt-in (AIMARKET_SLASH_ACCEPT_WEAK, default on) AND only from
            # trusted peers; a slash still needs ≥2 distinct weak issuers to move the
            # penalty, so approved peers cannot single-handedly slash either.
            weak_enabled = os.environ.get("AIMARKET_SLASH_ACCEPT_WEAK", "1").strip() != "0"
            accept_weak = weak_enabled and trusted
            return self.slash_registry.ingest_remote(
                envelopes, verifier=self.signer,
                expected_issuer_pubkey=peer_pubkey, accept_weak=accept_weak,
                peer_url=peer_url,
            )
        except Exception as exc:
            logger.debug("slash pull from %s failed: %s", peer_url[:60], exc)
            return 0

    async def _crawl_one(
        self, well_known_url: str, depth: int, discoverer: str,
    ) -> dict[str, Any] | None:
        """Crawl a single hub via its .well-known endpoint."""
        base_url = well_known_url.rsplit("/.well-known/", 1)[0]

        # Never crawl ourselves. The gossip branch has always filtered its own address,
        # but a URL reaches the frontier from three places — seeds, the pending queue,
        # gossip — and the other two did not check. A hub whose AIMARKET_SEED_LIST is its
        # own well-known (a natural thing to write, and what independentai.network/hub
        # actually ships) therefore fetched itself, met an unknown peer on first contact,
        # and filed *itself* as pending: a permanent slot in the open-federation queue and
        # one self-dial per cycle. The check lives here because this is the single funnel
        # every path goes through, and it compares through _norm_hub — the raw string
        # compare in the gossip branch missed a scheme or case difference, and missed a
        # path-based hub advertised under its apex.
        if _norm_hub(base_url) == _norm_hub(self.config.hub_url):
            logger.warning(
                "Refusing to crawl this hub's own address %s (queued by %s) — "
                "a hub cannot be its own peer. Remove it from AIMARKET_SEED_LIST.",
                base_url, discoverer or "?",
            )
            return None

        # 1. Fetch .well-known (SSRF-hardened)
        try:
            resp = await self._safe_get(well_known_url)
            if resp.status_code == 304:
                return {"capabilities_count": 0, "new_peer_urls": []}
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", well_known_url, exc)
            return None

        try:
            wk = resp.json()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON at %s", well_known_url)
            return None
        # A peer may serve the draft's member names (catalogue_url, peers as discovery
        # URIs). Fill the legacy names from them so everything below reads one shape.
        wk = normalize_discovery_document(wk)

        # 2. Validate well-known structure
        errors = validate_well_known(wk)
        if errors:
            logger.warning("Invalid well-known at %s: %s", well_known_url, errors)
            return None

        # 2b. Is this us, under a name we do not answer to?
        #
        # The URL guard above compares SPELLINGS, and a hub outlives its spellings.
        #
        # A RENAME is what produces this, not stray gossip. The competing lab hub ran as
        # `http://108.165.32.182:9083` from 2026-09-01T11:56:22Z to 2026-09-03T19:05:34Z and
        # stamped that address into `X-AIMarket-Crawler` on every fetch, so its neighbours
        # recorded it exactly as the open-federation door is meant to: three of them logged
        # 300-616 inbound hits under it. At 19:05:35Z the operator restarted it as
        # `https://hub.modelmarket.dev`. The old identity did not stop existing — pending
        # rows never expire, and ten seconds after the rename the hub read its own former
        # address back out of a neighbour's document and filed it as a stranger, then
        # rendered it in its own UNAPPROVED HUBS block with a red "assay failed" badge.
        # Measured 2026-09-05: that row's key, the raw-IP endpoint's key and the page's own
        # `signer_public_key` were one string.
        #
        # A URL is a name and a hub has many; the signing key IS the hub. This is the first
        # point where the key is known — the announce path writes its row before anyone
        # dials — so the identity check belongs here, with the string compare kept above as
        # the cheap first pass that avoids the fetch entirely.
        #
        # This is the FILTER, not the cure. It stops THIS hub adopting its own past, and
        # nothing more: the same address was still ACTIVE and TRUSTED on a neighbour on
        # 2026-09-05, and every hub that holds it re-publishes it. A renamed hub needs a way
        # to retire an identity it has already advertised; until then each hub can only
        # decline to be fooled by its own.
        #
        # Verified before landing: all 14 hubs in this federation publish distinct keys, so
        # nothing here shares a signer. A deployment that deliberately ran two hubs from one
        # key WOULD be refused federation between them, and should give the second its own.
        advertised = str(wk.get("signer_public_key") or "").strip()
        own = str(getattr(getattr(self, "signer", None), "public_key_b64", "") or "").strip()
        if advertised and own and advertised == own:
            logger.warning(
                "Refusing %s (queued by %s): it answers with THIS hub's own signing key — "
                "our own address under another name. Dropping the row.",
                base_url, discoverer or "?",
            )
            try:
                self.db.delete_peer(base_url)
            except Exception as exc:  # pragma: no cover - never fail a crawl over cleanup
                logger.debug("could not drop self-row %s: %s", base_url, exc)
            return None

        # 2c. Is this hub answering under a name it no longer calls itself?
        #
        # A hub outlives its addresses, and the protocol has no retraction. The competing lab
        # hub ran as `http://108.165.32.182:9083` for two days, every neighbour recorded that
        # address exactly as the open-federation door intends, and then it was renamed to
        # `https://hub.modelmarket.dev`. The old rows did not die with the old name: measured
        # 2026-09-05, a neighbour still held the plaintext raw IP as its ACTIVE, TRUSTED peer
        # and knew the hub by no other name.
        #
        # The endpoint itself says where it lives — `manifest_url` is where it wants its
        # catalogue read from. When that points somewhere else AND that somewhere answers
        # with the SAME signing key, the two names are one hub and this row is the stale one.
        #
        # The key match is what makes this safe. A hub that advertises a `manifest_url` on a
        # domain it does not control gets nothing: we fetch that domain, its key is its own,
        # the claim fails, and the row is left exactly where it was for the assay's
        # off-origin check to flag. Only a hub that can answer at BOTH names with ONE key can
        # move its own row — which is the definition of the thing being the same hub.
        #
        # Trust migrates with the row. Retiring an operator-approved peer into a fresh
        # pending row would punish the hub for renaming itself, so the canonical name
        # inherits the decision that was already made about this identity.
        canonical = _canonical_base_from_manifest_url(wk.get("manifest_url"))
        if canonical and advertised and _norm_hub(canonical) != _norm_hub(base_url):
            if await self._proves_same_key(canonical, advertised):
                old = self.db.get_peer(base_url)
                was_trusted = bool(getattr(old, "trusted", False))
                logger.warning(
                    "%s answers with the same key as %s, which it names as its own home — "
                    "superseding the row (trusted=%s).",
                    base_url, canonical, was_trusted,
                )
                try:
                    if self.db.get_peer(canonical) is None:
                        moved = Peer(
                            url=canonical,
                            name=str(wk.get("name") or canonical),
                            capabilities_count=0,
                            well_known_url=f"{canonical}/.well-known/ai-market.json",
                            public_key=advertised,
                            depth=getattr(old, "depth", depth) or depth,
                            discoverer="supersede:%s" % (discoverer or "crawl"),
                        )
                        self.db.upsert_peer(moved, status="active" if was_trusted else "pending")
                        if was_trusted:
                            self.db.set_peer_trusted(canonical, True)
                    self.db.delete_peer(base_url)
                except Exception as exc:  # pragma: no cover - a crawl must survive cleanup
                    logger.warning("supersede of %s -> %s failed: %s", base_url, canonical, exc)
                    return None
                return {"capabilities_count": 0, "new_peer_urls": [canonical]}

        # 3. Record or update peer (pubkey pinning)
        hub_name = wk.get("name", base_url)
        categories = _coerce_categories(wk.get("categories"))
        existing_peer = self.db.get_peer(base_url)
        advertised_key = wk.get("signer_public_key", "")
        prior_key = existing_peer.public_key if existing_peer else ""
        # The PQ key travels INSIDE the signature block, not beside it as `signer_public_key`
        # does, because it is part of the signature object the peer produced.
        wk_sig = wk.get("signature")
        advertised_pq_key = str(
            (wk_sig.get("pq_public_key") if isinstance(wk_sig, dict) else "") or ""
        )
        prior_pq_key = existing_peer.pq_public_key if existing_peer else ""
        signed_gossip = self._well_known_gossip_verified(wk, advertised_key)

        # Operator-vouched trusted seed: if we pinned this seed's key out of band
        # (federation_seeds.json / AIMARKET_SEED_PUBKEYS) and the peer advertises
        # exactly that key, trust + index it on FIRST contact instead of waiting
        # for manual approval. A key mismatch falls back to the safe path below.
        pinned_seed_key = (
            self.config.seed_pubkeys.get(base_url)
            or self.config.seed_pubkeys.get(well_known_url)
        )
        trusted_via_seed = bool(
            pinned_seed_key and advertised_key and same_key(advertised_key, pinned_seed_key)
        )
        is_first_contact = not (prior_key or trusted_via_seed)

        if prior_key:
            # Subsequent crawl: pubkey MUST match what we pinned previously.
            # Compared by KEY, not by string: the same key re-published in the other
            # base64 alphabet is not a takeover (see signing.same_key).
            if advertised_key and not same_key(advertised_key, prior_key):
                logger.warning(
                    "Peer %s public key changed! Rejecting (possible takeover). "
                    "Old: %s... New: %s...",
                    base_url, prior_key[:16], advertised_key[:16],
                )
                # Persist so /federation/peers surfaces "peer rejected: key changed"
                # instead of looking healthy while the catalogue freezes.
                try:
                    self.db.record_peer_key_mismatch(
                        base_url,
                        pinned_key=prior_key,
                        advertised_key=advertised_key,
                    )
                except Exception as exc:  # noqa: BLE001 — never fail closed on telemetry
                    logger.debug("Could not persist key mismatch for %s: %s", base_url, exc)
                return None
            pinned_key = prior_key
        elif trusted_via_seed:
            pinned_key = pinned_seed_key
            logger.info(
                "Trusted seed %s — advertised key matches operator pin; "
                "indexing on first contact.", base_url,
            )
        else:
            # First contact, untrusted: record the peer but do not trust the pubkey
            # until a sandbox assay pass (auto-admit) or an operator / seed pin.
            pinned_key = advertised_key
            if pinned_seed_key and advertised_key and not same_key(advertised_key, pinned_seed_key):
                logger.warning(
                    "Seed %s advertised key %s... does NOT match operator pin %s... "
                    "— treating as untrusted first contact.",
                    base_url, advertised_key[:16], pinned_seed_key[:16],
                )
            else:
                logger.info(
                    "First contact with peer %s — recording but not trusting "
                    "manifest until manual approval. Advertised pubkey: %s...",
                    base_url, advertised_key[:16] if advertised_key else "(none)",
                )

        # A peer's manifests are indexed ONLY when trusted: either operator-pinned via seed, or
        # explicitly approved before (preserved across crawls). Being crawled twice never grants
        # trust — this closes the TOFU manifest-injection hole.
        trusted = trusted_via_seed or bool(existing_peer and existing_peer.trusted)

        # ── Post-quantum identity: pin on first sight, record a change, never reject on it ──
        #
        # Collected NOW because attribution is only possible while classical signatures still
        # work: a PQ key first seen after Ed25519 falls cannot be tied to anyone. Unpinned, the
        # PQ layer authenticates the document and not the peer.
        #
        # A change is RECORDED and not rejected while PQ is not required. Rejecting would put
        # every legitimate rotation in quarantine — including the ones this fleet will cause on
        # its own, since a component whose key path is not on a volume regenerates its ML-DSA
        # key on every container recreate. Enforcement belongs to `AIMARKET_PQC_REQUIRE`, which
        # already gates the verification policy, rather than to a second switch here.
        pinned_pq_key = prior_pq_key or advertised_pq_key
        advertised_pq_mismatch = ""
        if prior_pq_key and advertised_pq_key != prior_pq_key:
            # THE RATCHET. A peer that has demonstrated post-quantum capability may not silently
            # regress — neither by withdrawing its key (the downgrade attack, which is precisely
            # what an adversary who has broken Ed25519 does) nor by substituting a different one
            # (which is what they do when withdrawal is refused).
            #
            # Per-peer and automatic, deliberately NOT a global `require` switch: a newcomer has
            # no pin, so nothing here touches it and the cost of joining stays zero. Only a peer
            # that once signed hybrid is held to it.
            #
            # Safe to enforce because a legitimate rotation now has a remedy —
            # `POST /federation/peers/repin` accepts `pq_public_key`. Without that endpoint this
            # rule would be a one-way door.
            if _pq_ratchet_enabled():
                logger.warning(
                    "Peer %s REJECTED: post-quantum key %s (pin %s...). "
                    "Re-pin via POST /federation/peers/repin with pq_public_key if this rotation "
                    "is legitimate.",
                    base_url,
                    "changed" if advertised_pq_key else "withdrawn",
                    prior_pq_key[:16],
                )
                try:
                    self.db.record_peer_pq_mismatch(
                        base_url,
                        pinned_pq_key=prior_pq_key,
                        advertised_pq_key=advertised_pq_key,
                    )
                except Exception as exc:  # noqa: BLE001 — never fail closed on telemetry
                    logger.debug("Could not persist PQ mismatch for %s: %s", base_url, exc)
                return None
            pinned_pq_key = prior_pq_key            # ratchet off: the pin stands, change is noted
            advertised_pq_mismatch = advertised_pq_key
            logger.warning(
                "Peer %s post-quantum key %s; pin kept (ratchet disabled by env)",
                base_url, "changed" if advertised_pq_key else "withdrawn",
            )
        elif advertised_pq_key and not prior_pq_key:
            logger.info(
                "Pinned post-quantum key for peer %s on first sight: %s...",
                base_url, advertised_pq_key[:16],
            )

        peer = Peer(
            url=base_url,
            name=hub_name,
            capabilities_count=_coerce_count(wk.get("capabilities_count", 0)),
            last_crawl=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            well_known_url=well_known_url,
            manifest_url=wk.get("manifest_url", f"{base_url}/ai-market/manifest"),
            public_key=pinned_key,
            pq_public_key=pinned_pq_key,
            advertised_pq_public_key=advertised_pq_mismatch,
            depth=depth,
            discoverer=discoverer,
            categories=categories,
            trusted=trusted,
            # What the peer says about itself. Written HERE and nowhere else: an
            # unauthenticated announce must not be able to seed a description or an id,
            # so `announce_peer` keeps writing exactly what it wrote before.
            **_self_description(wk, base_url),
            # ...including what it says it has on chain. Re-read on EVERY crawl, so a peer
            # that deploys an escrow tomorrow starts being re-exported with one on the next
            # pass, and a peer that withdraws it stops — without an operator anywhere in
            # the loop. `sanitize` returns {} for a peer that declares nothing, which is
            # also what clears a stale declaration.
            declared_contracts=contracts_declaration.sanitize(wk.get("contracts")) or {},
        )
        # `pending` marks a peer that arrived through the open door. A peer discovered by the
        # operator's own seed list is untrusted-until-approved but not *pending* — writing
        # pending here unconditionally hid every known-unapproved peer from /federation/peers
        # and from the published .well-known, because list_peers() filters pending out.
        pending = not trusted
        # An ALIAS of a hub we already trust must not become a second active row. This is how
        # a plaintext raw-IP peer got into production: `https://hub.modelmarket.dev` lists
        # `http://108.165.32.182:9083` in its own `observed_hubs` — the competing lab observing
        # itself by IP — the gossip path adopted that address, and the crawl then pinned the
        # same signing key to it. Two active rows for one hub, one of them plaintext, and every
        # federated call to that row travelling in the clear.
        #
        # Left visible as `pending` rather than dropped: the operator should see the alias and
        # decide, and an alias is also what a takeover attempt looks like from here.
        if not pending and pinned_key:
            twin = self.db.active_peer_with_public_key(pinned_key, exclude_url=peer.url)
            if twin:
                logger.warning(
                    "peer %s carries the signing key already active at %s — keeping it "
                    "pending instead of indexing the same hub twice",
                    peer.url,
                    twin,
                )
                pending = True
                trusted = False
                peer.trusted = False
        self.db.upsert_peer(peer, status="pending" if pending else "active")

        # 4. Index manifests from TRUSTED peers only. An unapproved peer (first contact or not)
        #    is recorded as pending; an operator must approve it (db.set_peer_trusted / admin
        #    endpoint) or pin its key via AIMARKET_SEED_PUBKEYS.
        if not trusted:
            previewed = await self._preview_pending_manifest(
                wk, base_url, pinned_key, pinned_pq_key)
            logger.info(
                "Peer %s pending operator approval — manifest indexing skipped"
                "%s", base_url,
                f" ({previewed} capabilities previewed)" if previewed else "",
            )
            # Trust gates commerce, not topology. A self-consistent signed discovery
            # document may relay address observations even before this Hub is approved;
            # every relayed address still lands pending and gets no catalogue rights.
            return {
                "capabilities_count": 0,
                "new_peer_urls": (
                    self._extract_peer_urls(wk, include_observed=True)
                    if signed_gossip else []
                ),
            }

        # Fetch and index manifest (trusted peers only)
        manifest_url = wk.get("manifest_url", f"{base_url}/ai-market/manifest")
        if not _url_is_safe(manifest_url):
            logger.warning("Manifest URL rejected as unsafe: %s", manifest_url[:60])
            return {"capabilities_count": 0, "new_peer_urls": self._extract_peer_urls(wk, include_observed=signed_gossip)}
        indexed = 0
        try:
            manifest_resp = await self._safe_get(manifest_url)
            manifest = manifest_resp.json()

            # Validate manifest structure
            m_errors = validate_manifest(manifest)
            if m_errors:
                logger.warning("Invalid manifest at %s: %s", manifest_url, m_errors)
                return None

            # Verify signature. The PQ pin is passed so a PRESENT post-quantum signature is
            # checked against the key this hub recorded for the peer, not against the key the
            # document carries — an unpinned PQ key authenticates the document and not the peer.
            # Empty pin means "not pinned yet", and then the document's own key is used, which is
            # exactly the migration state this is here to end.
            if not self.signer.verify_manifest_signature(manifest, pinned_key, pinned_pq_key):
                if pq_unverifiable(manifest.get("signature")):
                    # Not the peer's fault: the document is fine and THIS hub cannot read it.
                    logger.error("Manifest at %s refused, not indexed: %s.", manifest_url,
                                 PQ_MISSING_ADVICE)
                else:
                    logger.warning("Invalid manifest signature at %s", manifest_url)
                return None

            # Freshness: reject a stale/replayed (or far-future) signed manifest.
            if self._manifest_too_stale(manifest):
                logger.warning(
                    "Manifest at %s rejected as stale/replayed (generated_at=%s)",
                    manifest_url, manifest.get("generated_at"),
                )
                return {"capabilities_count": 0, "new_peer_urls": self._extract_peer_urls(wk, include_observed=signed_gossip)}

            # Index capabilities
            indexed = self._index_manifest_capabilities(manifest, base_url, hub_name, evidence={
                "kind": "signed_catalogue",
                "scope": "catalogue",
                "signer": base_url,
                "signer_public_key": pinned_key,
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "checked_by": self.config.hub_url,
            })
            self._warn_on_index_shortfall(manifest, base_url, indexed)
            self._prune_unlisted(base_url)

        except Exception as exc:
            logger.warning("Failed to fetch/parse manifest at %s: %s", manifest_url, exc)
            # Still return peer data even if manifest fetch fails
            return {"capabilities_count": 0, "new_peer_urls": self._extract_peer_urls(wk, include_observed=signed_gossip)}

        return {
            "capabilities_count": indexed,
            "new_peer_urls": self._extract_peer_urls(wk, include_observed=signed_gossip),
        }

    async def _preview_pending_manifest(
        self, wk: dict[str, Any], base_url: str, pinned_key: str, pinned_pq_key: str = ""
    ) -> int:
        """Read a PENDING peer's manifest into the preview table. Never indexes.

        The operator has to decide whether to approve a stranger, and until now the
        only thing on offer was a URL. This fetches what the peer claims to sell so
        that decision can be made by looking at it — under exactly the same defences
        the trusted path uses: SSRF-checked URL, size-capped body, schema validation,
        signature check and a freshness bound.

        What the signature proves here is narrow, and worth stating plainly: the
        manifest was signed by whoever holds the key the peer advertises, and was not
        altered in transit. It says nothing about that key belonging to anyone
        trustworthy. That is what operator approval is for.

        Rows go to ``peer_preview_capabilities`` — a table no search, routing, invoke
        or manifest query reads. Returns how many were previewed (0 on any failure;
        a preview is a convenience and must never break a crawl).
        """
        # Its OWN switch decides this, not the open door. A closed-door hub still has
        # pending peers — an inbound crawler is quarantined as pending in default mode,
        # and a seed the operator never approved is pending too — and the landing page
        # renders "capabilities: N" and a "Show what it offers" button for every one of
        # them. Tied to `federation_open`, those read 0 and empty on every closed-door
        # hub in the fleet: a promise the page could not keep (hub.attestedmemory.net,
        # 4 knocking peers, 0 previewed, 2026-09-08). The defences that make a preview
        # safe are in this function, not in the door: SSRF-checked URL, size-capped
        # body, schema validation, a signature that must verify against the key we
        # pinned, a freshness bound, and rows that land in a table no search, routing,
        # invoke or manifest query reads.
        if not self.config.federation_preview_capabilities:
            return 0
        if not pinned_key:
            return 0  # nothing to verify against — refuse rather than show unsigned claims
        manifest_url = wk.get("manifest_url", f"{base_url}/ai-market/manifest")
        if not _url_is_safe(manifest_url):
            return 0
        try:
            manifest = (await self._safe_get(manifest_url)).json()
            if validate_manifest(manifest):
                return 0
            # Satellite CI / thin images fall back to a structural basic check that
            # does not inspect per-tool fields. Preview must still refuse half-built
            # tools (missing description / input_schema) so the operator never sees
            # a claim that would fail full schema validation in the monorepo.
            tools_raw = manifest.get("tools")
            if not isinstance(tools_raw, list):
                return 0
            for tool in tools_raw:
                if not isinstance(tool, dict):
                    return 0
                if not str(tool.get("name") or "").strip():
                    return 0
                if "description" not in tool or "input_schema" not in tool:
                    return 0
            if not self.signer.verify_manifest_signature(manifest, pinned_key, pinned_pq_key):
                if pq_unverifiable(manifest.get("signature")):
                    logger.error("Preview skipped for %s: %s.", base_url, PQ_MISSING_ADVICE)
                else:
                    logger.info("Preview skipped for %s — manifest signature invalid", base_url)
                return 0
            if self._manifest_too_stale(manifest):
                return 0
            # A manifest carries `tools`, not `capabilities` — `capabilities_count` is a
            # number beside it, and reading the wrong key previewed zero rows against every
            # real peer while every test passed, because the tests wrote preview rows directly.
            caps = tools_raw
            if not isinstance(caps, list):
                return 0
            limit = max(0, int(self.config.federation_preview_max_caps))
            rows = [c for c in caps[:limit] if isinstance(c, dict)]
            return self.db.replace_preview_capabilities(base_url, rows)
        except Exception as exc:  # pragma: no cover - defensive
            # WARNING, not INFO. This branch is how a preview turns into a permanent zero
            # on the operator's screen, and at INFO the container swallowed it: the
            # Postgres upsert had been failing on every crawl for as long as the feature
            # existed, and the page just said 0. A number that cannot be produced has to
            # say so somewhere the operator will actually see it.
            logger.warning("Preview of %s failed: %s", base_url, exc)
            return 0

    def _warn_on_index_shortfall(
        self, manifest: dict[str, Any], base_url: str, indexed: int
    ) -> int | None:
        """Log when a peer declares more capabilities than we indexed.

        Found the hard way: ATLAS published seven capabilities and this hub's catalogue
        carried six. The missing one was a priced, fully implemented $0.12 SKU that no
        buyer could discover, and nothing anywhere said a number had gone missing —
        ``capabilities_count: 6`` looked like the truth about the peer rather than the
        truth about our last crawl of it. Returns the declared total when it disagrees,
        so the caller (and tests) can see the gap; ``None`` when it agrees or the peer
        declared nothing.
        """
        for key in ("total_capabilities", "capabilities_count"):
            raw = manifest.get(key)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                continue
            if raw > indexed:
                logger.warning(
                    "Peer %s declares %d capabilities in %s but only %d were indexed — "
                    "the catalogue will under-report this peer until the gap is explained",
                    base_url, raw, key, indexed,
                )
                return raw
            return None
        return None

    _indexed_now: set = set()

    def _index_manifest_capabilities(
        self, manifest: dict[str, Any], base_url: str, hub_name: str,
        *, evidence: dict[str, Any] | None = None,
    ) -> int:
        """Index validated capabilities from a manifest into the database.

        All prices, latencies, and success rates are sanity-checked.
        Malicious values are clamped or cause the tool to be skipped.
        """
        count = 0
        self._indexed_now = set()
        tools = manifest.get("tools") or []
        if len(tools) > MAX_CAPABILITIES_PER_MANIFEST:
            logger.warning(
                "Manifest from %s has %d tools — limiting to %d",
                base_url, len(tools), MAX_CAPABILITIES_PER_MANIFEST,
            )
            tools = tools[:MAX_CAPABILITIES_PER_MANIFEST]

        peer_host = _norm_hub(base_url)
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            # Index only what this peer ORIGINATES. A hub's manifest carries its federated
            # rows too, so importing all of them re-imports our own catalogue through
            # whoever else federates with us: crawling hunt.modelmarket.dev pulled 101 tools
            # of which 96 were ATLAS, GAIA and the oracle family coming back a second time.
            # Measured on the live catalogue the moment those peers became reachable —
            # 274 rows for 103 distinct capabilities, 92 of them duplicated — and a buyer
            # routed through the copy pays two hops to reach a provider we already index
            # directly. Their origin is crawled on its own; a re-export is not a listing.
            origin = _norm_hub(tool.get("source_hub"))
            if origin and origin not in ("local", peer_host):
                continue

            # Validate price (EXP-29). `price_usd` is the same field under the name x402 sellers
            # use (mach402.dev lists every tool that way); read as absent, a $0.02 tool was
            # indexed at the $0.35 default — a price the seller never asked for.
            raw_price = tool.get("price_per_call_usd")
            if raw_price is None:
                raw_price = tool.get("price_usd")
            try:
                if isinstance(raw_price, bool):
                    raise ValueError("boolean price")
                price = float(0.35 if raw_price is None else raw_price)
            except (TypeError, ValueError, OverflowError):
                logger.warning("Skipping tool %s: invalid price", tool.get("capability_id", "?"))
                continue
            if not math.isfinite(price) or price < MIN_PRICE_USD or price > MAX_PRICE_USD:
                logger.warning(
                    "Skipping tool %s: price %.2f out of range [%.2f, %.2f]",
                    tool.get("capability_id", "?"), price, MIN_PRICE_USD, MAX_PRICE_USD,
                )
                continue

            # Validate latency
            raw_latency = tool.get("p50_latency_ms", 3000)
            try:
                latency_f = 3000.0 if isinstance(raw_latency, bool) else float(raw_latency)
            except (TypeError, ValueError, OverflowError):
                latency_f = 3000.0
            if not math.isfinite(latency_f):  # NaN, ±inf, 1e999: one bad field must not stop the index
                latency_f = 3000.0
            latency = int(max(MIN_LATENCY_MS, min(MAX_LATENCY_MS, round(latency_f))))
            # 0 means "unknown" to ranking (scored like a 1 s p50). A peer that MEASURED a
            # sub-millisecond handler rounds to 0 too, and was ranked as unknown: GAIA's
            # weather relay lost "weather in Berlin" to slower siblings on exactly this.
            try:
                observed_f = float(tool.get("calls_observed") or 0)
                observed = int(observed_f) if math.isfinite(observed_f) else 0
            except (TypeError, ValueError, OverflowError):
                observed = 0
            if latency == 0 and (tool.get("metrics_source") == "measured" or observed > 0):
                latency = 1

            # Ignore peer-declared success_rate — we compute it ourselves from
            # observed invocations. Trusting peer-declared values lets a malicious
            # peer claim 99% trust and dominate routing on first index (NEW-7).
            # Start at a neutral baseline; trust_scorer will update over time.
            success = 0.5

            # A tool sold at its own URL on the peer (no capability_id, a same-origin POST
            # endpoint): routed calls go there. Such a seller names no product either, and an
            # invoke needs one of two characters or more, so its listing is filed under the
            # peer's host — otherwise it was indexed but could never be bought.
            peer_endpoint = _safe_tool_endpoint(tool, base_url)
            product_id = tool.get("product_id", "")
            if peer_endpoint and not str(product_id or "").strip():
                product_id = (urlparse(base_url).hostname or "").lower()

            cap = Capability(
                capability_id=tool.get("capability_id", tool.get("name", "")),
                product_id=product_id,
                name=tool.get("name", tool.get("capability_id", "")),
                version="v1",
                description=tool.get("description", ""),
                input_schema=tool.get("input_schema", {}),
                output_schema=tool.get("output_schema", {}),
                price_per_call_usd=price,
                p50_latency_ms=latency,
                success_rate_30d=success,
                source_hub=base_url,
                source_hub_name=hub_name,
                routed_price_usd=self._routed_price(price),
                routing_fee_bps=self.config.routing_fee_bps,
                trust_score=0.5,
                # Preserve the peer's seller attribution when it has one.  The peer's
                # signed manifest authenticates the statement; an absent legacy value
                # stays absent instead of being invented by this router.
                publisher_id=str(tool.get("publisher_id") or tool.get("provider_id") or "").strip(),
                payout_address=str(tool.get("payout_address") or tool.get("pay_to") or "").strip(),
                # The key the seller signs its own answers and receipts with, as the peer's signed
                # manifest states it: what lets a buyer's delivery receipt be tied to this
                # listing (deliveries.py). Not a routing input; a malformed one is dropped.
                provider_pubkey=_provider_pubkey(tool.get("provider_pubkey")),
                peer_endpoint=peer_endpoint,
                catalogue_evidence=dict(evidence or {}),
            )
            self.db.upsert_capability(cap)
            self._indexed_now.add((cap.product_id, cap.capability_id))
            count += 1
        return count

    def _prune_unlisted(self, base_url: str) -> int:
        """Drop rows this peer no longer lists.

        The crawl upserts and never deleted, so a capability a peer stopped advertising —
        or one this hub should never have taken from it in the first place — stayed in the
        catalogue for good. Live consequence: after re-exported rows stopped being indexed,
        the 96 copies of our own ATLAS and GAIA that had arrived through a peer's manifest
        were still being served, because nothing removes what nothing rewrites.

        Per peer, and only after that peer answered: a hub that failed this cycle keeps its
        catalogue instead of being emptied by somebody else's outage — which is exactly the
        empty-catalogue window the "clear before crawl" logic was removed to close.
        """
        removed = 0
        try:
            existing = self.db.list_capabilities(source_hub=base_url, limit=1000)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("prune: could not list %s capabilities: %s", base_url, exc)
            return 0
        for cap in existing:
            if (cap.product_id, cap.capability_id) in self._indexed_now:
                continue
            with contextlib.suppress(Exception):
                removed += self.db.delete_capability(cap.capability_id, source_hub=base_url)
        if removed:
            logger.info("prune: dropped %d row(s) %s no longer lists", removed, base_url)
        return removed

    def _routed_price(self, base_price: float) -> float:
        # Integer MICRO-dollars, not cents, to avoid IEEE 754 drift at the prices the
        # catalogue actually carries: $0.001 sensor reads and $0.004 oracle calls.
        # Quantising to whole cents published every one of those as a routed price of
        # $0.00 — free, for capabilities this hub then bills the peer's price for — and
        # it swallowed the routing fee on anything under about $0.50, since 100 bps of
        # 35 cents rounds to zero cents. Micros are one order finer than the smallest
        # listed price, so the published number is the number.
        micros = round(base_price * 1_000_000)
        routed_micros = round(micros * (1 + self.config.routing_fee_bps / 10000))
        return routed_micros / 1_000_000

    def _manifest_too_stale(self, manifest: dict[str, Any]) -> bool:
        """True if the manifest's signed `generated_at` is older than the
        configured max age (replay) or implausibly far in the future (clock
        spoof). Lenient: a missing/unparseable timestamp or disabled limit
        returns False so well-formed live peers are never rejected."""
        max_age = getattr(self.config, "manifest_max_age_s", 0) or 0
        if max_age <= 0:
            return False
        raw = manifest.get("generated_at")
        if not isinstance(raw, str) or not raw:
            return False
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > max_age or age < -3600

    def _extract_peer_urls(
        self, well_known: dict[str, Any], *, include_observed: bool = False,
    ) -> list[str]:
        """Extract peer origins, optionally including quarantined gossip.

        Callers set ``include_observed`` only after the source Hub's pinned identity
        was verified. An unknown Hub cannot use this crawler as a URL-laundering relay.
        """
        urls: list[str] = []
        peers = well_known.get("peers") or []
        for p in peers:
            if isinstance(p, dict) and p.get("url"):
                urls.append(p["url"])
                wk_url = p.get("well_known_url")
                if isinstance(wk_url, str) and wk_url.endswith(DRAFT_WELL_KNOWN_PATH):
                    # Bounded: a trusted peer's document is still a document somebody else
                    # wrote, and this map lives as long as the crawler does.
                    if len(self._peer_discovery_urls) >= _PEER_DISCOVERY_URLS_MAX:
                        self._peer_discovery_urls.clear()
                    self._peer_discovery_urls[str(p["url"]).rstrip("/")] = wk_url
        if include_observed:
            observations = well_known.get("observed_hubs") or []
            limit = self.config.federation_gossip_max_observed
            for item in observations[:limit]:
                if not isinstance(item, dict) or item.get("status") != "observed":
                    continue
                value = item.get("url")
                if isinstance(value, str) and value not in urls:
                    urls.append(value.rstrip("/"))
        # Also crawl seed list entries from the federation block
        federation = well_known.get("federation") or {}
        seed_list = federation.get("seed_list") or []
        for s in seed_list:
            if isinstance(s, str) and s not in urls:
                urls.append(s.rsplit("/.well-known/", 1)[0])
        return urls

    def _well_known_gossip_verified(
        self, well_known: dict[str, Any], advertised_key: str,
    ) -> bool:
        """Verify the full discovery document before relaying its observations.

        This is authentication of a statement, not trust in the speaker. A new Hub
        may say "I observed X" and have that statement propagate, but neither it nor X
        gains catalogue, routing or payment privileges from doing so.
        """
        signature = well_known.get("signature")
        if not advertised_key or not isinstance(signature, dict):
            return False
        if signature.get("algorithm") != "ed25519":
            return False
        sig_key = signature.get("public_key")
        if sig_key and sig_key != advertised_key:
            return False
        value = signature.get("value")
        if not isinstance(value, str) or not value:
            return False
        return self.signer.verify(
            advertised_key, value, self.signer.object_canonical(well_known),
        )

    async def close(self) -> None:
        await self._http.aclose()
