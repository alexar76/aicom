"""The realm seal — UNI is a sealed bubble, and nothing inside it can reach a real chain.

UNI is not "crypto off". It is a parallel chain of our own (Anvil, chain id 31337, our
contracts, a USD-pegged token funded from nowhere) whose whole point is that from inside it
behaves exactly like the live economy: real signatures, real contracts, real escrow, real
slashing, real receipts. Two properties follow, and only one of them is achievable by
wishing:

**No escape (absolute, enforced here).** Nothing configured inside UNI may name a real
chain, a real contract, a real token or a public RPC. This is not a convention — every one
of those was a live leak before this module existed:

* ``chain_net`` defaults ``base`` to real public RPC endpoints AND auto-loads
  ``deployments/base-mainnet.json``, so a hub told "you are on base" inside a bubble read
  and wrote against Base mainnet addresses over the public internet;
* the x402 asset table hard-codes the REAL Base USDC contract and ``eip155:8453``, so a
  402 issued inside the bubble handed every participant a payment offer valid on mainnet.
  An agent inside with a funded real key could sign it, and that signature settles on Base.
  That is money leaving the bubble, which is the exact thing that must be impossible.

**Indistinguishability (behavioural, and stated honestly).** Display names, API shapes,
receipts and flows are identical to LIVE — nothing in any public payload says "uni". What
cannot be hidden is ``chainId``: a participant who signs anything needs it, because it is
inside the EIP-712 domain separator. So an inside agent can always *read* which chain it is
on; what it can never do is act outside. Claiming otherwise would be a lie told by
software, and the seal is worth more than the illusion.

The same separator is what makes the two realms non-interchangeable in both directions: a
signature made for 31337 is invalid on 8453 and vice versa. The seal is belt and braces on
top of that arithmetic, for the parts that are not signed — RPC hosts, contract addresses,
token identities.

Default realm is ``live``, so an existing deployment behaves exactly as before.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

LIVE = "live"
UNI = "uni"

DEFAULT_UNI_CHAIN_ID = 31337

#: Chain ids that are ONLY ever a private chain. A live realm that names one is misconfigured.
PRIVATE_CHAIN_IDS = frozenset({31337, 1337, 31338})

#: Contracts and tokens that exist on real chains. Naming any of them inside UNI is an escape
#: attempt, whether deliberate or a copy-paste. Kept as a lowercase set of addresses.
_REAL_ASSETS: frozenset[str] = frozenset(
    a.lower() for a in (
        # Base mainnet USDC — the one the x402 asset table advertises by default.
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        # Base Sepolia USDC: a public testnet is still outside the bubble.
        "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        # Ethereum mainnet USDC / USDT.
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xdac17f958d2ee523a2206206994597c13d831ec7",
    )
)


def realm() -> str:
    """``live`` (default) or ``uni``."""
    value = os.getenv("AIMARKET_CHAIN_REALM", LIVE).strip().lower()
    return UNI if value in (UNI, "bubble", "virtual") else LIVE


def is_uni() -> bool:
    return realm() == UNI


def uni_chain_id() -> int:
    try:
        return int(os.getenv("AIMARKET_UNI_CHAIN_ID", str(DEFAULT_UNI_CHAIN_ID)))
    except (TypeError, ValueError):
        return DEFAULT_UNI_CHAIN_ID


class RealmBreach(RuntimeError):
    """A configuration that would let the bubble reach a real chain, or the reverse.

    Raised at startup rather than logged: a hub that has already answered one request with
    a mainnet payment offer cannot un-answer it.
    """


def is_private_host(host: str) -> bool:
    """Is this a host that cannot be a public chain endpoint?

    Loopback, private ranges, link-local, and the container-gateway names the UNI stack
    actually uses (``host.docker.internal``, ``anvil``, plain ``localhost``).
    """
    h = (host or "").strip().lower().strip("[]")
    if not h:
        return False
    if h in ("localhost", "host.docker.internal", "anvil", "hardhat", "chain", "uni-chain"):
        return True
    if h.endswith((".localhost", ".internal", ".local")):
        return True
    try:
        addr = ipaddress.ip_address(h)
    except ValueError:
        return False
    return bool(
        addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified
    )


def is_private_rpc(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https", "ws", "wss"):
        return False
    return is_private_host(parsed.hostname or "")


def names_real_asset(address: str) -> bool:
    return str(address or "").strip().lower() in _REAL_ASSETS


def check_rpc(url: str) -> None:
    """Refuse an RPC endpoint that does not belong to this realm."""
    if not str(url or "").strip():
        return
    private = is_private_rpc(url)
    if is_uni() and not private:
        raise RealmBreach(
            f"UNI realm cannot use the public RPC {urlparse(url).hostname!r} — the bubble "
            "must not reach a real chain. Point AIMARKET_RPC_* at the private node."
        )
    if not is_uni() and private:
        raise RealmBreach(
            f"live realm refuses the private RPC {urlparse(url).hostname!r} — a live hub "
            "reading a simulated chain would report simulated money as real. Set "
            "AIMARKET_CHAIN_REALM=uni if this deployment IS the bubble."
        )


def check_chain_id(chain_id: int | None) -> None:
    if chain_id is None:
        return
    private = int(chain_id) in PRIVATE_CHAIN_IDS
    if is_uni() and not private:
        raise RealmBreach(
            f"UNI realm cannot run on chain id {chain_id} — that is a real network. "
            f"Use AIMARKET_UNI_CHAIN_ID (default {DEFAULT_UNI_CHAIN_ID})."
        )
    if not is_uni() and private:
        raise RealmBreach(
            f"live realm cannot run on chain id {chain_id} — that is a private chain. "
            "Set AIMARKET_CHAIN_REALM=uni for the bubble."
        )


def check_addresses(addresses: dict[str, str]) -> None:
    """Refuse a real token/contract address inside the bubble."""
    if not is_uni():
        return
    for name, addr in (addresses or {}).items():
        if names_real_asset(addr):
            raise RealmBreach(
                f"UNI realm names the real asset {addr} as {name!r}. Deploy the bubble's own "
                f"token and set AIMARKET_ADDR_<NET>_{name.upper()}."
            )


def assert_sealed(*, chain_id: int | None, rpc_urls: tuple[str, ...] | list[str],
                  addresses: dict[str, str] | None = None) -> None:
    """One call, at startup, over everything the realm could leak through."""
    check_chain_id(chain_id)
    for url in rpc_urls or ():
        check_rpc(url)
    check_addresses(addresses or {})


# ── federation: the bubble may only federate with the bubble ──────────────────────
#
# The chain seal above was never the only way out. `federation_seeds.json` ships in the image
# with the SIX REAL satellites and their pinned public keys, and `_parse_seed_list` falls back
# to that file whenever `AIMARKET_SEED_LIST` is empty — which is what the bubble was deployed
# with. Two consequences, both live:
#
#   * the bubble PUBLISHED the real ecosystem's hostnames in its own
#     `/.well-known/ai-market.json` under `federation.seed_list`. An agent inside the bubble
#     could read the exact addresses of the world outside it. That is a door in the wall.
#   * a single operator crawl would have indexed real, outside-reachable, priced endpoints
#     into the bubble's catalogue, and those seed keys are pinned for trusted-on-first-contact
#     indexing — so no approval step would have stood in the way. A bubble invoke would then
#     have routed real money to a real provider.
#
# Hence: inside UNI the committed seed file is DROPPED, not filtered — it is the live
# ecosystem's address book and nothing in it can ever be inside a bubble — and an explicitly
# configured seed must name a host the bubble itself answers on.


def _host_of(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower()
    except ValueError:
        return ""


def federation_hosts() -> frozenset[str]:
    """Hosts the bubble's federation may reach.

    The hub's own host is always allowed: a bubble satellite lives behind the same name as
    the bubble hub (`uni.modelmarket.dev/sat/<name>`), which is also what lets it pass the
    crawler's private-address guard without weakening that guard for anyone.
    """
    hosts = {_host_of(os.getenv("AIMARKET_HUB_URL", ""))}
    for extra in os.getenv("AIMARKET_UNI_FEDERATION_HOSTS", "").split(","):
        host = _host_of(extra.strip())
        if host:
            hosts.add(host)
    return frozenset(h for h in hosts if h)


def seed_file_entries(entries: list[dict]) -> list[dict]:
    """Drop the committed seed file inside the bubble, keys and all."""
    if not is_uni():
        return entries
    if entries:
        logger.info(
            "UNI realm: dropping %d committed federation seed(s) — the seed file names the "
            "live ecosystem, which is outside the bubble.", len(entries),
        )
    return []


def check_seed(url: str) -> None:
    """Refuse a federation seed that points out of the realm — in both directions."""
    host = _host_of(url)
    if not host:
        raise RealmBreach(f"federation seed {url!r} has no host")
    if is_uni():
        allowed = federation_hosts()
        if not allowed:
            raise RealmBreach(
                f"UNI realm cannot validate the federation seed {url!r}: set "
                "AIMARKET_HUB_URL to the bubble's own name (and optionally "
                "AIMARKET_UNI_FEDERATION_HOSTS) so the seal knows what is inside."
            )
        if host not in allowed:
            raise RealmBreach(
                f"UNI realm names the outside host {host!r} as a federation seed. The bubble "
                f"may only federate with itself — allowed: {', '.join(sorted(allowed))}."
            )
        return
    # Symmetric: a live hub that seeds a private address would publish an unreachable
    # internal name to every peer that reads its well-known, and a live hub reading a
    # simulated peer would report simulated capabilities as real stock.
    if is_private_host(host):
        raise RealmBreach(
            f"live realm names the private host {host!r} as a federation seed. Set "
            "AIMARKET_CHAIN_REALM=uni for a sealed deployment."
        )


def assert_seeds_sealed(seeds: list[str]) -> None:
    for url in seeds or ():
        check_seed(url)


# The seed list is only one of the doors. A peer also arrives by knocking
# (`/federation/announce`, open or admin), by crawling us (the inbound-crawl note), by being
# named in a crawled peer's well-known (gossip), and from the pending and refresh queues. On
# 2026-09-23 HISTOR announced itself to the bubble through the open door, passed the assay,
# and was auto-admitted: three live-world capabilities sat in the UNI catalogue for ten days,
# and every bubble invoke of them went out to histor.modelmarket.dev. `check_seed` was never
# consulted, because nothing on that path is a seed.

def peer_inside(url: str) -> bool:
    """May this hub federate with ``url``? Always true outside UNI.

    Inside UNI the answer is the same one `check_seed` gives — a host the bubble itself
    answers on — but as a predicate, for the doors that must refuse quietly per request
    rather than refuse to start.
    """
    if not is_uni():
        return True
    host = _host_of(url)
    return bool(host) and host in federation_hosts()


def evict_outside_peers(db: object) -> list[str]:
    """Drop every peer row, and every listing it left, that names a host outside the bubble.

    Run at startup inside UNI: the doors above stop new arrivals, this removes what arrived
    before they were shut. Dropped, not quarantined — a pending row is still a URL the
    crawler dials. A no-op in a live realm.
    """
    if not is_uni():
        return []
    evicted: list[str] = []
    for peer in list(db.list_peers()):
        url = str(getattr(peer, "url", "") or "")
        if not url or peer_inside(url):
            continue
        for cap in db.list_capabilities(source_hub=url, limit=10000):
            db.delete_capability(cap.capability_id, source_hub=url)
        db.delete_peer(url)
        evicted.append(url)
    if evicted:
        logger.warning(
            "UNI realm: evicted %d federation peer(s) outside the bubble, with their "
            "listings: %s", len(evicted), ", ".join(evicted),
        )
    return evicted


def describe() -> dict[str, object]:
    """Operator-facing only.

    Deliberately NOT part of any public payload: the bubble must look like the real thing
    from inside, so this is for logs and admin routes, where the reader is outside it.
    """
    return {
        "realm": realm(),
        "sealed": is_uni(),
        "chain_id": uni_chain_id() if is_uni() else None,
        "note": (
            "simulated economy — every amount here is virtual and must never be reported "
            "as revenue"
        ) if is_uni() else "live economy",
    }
