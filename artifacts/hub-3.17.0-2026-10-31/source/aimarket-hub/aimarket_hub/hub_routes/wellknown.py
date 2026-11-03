"""Discovery documents: /.well-known, x402 bazaar discovery and the protocol's JSON schemas."""

from __future__ import annotations

import contextlib
import json
import os
import time
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from aimarket_hub import (
    card_topup,
    contracts_declaration,
    credits,
    deposit_watch,
    mandates,
    realm,
    settle,
    subcontract,
    topup,
    verified_settlement,
    x402,
)
from aimarket_hub.channels import payment_readiness
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.deposit_watch import DepositStore
from aimarket_hub.discovery_names import (
    DRAFT_WELL_KNOWN_PATH,
    LEGACY_WELL_KNOWN_PATH,
    draft_discovery_document,
)
from aimarket_hub.models import Peer
from aimarket_hub.plugin import PluginRegistry
from aimarket_hub.public_cache import PublicDocumentCache
from aimarket_hub.sandbox_trials import trial_policy
from aimarket_hub.signing import Signer
from aimarket_hub.paging import page_limit


# Bazaar discovery resources: the default page and the most one request may read.
DISCOVERY_PAGE = 20
DISCOVERY_PAGE_MAX = 100


def register(
    *,
    _AGENT_TOKENS: dict[str, str],
    config: HubConfig,
    db: HubDatabase,
    hub_deposits: DepositStore,
    late: SimpleNamespace,
    plugins: PluginRegistry,
    signer: Signer,
    wellknown_router: APIRouter,
) -> None:
    """Attach the well-known and schema routes to ``wellknown_router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _catalogue_snapshot,
        _inbound_pool,
        logger,
    )

    # ── .well-known ────────────────────────────────────────────

    def _note_inbound_federation(crawler_hub: str, user_agent: str) -> None:
        """Record and quarantine as PENDING a public hub that crawled us.

        Federation was one-way blind: a peer could index this hub, route buyers to
        it and appear in its own catalogue, while this hub had no idea the peer
        existed. The crawler has always sent ``X-AIMarket-Crawler: <its hub url>``;
        nothing ever read it. Now we do.

        Runs off the request path (see the caller) because the SSRF-safe URL check
        resolves DNS, which must never be on the hot path of a document every peer
        in the network fetches on a timer. Fails silently by design: discovery is a
        courtesy, and no failure of it may affect serving ``.well-known``.
        """
        try:
            from aimarket_hub.crawler import _url_is_safe

            url = (crawler_hub or "").strip()
            if not url or len(url) > 300 or any(c in url for c in "\r\n\t"):
                return
            if not url.startswith(("http://", "https://")):
                return
            url = url.rstrip("/")

            # Recording is syntactic-only and capped. Noting that a hub reads us costs
            # nothing and is useful even when its DNS is broken or its host is down;
            # gating the note on a name resolving would have hidden exactly the peers
            # an operator most wants to hear about.
            db.record_inbound_federation(url, user_agent)

            if db.get_peer(url) is not None:
                return
            if not realm.peer_inside(url):
                return
            # Admission is different: a pending peer is a URL the crawler will later
            # fetch, so it passes the same DNS-resolving SSRF check as a seed. Done
            # here, once per never-before-seen hub, and never on the response path.
            if not _url_is_safe(url):
                logger.debug("Inbound crawler %s not admitted — URL failed safety check", url[:60])
                return
            outcome = db.announce_peer(
                Peer(
                    url=url,
                    name=url,
                    well_known_url=f"{url}/.well-known/ai-market.json",
                    depth=1,
                    discoverer="inbound-crawl",
                ),
                max_pending=late._pending_peer_cap(),
            )
            if outcome == "added":
                logger.info(
                    "Open federation: %s crawled us and was recorded as PENDING. "
                    "It is visible to the operator and indexed by nothing until approved.",
                    url,
                )
        except Exception as exc:  # pragma: no cover - never break .well-known
            logger.debug("inbound federation note failed: %s", exc)

    # Every protocol schema declares an absolute `$id` under /schemas/. Until now nothing
    # served that path, so a validator that dereferenced `$id` — which is what `$id` is for —
    # got a 404, and `$ref` between schemas could not resolve at all. Serving them here makes
    # the identifier true. The `$id` values stay canonical (modelmarket.dev) on every mirror,
    # which is correct JSON Schema semantics: identity is a name, not a location.
    _SCHEMA_FILES = frozenset({
        "well-known.json", "manifest.json", "receipt.json",
        "federation-announce.json", "provenance-receipt.json",
    })

    @wellknown_router.get("/discovery/resources")
    async def bazaar_discovery(type: str = "http", limit: int = 20, offset: int = 0):
        """A Bazaar-compatible discovery index of what this hub sells.

        The x402 Bazaar is not a registry anyone registers with — it is a per-facilitator
        index, and its specification says in as many words that any facilitator may run its
        own. Serving this envelope means every official x402 SDK can enumerate this hub's
        catalogue with no code changes: point a facilitator client at this host and call
        `listResources`.

        That matters more than one endpoint usually does. Each existing Bazaar catalogues
        only what its own facilitator settles, and they do not federate — Coinbase's index
        and PayAI's share no entries at all. An index that can be crawled by others is the
        one thing that turns a set of disjoint catalogues back into a market, which is what
        this protocol is for.

        Public and unauthenticated by design. SDK clients attach auth headers on their way
        in; a public index ignores them rather than rejecting the request.
        """
        limit = page_limit(limit, default=DISCOVERY_PAGE, maximum=DISCOVERY_PAGE_MAX)
        offset = max(0, int(offset or 0))
        if (type or "http").lower() != "http":
            # Only HTTP-invocable capabilities are advertised. Claiming an "mcp" type here
            # would promise a tool surface each capability does not individually expose.
            return {"x402Version": 2, "items": [],
                    "pagination": {"limit": limit, "offset": offset, "total": 0}}

        from aimarket_hub import x402

        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        priced = [
            c for c in _catalogue_snapshot(db, config)
            if float(getattr(c, "price_per_call_usd", 0) or 0) > 0
        ]
        window = priced[offset:offset + limit]
        items = [i for i in (x402.bazaar_item(c, config.hub_url, stamp) for c in window) if i]
        return {
            "x402Version": 2,
            "items": items,
            "pagination": {"limit": limit, "offset": offset, "total": len(priced)},
        }

    @wellknown_router.get("/schemas/{filename}")
    async def protocol_schema(filename: str):
        # Allow-list, not sanitisation: this handler reads from disk by a name taken from the
        # URL, and a deny-list of traversal tricks is a game you eventually lose.
        if filename not in _SCHEMA_FILES:
            raise HTTPException(status_code=404, detail="unknown schema")
        from aimarket_hub.validator import _SCHEMA_DIR

        path = _SCHEMA_DIR / filename
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Schemas are not bundled with this deployment. Set AIMARKET_SCHEMA_DIR "
                    "to a checkout of aimarket-protocol/schemas."
                ),
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="schema unreadable")
        return JSONResponse(
            payload,
            media_type="application/schema+json",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @wellknown_router.get("/schemas")
    async def protocol_schema_index():
        return {
            "schemas": sorted(_SCHEMA_FILES),
            "base": f"{config.hub_url.rstrip('/')}/schemas/",
            "canonical_note": (
                "Each document's own $id is its canonical identifier and does not change "
                "when mirrored by another hub."
            ),
        }

    # The document is the same for every caller and costs a catalogue scan plus a
    # full-document signature (0.3-0.5 s on a crowded host), so it is built once per TTL in
    # a worker thread. On 2026-10-16 building it on the event loop for a monitor that asked
    # every 1.5 s left /health queued until hub.attestedmemory.net went down. `generated_at`
    # is therefore up to a TTL old; it is inside the signature, so it stays honest.
    _well_known_cache = PublicDocumentCache("AIMARKET_WELL_KNOWN_CACHE_S", 60.0)

    def _note_crawler(x_aimarket_crawler: str, agent_marketplace_crawler: str, user_agent: str) -> None:
        """Hand an inbound crawler's self-declared URL to the off-path recorder.

        Two spellings of one header: ``X-AIMarket-Crawler`` (what every peer sends today)
        and ``Agent-Marketplace-Crawler`` (the Internet-Draft's name, RFC 6648 — no
        ``X-``). Our own crawler sends both; a draft-only implementation sends the second.
        When both arrive, the legacy one wins, since that is the value peers have always
        been identified by.
        """
        crawler_hub = x_aimarket_crawler or agent_marketplace_crawler
        if crawler_hub:
            # Off the response path: a peer's discovery must not cost us latency.
            #
            # Deliberately NOT asyncio's default executor. The work below calls
            # getaddrinfo, which blocks, and the default pool is the same one asyncio uses
            # for its own DNS — an unauthenticated header could therefore starve the event
            # loop's name resolution. A single dedicated worker bounds the damage to this
            # feature, and a full queue drops the note rather than queueing unboundedly.
            with contextlib.suppress(Exception):
                pool = _inbound_pool()
                if pool._work_queue.qsize() < 32:  # noqa: SLF001 - bounded backlog
                    pool.submit(
                        _note_inbound_federation, crawler_hub, user_agent
                    )

    @wellknown_router.api_route(LEGACY_WELL_KNOWN_PATH, methods=["GET", "HEAD"])
    async def well_known(
        x_aimarket_crawler: str = Header(default=""),
        agent_marketplace_crawler: str = Header(default=""),
        user_agent: str = Header(default=""),
    ):
        _note_crawler(x_aimarket_crawler, agent_marketplace_crawler, user_agent)
        # HEAD must succeed (Allow: GET alone → 405). Same payload as GET;
        # Starlette/FastAPI omit the body for HEAD automatically.
        return await run_in_threadpool(
            _well_known_cache.get, "document", _build_well_known
        )

    @wellknown_router.api_route(DRAFT_WELL_KNOWN_PATH, methods=["GET", "HEAD"])
    async def well_known_draft(
        x_aimarket_crawler: str = Header(default=""),
        agent_marketplace_crawler: str = Header(default=""),
        user_agent: str = Header(default=""),
    ):
        """The discovery document under the Internet-Draft's name and member names.

        Same key, same catalogue, same counts as ``/.well-known/ai-market.json`` — it is
        built from that document, so the two cannot disagree. ``peers`` is the list of
        discovery-document URIs this hub actually reads for its admitted peers; the
        legacy document keeps the richer per-peer objects. Served alongside the legacy
        path, not instead of it: no peer reads this one yet.
        """
        _note_crawler(x_aimarket_crawler, agent_marketplace_crawler, user_agent)
        return await run_in_threadpool(
            _well_known_cache.get, "agent-marketplace", _build_well_known_draft
        )

    def _build_well_known_draft() -> dict[str, Any]:
        # Built directly, NOT through the cache: this function already runs under the
        # cache's lock (for the "agent-marketplace" key), and PublicDocumentCache's lock is
        # not re-entrant. Asking the cache for "document" from in here deadlocked the first
        # request to the draft path on a cold cache — and every well-known request after
        # it, on both paths, until a restart (uni + attested, 2026-10-30 04:40Z).
        legacy = _build_well_known()
        discovery_urls = [
            p.well_known_url or f"{p.url.rstrip('/')}{LEGACY_WELL_KNOWN_PATH}"
            for p in db.list_peers()
        ]
        return draft_discovery_document({**legacy, "hub_url": config.hub_url}, discovery_urls)

    def _build_well_known() -> dict[str, Any]:
        peers = []
        for p in db.list_peers():
            entry = {
                "url": p.url,
                "name": p.name,
                "capabilities_count": p.capabilities_count,
                "last_crawl": p.last_crawl,
                "trust_score": p.trust_score,
                "categories": p.categories,
            }
            # What the peer says it has ON CHAIN, re-exported as it declared it. A reader
            # two hops away cannot fetch this peer (that is what bounds a cyclic
            # federation), so without the re-export a stranger hub is a name and a number
            # — and its escrow, the one thing about it anyone can independently check, is
            # invisible. Re-exported only; never merged with our own declaration, and
            # bounded at crawl time (contracts_declaration.sanitize).
            if p.declared_contracts:
                entry["contracts"] = p.declared_contracts
            peers.append(entry)

        # The observation layer is deliberately separate from `peers`.  It makes the
        # network eventually aware of every public Hub seen by a member, while preserving
        # the hard line between "an address exists" and "this Hub may sell/rout here".
        # The whole well-known document is signed below, so a crawler can attribute the
        # observation to this Hub; it must still quarantine the observed address.
        observed_hubs = []
        for p in late._publishable_pending_peers(db)[: config.federation_gossip_max_observed]:
            observed_hubs.append({
                "url": p.url,
                "name": p.name or p.url,
                "first_seen": p.first_seen,
                "observed_by": config.hub_url,
                "depth": max(1, int(p.depth or 1)),
                "status": "observed",
            })

        # x402 sellers this hub lists by observation, with their consent (spec §2.7). Under
        # this hub's signature as THIS hub's observation — never a seller's — and with no
        # routes: a crawler that wants them reads the listing, and re-lists nothing.
        observed_sellers_wk = []
        with contextlib.suppress(Exception):
            from aimarket_hub import observed_sellers as _observed

            if _observed.enabled():
                for seller in db.list_observed_sellers():
                    served = _observed.served_routes([seller], hub_url=config.hub_url)
                    if not served:
                        continue
                    observed_sellers_wk.append({
                        "origin": seller["origin"],
                        "name": seller.get("name") or seller["origin"],
                        "routes_served": len(served),
                        "observed_at": seller.get("observed_at") or "",
                        "observed_by": config.hub_url,
                        "status": "observed",
                    })

        erc8004 = None
        with contextlib.suppress(Exception):
            from aimarket_hub import x402 as _x402

            erc8004 = _x402.erc8004_declaration(config.hub_url)

        public_caps = _catalogue_snapshot(db, config)
        public_local = [c for c in public_caps if (c.source_hub or "local") == "local"]
        # A Hub may have its own provider ecosystem.  Keep that topology separate from
        # federation `peers`: a locally published KOVA/AEGIS service is our child node, not
        # an independently trusted Hub.  The complete well-known document is signed below,
        # so another Monitor can draw this declaration without granting it routing trust.
        ecosystem_labels: dict[str, str] = {}
        for raw_label in os.environ.get("AIMARKET_ECOSYSTEM_LABELS", "").split(","):
            publisher, separator, display = raw_label.partition(":")
            if separator and publisher.strip() and display.strip():
                ecosystem_labels[publisher.strip()] = display.strip()[:80]
        # Where each provider can be REACHED, when that differs from where this hub calls
        # it. A provider is usually registered with the address the hub itself dials — a
        # compose hostname on a single-host deploy — and that address is meaningless to
        # everyone else: `hub.attestedmemory.net` published Memory Market, Truth Layer and
        # Provenance Ledger as `http://memory-market:8810` and friends, so every monitor
        # drew three nodes with no usable link. There was a way to set their NAMES
        # (AIMARKET_ECOSYSTEM_LABELS) and no way to set their addresses.
        #
        #   AIMARKET_ECOSYSTEM_URLS=memory-market=https://memory.example,truth-layer=https://truth.example
        #
        # `=` separates, not `:`, because the value is a URL and contains colons.
        ecosystem_urls: dict[str, str] = {}
        for raw_url in os.environ.get("AIMARKET_ECOSYSTEM_URLS", "").split(","):
            publisher, separator, address = raw_url.partition("=")
            address = address.strip()
            if separator and publisher.strip() and address.startswith(("http://", "https://")):
                ecosystem_urls[publisher.strip()] = address.rstrip("/")[:300]
        ecosystem_by_publisher: dict[str, dict[str, Any]] = {}
        for c in public_local:
            publisher_id = str(c.publisher_id or "").strip()
            if not publisher_id:
                continue
            item = ecosystem_by_publisher.setdefault(publisher_id, {
                "id": publisher_id,
                "name": ecosystem_labels.get(publisher_id) or (
                    str(c.source_hub_name or publisher_id).strip() or publisher_id
                ),
                "role": "provider",
                "url": "",
                "capabilities_count": 0,
                "categories": set(),
            })
            item["capabilities_count"] += 1
            category = str(getattr(c, "category", "") or "").strip()
            if category:
                item["categories"].add(category)
            declared = ecosystem_urls.get(publisher_id, "")
            if declared:
                # The operator has said where this provider actually lives; that wins over
                # anything derivable from how the hub happens to dial it.
                item["url"] = declared
                continue
            invoke_url = str(c.invoke_url or "").strip()
            if invoke_url and not item["url"]:
                # Provider manifests use /capabilities/<product>/<capability>/invoke.  The
                # prefix is the human/API address of the node and contains no secret.
                address = invoke_url.split("/capabilities/", 1)[0].rstrip("/")
                # A self-published provider registers a bare `…/invoke` with no
                # `/capabilities/` in it, so the split above returned the ENDPOINT as the
                # node address — `http://172.17.0.1:9195/invoke` on the UNI hub. Trim it.
                if address.endswith("/invoke"):
                    address = address[: -len("/invoke")].rstrip("/")
                item["url"] = address
        ecosystem_nodes = []
        for item in ecosystem_by_publisher.values():
            item["categories"] = sorted(item["categories"])
            ecosystem_nodes.append(item)
        ecosystem_nodes.sort(key=lambda item: item["id"])
        # Configuration readiness is necessary but not sufficient. The live channel
        # stack also needs an RPC/token verifier and payer-signature recovery. Keeping
        # this runtime verdict in discovery prevents a missing optional dependency from
        # advertising a wallet that every channel/open will refuse.
        runtime_payment = payment_readiness()
        payment_ready = bool(
            config.payment_ready and runtime_payment.get("can_credit_channels", False)
        )
        wk = {
            "name": config.hub_name,
            **({"description": config.hub_description} if config.hub_description else {}),
            "protocol_versions": ["v1", "v2"],
            "hub_version": config.hub_version,
            "mcp_endpoint": f"{config.hub_url}/ai-market/mcp",
            # A2A 1.0 is a real, bounded marketplace-discovery facade, not just a card.
            # Both URLs are inside this signed document so a consumer of our native
            # protocol can bind the A2A surface to the same Hub identity.
            "a2a_endpoint": f"{config.hub_url}/a2a",
            "a2a_agent_card_url": f"{config.hub_url}/.well-known/agent-card.json",
            "manifest_url": f"{config.hub_url}/ai-market/v2/manifest",
            # Offerable, not stored: these three numbers are how a peer sizes us up, and
            # they must match what /v2/manifest is willing to list.
            "products_count": len({c.product_id for c in public_local}),
            "capabilities_count": len(public_local),
            "federated_capabilities_count": len(public_caps),
            "supported_chains": config.payment_chains,
            "supported_tokens": config.payment_tokens,
            # Payment recipient hidden from public manifest — exposed only when stub mode
            # `payment_ready` (not `not stub`): stub off with AIFACTORY_PROD unset skips
            # on-chain verification entirely, so the old flag could advertise payments as
            # configured on a hub that credits any tx_hash. See HubConfig.payment_readiness.
            "payment_configured": payment_ready,
            # How to pay THIS hub, in the manifest, because a price nobody can discover a
            # rail for is not an offer. `credits` needs no wallet, no chain and no contract
            # — it is the rail an operator can actually switch on — so an agent that reads
            # this knows whether it can transact here before it tries.
            "payment_rails": {
                "seller_direct": {
                    "enabled": x402.enabled() and x402.accept_enabled(),
                    "header": "X-Payment",
                    "also": ["PAYMENT-SIGNATURE", "X-PAYMENT", "X-Payment-Nonce"],
                    "asset": "USDC",
                    "note": (
                        "buyer pays the listing payout_address on-chain; "
                        "this hub verifies and never holds the money"
                    ),
                },
                "credits": {
                    "enabled": credits.enabled(),
                    "open_signup": credits.enabled() and credits.signup_open(),
                    "signup_url": f"{config.hub_url}/ai-market/v2/accounts",
                    # The same key also rides an MCP connection (X-API-Key) and pays there.
                    **({"start_url": f"{config.hub_url}/start"}
                       if credits.enabled() and credits.signup_open() else {}),
                    "header": "X-API-Key",
                    "free_grant_usd": credits.signup_grant_usd() if credits.enabled() else 0.0,
                    "min_unit_usd": 0.00001,
                    # Buying credit with USDC — how an account that is not the operator's
                    # gets money onto this rail at all (docs/credits-topup.md).
                    "topup": {**topup.well_known(),
                              "deposit_watch": deposit_watch.well_known(hub_deposits, config.hub_url)},
                    # The same credit bought with a card (Stripe Checkout) — for a person
                    # who has no wallet. Off unless the operator configures it.
                    "topup_card": card_topup.well_known(),
                },
                "channel": {
                    "enabled": payment_ready,
                    "header": "X-Payment-Channel",
                    "chains": config.payment_chains,
                },
            },
            # Published next to the price list on purpose: an agent that sees only
            # "payments configured" and a price assumes it needs a funded wallet before
            # it can find out whether a capability is any good.
            "free_trial": trial_policy(),
            "payment_testnet": config.payment_testnet,
            "signer_public_key": signer.public_key_b64,
            "federation": {
                "crawl_interval_s": config.crawl_interval_s,
                "routing_fee_bps": config.routing_fee_bps,
                "min_trust_score": config.min_trust_score,
                "seed_list": config.seed_list,
            },
            # Federation membership authenticates a Hub, not an arbitrary caller
            # claiming to be one of its agents. Advertise the standard wallet-bound
            # proof endpoint so lottery clients can discover whether their home Hub
            # can attest that second leg of identity.
            "lottery_admission": {
                "version": 1,
                "work_seat_entitlement_url": (
                    f"{config.hub_url}/ai-market/v2/lottery/work-seat-entitlement"
                ),
                "authentication": "Bearer credential for the requested agent_id",
                "participant_id": "sha256(normalized_hub_url + newline + agent_id)",
                "max_ttl_s": 600,
                # Advertise the door an AGENT can actually walk through. _ADMIN_TOKEN is
                # the operator's and can never be presented by an agent, and the shared
                # publish token is refused on this route, so neither makes it "enabled".
                "enabled": bool(_AGENT_TOKENS),
            },
            "peers": peers,
            "ecosystem": {
                "version": 1,
                "relationship": "owned-provider",
                "nodes": ecosystem_nodes,
            },
            "observed_hubs": observed_hubs,
            "observed_sellers": observed_sellers_wk,
            "observed_sellers_url": f"{config.hub_url}/ai-market/v2/federation/observed-sellers",
            "plugins_loaded": plugins.count(),
            # Loaded ≠ reachable: a plugin whose register_routes body is `pass` still counts
            # as loaded, and eight of the fifteen shipped ones are exactly that.
            "plugins_with_routes": plugins.routed_count(),
        }

        # What THIS hub has on chain: the escrow it settles through and the wallet it is
        # paid to, with the chain id and an explorer link, so "payments configured" stops
        # being a claim a reader has to buy something to check. Derived from the payment
        # config and deployment registry already in use — a hub that deploys an escrow
        # starts declaring it with no switch to flip, and one with none stays silent.
        own_contracts = contracts_declaration.own_declaration(
            config, payment_ready=payment_ready
        )
        if own_contracts:
            wk["contracts"] = own_contracts
        # Pay-on-Verified: whether a buyer can make payment conditional on a verdict here,
        # and how. Advertised as off unless a verifier is actually named.
        wk["pay_on_verified"] = verified_settlement.advertisement()

        # Agent mandates and subcontracting (aimarket-protocol/mandates.md): what a client needs
        # to know before it sends a mandate or opens an allowance — whether this hub enforces
        # them (both live on the credits rail) and the limits it applies regardless of buyer.
        credits_on_here = credits.enabled()
        wk["mandates"] = {
            "spec": "aimarket-protocol/mandates.md",
            "version": "AMD/1",
            "enabled": credits_on_here,
            "audience": config.hub_url.rstrip("/"),
            "register": "/ai-market/v2/mandates",
            "owners": "/ai-market/v2/mandates/owners",
            "revoke": "/ai-market/v2/mandates/revoke",
            "status": "/ai-market/v2/mandates/{digest}",
            "max_chain": mandates.MAX_CHAIN,
        }
        wk["subcontracting"] = {
            "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1",
            "version": "SUB/1",
            # Linkage works on any rail; the pass-through allowance needs the credits rail.
            "job_tokens": True,
            "allowance": credits_on_here,
            "max_allowance_usd": subcontract.max_allowance_usd(),
            "max_depth": subcontract.HUB_MAX_DEPTH,
            "max_nodes_per_job": subcontract.MAX_NODES_PER_JOB,
            "max_children_per_node": subcontract.MAX_CHILDREN_PER_NODE,
            "jobs": "/ai-market/v2/jobs/{job_id}",
        }
        from aimarket_hub.pipeline_distribution import metadata as client_distribution
        wk["seller_operations"] = {
            "protocol": "SELLER-OP/1", "prepare": "/ai-market/v2/operations/prepare",
            "invoke": "/ai-market/v2/operations/{operation_id}/invoke",
            "status": "/ai-market/v2/operations/{operation_id}", "auth_header": "X-Operation-Token",
            "funding": "seller_direct_eip3009", "local_listings_only": True,
            "recovery": "durable_result_at_most_once_dispatch", "uncertain_dispatch": "reconciliation_required",
            "provider_recovery_protocol": "PROVIDER-OP/1",
            "provider_recovery_requires": "operator_opt_in_and_provider_durable_signed_result",
        }
        wk["pipeline_execution"] = {
            "product_id": "hephaestus", "capability_id": "pipeline.run@v1",
            "invoke": "/ai-market/v2/invoke", "preflight": "/studio/preflight",
            "prepare": "/studio/paid-runs/{run_id}/prepare-pipeline",
            "prepare_graph": "/studio/prepare-pipeline",
            "status": "/studio/paid-runs/{run_id}/pipeline",
            "status_auth_header": "X-Studio-Run-Token",
            "mcp_tools": ["pipeline_prepare", "pipeline_invoke", "pipeline_status", "pipeline_refund_prepare", "pipeline_refund", "pipeline_refund_status"],
            "client": {"python": "aimarket_hub.pipeline_client.run_pipeline", "minimum_version": "3.9.0",
                       "cli": "aimarket-pipeline", "paid_chains": [8453, 1], "paid_token": "USDC",
                       "asset_policy": "buyer_pinned_usd_eip3009_allowlist", "single_asset_per_graph": True,
                       "wallet_coordination": ["local_files", "buyer_owned_postgresql"],
                       "advanced_client_minimum_version": "3.14.0",
                       "requires_native_gas": "unless_sponsored", "receipt_verification": True,
                       "distribution": client_distribution(),
                       "documentation": {lang: f"/clients/pipeline-guide/{lang}" for lang in ("en", "ru", "es", "fr", "zh")}},
            "settlement_routes": ["local_seller_direct", "peer_seller_of_record", "configured_peer_reseller", "independent_seller_operation"],
            "independent_peer_billing": "SELLER-OP/1",
            "quote_ttl_seconds": 900, "payment_offer_ttl_seconds": settle.invoice_ttl_s(),
            "funding": "buyer_signed_transactions", "credits_allowance": False,
            "gas_sponsorship": late.pipeline_provider.relay.describe(),
            "gas_modes": ["buyer", "auto", "required"],
            "refunds": {"protocol": "SELLER-REFUND/1", "seller_approval_required": True,
                        "prepare": "/studio/paid-runs/{run_id}/refunds/{step_id}/prepare",
                        "advance": "/studio/paid-runs/{run_id}/refunds/{step_id}",
                        "status": "/studio/paid-runs/{run_id}/refunds/{step_id}", "buyer_gas_fee_units": "0"},
            "job_linkage": "SUB/1", "max_steps": 16,
        }

        # Merge plugin manifest extensions
        plugin_ext = plugins.get_manifest_extensions()
        if plugin_ext:
            wk["plugin_extensions"] = plugin_ext

        # Advertise the agent-native MCP servers so external AI agents can discover + add them
        # (the on-chain/HTTP capabilities are also reachable as MCP tools).
        # The hosted one comes first because it is the only entry that costs a reader
        # nothing to try: the others must be installed before they can say anything.
        wk["mcp_servers"] = [
            {
                "name": "aimarket-hub",
                "transport": "streamable-http",
                "url": f"{config.hub_url}/mcp",
                "description": (
                    "This hub's marketplace as MCP tools: search the catalogue and invoke a "
                    "capability. A few trial invokes per caller with no wallet, key or install; "
                    "after that the hub answers 402."
                ),
                "tools": ["market_search", "market_invoke", "pipeline_prepare", "pipeline_invoke", "pipeline_status", "pipeline_refund_prepare", "pipeline_refund", "pipeline_refund_status"],
            },
            {
                "name": "aimarket-oracle-gateway",
                "transport": "stdio",
                "glama": "https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway",
                "description": "Verifiable oracle services (Platon VRF, Chronos VDF, LUMEN reputation) as MCP tools — pay-per-call, every result verifiable.",
                "tools": [
                    "get_random", "get_randomness_beacon", "ask_oracle", "verify_random",
                    "compute_vdf", "verify_vdf", "get_reputation_scores", "get_agent_trust",
                    "verify_reputation", "list_oracle_capabilities",
                ],
            },
            {
                "name": "aimarket-mcp-packager",
                "transport": "stdio",
                "glama": "https://glama.ai/mcp/servers/alexar76/aimarket-plugins",
                "description": "Package any AIMarket capability as a self-hosted MCP server.",
                "tools": ["package_capability", "generate_dockerfile", "generate_claude_desktop_config"],
            },
        ]
        wk["prices_url"] = f"{config.hub_url}/ai-market/v2/prices"
        wk["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Sign the ENTIRE document (sign_object) so every field — mcp_servers, prices_url,
        # federation, peers, generated_at — is tamper-evident and an external validator can verify
        # the hub from .well-known alone. (manifest_canonical only covered structural fields, so it
        # left these unprotected.)
        if erc8004:
            # BEFORE sign_object, deliberately. A self-declared identity that sits outside
            # the document signature is rewritable in transit by any relay — the same class
            # of hole as an unsigned tools[] (spec §7.3.2). Declared here, never verified.
            wk["erc8004"] = erc8004

        wk["signature"] = signer.sign_object(wk)
        return wk
