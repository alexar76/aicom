"""The signed manifest, the price list and catalogue search."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter

from aimarket_hub import credits, settle, x402
from aimarket_hub.access_policy import capability_access_mode, capability_is_publicly_offerable
from aimarket_hub.catalog import catalogue_display_name
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable
from aimarket_hub.semantic_search import interpret_intent
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import SupplySecurity


def register(
    *,
    _pays_a_third_party: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    router: APIRouter,
    signer: Signer,
    supply_security: SupplySecurity,
) -> SimpleNamespace:
    """Attach /manifest, /prices and /search to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _catalogue_route,
        _catalogue_snapshot,
        _input_requirements,
    )

    # ── Manifest ────────────────────────────────────────────────

    # Plain `def` (FastAPI runs it in a worker thread): a 0.8-1 s catalogue walk and
    # signature on the event loop holds every other request, /health included.
    @router.get("/manifest")
    def v2_manifest():
        # The manifest is the federation's and every MCP client's view of what is on
        # sale here, so it gets the same gate as /search: a row this hub cannot execute
        # is not a tool, and advertising it to peers propagates the dead listing.
        caps = _catalogue_snapshot(db, config)
        # A published success rate with no invocations behind it is the crawler's neutral
        # baseline, not a measurement — and the two are indistinguishable from the number
        # alone. Carry the observation count so a buyer can tell, and serve the MEASURED
        # rate the moment there is one (the crawler's comment has always said the hub
        # computes this itself; nothing did, so 0.5 was frozen into every signed manifest).
        observed = db.observations_30d()
        observed_caps = observed["by_capability"]
        observed_hubs = observed["by_hub"]
        tools = []
        for c in caps:
            attempts, successes = observed_caps.get(c.capability_id, (0, 0))
            tools.append({
                "name": c.tool_name(),
                "display_name": catalogue_display_name(c),
                "description": c.description,
                "input_schema": c.input_schema,
                "output_schema": c.output_schema,
                "price_per_call_usd": c.price_per_call_usd,
                "access_mode": capability_access_mode(c),
                "offerable": capability_is_publicly_offerable(c),
                "p50_latency_ms": c.p50_latency_ms,
                "success_rate_30d": (
                    round(successes / attempts, 4) if attempts else c.success_rate_30d
                ),
                # "measured" → the rate above is successes/attempts over the 30d window.
                # "unobserved" → nothing was invoked; the rate is a neutral placeholder and
                # must not be rendered as a score. Consumers key off THIS, not the number.
                "reputation_basis": "measured" if attempts else "unobserved",
                "observations_30d": attempts,
                "product_id": c.product_id,
                "capability_id": c.capability_id,
                "source_hub": c.source_hub,
                "source_hub_name": c.source_hub_name,
                # The protocol schema requires a number. Local publisher rows have no
                # federation markup and historically stored NULL here, which made the
                # entire signed manifest invalid to every strict peer crawler.
                "routed_price_usd": (
                    c.routed_price_usd
                    if c.routed_price_usd is not None
                    else c.price_per_call_usd
                ),
                "routing_fee_bps": c.routing_fee_bps,
                "trust_score": c.trust_score,
                "route_status": _catalogue_route(db, config, c).status,
                # Where a caller POSTs this capability. A locally published capability
                # carries its provider's own URL. A FEDERATED one carried `null`: the
                # crawler deliberately does not store a peer-supplied invoke_url (a peer
                # could point it anywhere), so the entry advertised a price, schemas and
                # a source hub with no address to send anything to. The address is this
                # hub — routed invokes go here with `source_hub` naming the peer, which
                # the entry above already carries. Derived from our own configured
                # hub_url, never from the peer.
                "invoke_url": c.invoke_url or (
                    f"{config.hub_url.rstrip('/')}/ai-market/v2/invoke"
                    if (c.source_hub or "local") != "local"
                    else None
                ),
                # The key OUR OWN provider signs answers and delivery receipts with, so a hub
                # that crawls us can count buyers' signed receipts for this seller
                # (deliveries.py) — what `aimarket node` already publishes. Never repeated
                # for a federated row: a key about somebody else's listing is the source
                # hub's to publish, and a relay restating it could substitute its own.
                **(
                    {"provider_pubkey": c.provider_pubkey}
                    if (c.source_hub or "local") == "local" and (c.provider_pubkey or "").strip()
                    else {}
                ),
            })

        by_hub: dict[str, dict[str, Any]] = {}
        for p in db.list_peers():
            attempts, _successes = observed_hubs.get(p.url, (0, 0))
            by_hub[p.url] = {
                "capabilities_count": p.capabilities_count,
                "trust_score": p.trust_score,
                # Peer trust is only earned through observed trade. Without a single
                # invocation the score is whatever the crawler seeded, so say so rather
                # than let a peer's placeholder read as a rating.
                "trust_basis": "measured" if attempts else "unobserved",
                "observations_30d": attempts,
                "last_crawl": p.last_crawl,
            }
        local_attempts, _local_successes = observed_hubs.get("local", (0, 0))
        by_hub["local"] = {
            "capabilities_count": db.count_capabilities("local"),
            "trust_score": 1.0,
            # This hub trusts itself by construction, not by measurement.
            "trust_basis": "self",
            "observations_30d": local_attempts,
            "last_crawl": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        manifest_body = {
            "protocol_version": "v2",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": config.hub_url,
            "total_capabilities": len(caps),
            # Counted off the filtered list, not the table: a count that includes rows
            # absent from `tools` tells a peer we have stock we will not show it.
            "local_capabilities": sum(1 for c in caps if c.source_hub == "local"),
            "federated_capabilities": sum(1 for c in caps if c.source_hub != "local"),
            "hubs_indexed": db.peer_count(),
            "tools": tools,
            "by_hub": by_hub,
        }
        manifest_body["signature"] = signer.sign_manifest(manifest_body)
        return manifest_body

    # ── Prices (bulk) ───────────────────────────────────────────

    @router.get("/prices")
    def v2_prices():  # sync for the same reason as /manifest
        """Compact, signed price list for every capability — so an agent can learn
        'what costs what' in one call without a full manifest/search.

        Fulfillable rows only, the same rule the manifest and /search apply. This list
        was the one storefront that did not: on 2026-08-25 it advertised 97 rows against
        the manifest's 85, and the twelve extras were exactly the unfulfillable local
        demos — headed by `audit.perf@v1` at $1.50, the most expensive item on the shelf.
        An agent that shops by price sorts descending, so the price list was steering
        buyers at precisely the capabilities the hub cannot run.
        """
        caps = _catalogue_snapshot(db, config)
        prices = [
            {
                "capability_id": c.capability_id,
                "product_id": c.product_id,
                "price_usd": c.price_per_call_usd,
                "routed_price_usd": c.routed_price_usd,
                "routing_fee_bps": c.routing_fee_bps,
                "source_hub": c.source_hub,
                "route_status": _catalogue_route(db, config, c).status,
            }
            for c in caps
        ]
        body = {
            "protocol_version": "v2",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": config.hub_url,
            "currency": "USD",
            "routing_fee_bps": config.routing_fee_bps,
            "count": len(prices),
            "prices": prices,
        }
        body["signature"] = signer.sign_object(body)  # sign all price rows, not just structural fields
        return body

    # ── Search ──────────────────────────────────────────────────

    def _observed_matches(intent: str, budget: float | None, hub: str, category_key: str,
                          limit: int) -> list[dict[str, Any]]:
        """x402 routes listed by observation (spec §2.7) that fit the search."""
        from aimarket_hub import observed_sellers

        if not observed_sellers.enabled():
            return []
        try:
            routes = observed_sellers.served_routes(
                db.list_observed_sellers(), hub_url=config.hub_url,
            )
        except Exception:  # noqa: BLE001 - an observation must never fail a search
            return []
        if hub != "any":
            routes = [r for r in routes if r["seller"] == hub]
        if category_key:
            routes = [r for r in routes if category_key in r.get("description", "").lower()]
        return observed_sellers.search_routes(routes, intent, budget=budget, limit=limit)

    @router.get("/search")
    async def search(
        intent: str = "",
        budget: float | None = None,
        max_latency_ms: int | None = None,
        min_trust: float | None = None,
        hub: str = "any",
        category: str | None = None,
        include_demo: bool = False,
        include_stale: bool = False,
        limit: int = 20,
        offset: int = 0,
    ):
        search_started = time.perf_counter()
        # ``limit``/``offset`` page the response. They must not hide the catalogue:
        # empty-intent browse ranks the full index, then slices. ``limit=0`` means
        # "from offset to the end". A 100/500 ceiling used to drop live SKUs.
        offset = max(0, int(offset))
        page = int(limit)
        detailed = db.search_capabilities_detailed(intent, limit=None)
        # filter_for_discover preserves input order. A capability id may legitimately be
        # offered by multiple hubs, so explanations are keyed by the whole routed offer.
        detail_by_offer = {
            (m.capability.capability_id, m.capability.product_id, m.capability.source_hub): m
            for m in detailed
        }
        results = supply_security.filter_for_discover([m.capability for m in detailed])
        floor = min_trust if min_trust is not None else supply_security.policy.min_trust_discover
        category_key = (category or "").strip().lower()

        # Same honesty rule as /manifest: an agent picking between offers has to be able
        # to tell an earned trust score from the crawler's placeholder.
        observed_search = db.observations_30d()["by_capability"]
        # Deliveries buyers confirmed for sellers paid directly (deliveries.py): the evidence a
        # hub cannot observe itself. Keyed by seller, shown on every listing of that seller.
        delivered_search = db.deliveries_30d()
        peer_categories: dict[str, frozenset[str]] = {}

        def _peer_categories(source_hub: str) -> frozenset[str]:
            if not source_hub or source_hub == "local":
                return frozenset()
            if source_hub not in peer_categories:
                try:
                    peer = db.get_peer(source_hub)
                except Exception:  # noqa: BLE001 - a lookup must never fail a search
                    peer = None
                declared = getattr(peer, "categories", None) or []
                peer_categories[source_hub] = frozenset(
                    str(c).strip().lower() for c in declared if isinstance(c, str)
                )
            return peer_categories[source_hub]

        filtered: list[dict[str, Any]] = []
        for cap in results:
            if hub != "any" and cap.source_hub != hub:
                continue
            if not include_demo and getattr(cap, "is_demo", False):
                continue
            # Never offer what this hub cannot run. The is_demo check above is not
            # enough on its own: the twelve seeded showcase rows predate migration 013,
            # so their flag is 0 and they were being sold at $0.15–$1.50 while the
            # invoke path answered 404. include_demo does not override this — a buyer
            # asking to see demos still must not be quoted a price for a dead row.
            if not capability_is_fulfillable(cap):
                continue
            if not capability_is_publicly_offerable(cap):
                continue
            route = _catalogue_route(db, config, cap)
            if route.status == "unavailable":
                continue
            if route.status == "stale" and not include_stale:
                continue
            if category_key and category_key in _peer_categories(cap.source_hub):
                # The peer's own well-known `categories` — MOMUS declares "security", but
                # none of its ids or descriptions carry a token below, so the ecosystem's
                # security auditor was invisible under category=security.
                pass
            elif category_key:
                blob = (
                    f"{cap.capability_id} {cap.product_id} {cap.name} {cap.description}"
                ).lower()
                # "security" must not match Platon merely because its description
                # mentions a "security model" — require a tighter token.
                if category_key == "security":
                    if not any(
                        t in blob
                        for t in (
                            "security.", "skopos", "posture", "cve",
                            "secret-scan", "sec-feed", "security-rules",
                        )
                    ):
                        continue
                elif category_key not in blob:
                    continue
            if cap.trust_score < floor:
                continue
            if max_latency_ms is not None and cap.p50_latency_ms > max_latency_ms:
                continue
            routed = cap.routed_price_usd or cap.price_per_call_usd
            if budget is not None and routed > budget:
                continue
            match = detail_by_offer.get((cap.capability_id, cap.product_id, cap.source_hub))
            # What the buyer must send. Without this a client can only guess the body,
            # and a guessed body is a refusal that still costs a trial — see
            # _input_requirements for the production case this comes from.
            input_required, input_hint = _input_requirements(cap.input_schema)
            filtered.append({
                "product_id": cap.product_id,
                "capability_id": cap.capability_id,
                "source_hub": cap.source_hub,
                "source_hub_name": cap.source_hub_name,
                "name": cap.name,
                # Historical evidence for this indexed row, not the peer's last attempted
                # crawl. Missing records stay unknown until a successful signed refresh.
                "evidence": cap.catalogue_evidence or {
                    "kind": "local_catalogue" if (cap.source_hub or "local") == "local" else "catalogue_unrecorded",
                    "scope": "catalogue",
                    "signer": None,
                    "signer_public_key": None,
                    "checked_at": None,
                    "checked_by": config.hub_url,
                },
                "display_name": catalogue_display_name(cap),
                "description": cap.description,
                "score": match.score if match else 0.0,
                "match_type": match.match_type if match else "browse",
                "matched_concepts": list(match.matched_concepts) if match else [],
                "matched_terms": list(match.matched_terms) if match else [],
                "score_breakdown": {
                    "lexical": match.lexical_score if match else 0.0,
                    "semantic": match.semantic_score if match else 0.0,
                    "quality": match.quality_score if match else 0.0,
                },
                # The same answer whatever it is asked: listed after the matches whose answer
                # depends on the request (answer_dependence.py).
                "input_independent": bool(match.input_independent) if match else False,
                "price_per_call_usd": cap.price_per_call_usd,
                "access_mode": capability_access_mode(cap),
                # Use the same payee predicate as invoke admission. A local route alone
                # does not mean that the buyer may pay this seller with Hub credits.
                "credits_eligible": (
                    (cap.source_hub or "local") == "local"
                    and (cap.price_per_call_usd <= 0 or (credits.enabled() and not _pays_a_third_party(cap)))
                ),
                "routed_price_usd": routed,
                "routing_fee_bps": cap.routing_fee_bps,
                "trust_score": cap.trust_score,
                "reputation_basis": (
                    "measured" if observed_search.get(cap.capability_id, (0, 0))[0] else "unobserved"
                ),
                "observations_30d": observed_search.get(cap.capability_id, (0, 0))[0],
                "deliveries_30d": delivered_search.get((cap.source_hub or "local", cap.product_id)),
                "p50_latency_ms": cap.p50_latency_ms,
                "publisher_id": cap.publisher_id or None,
                "payout_address": settle.seller_pay_to(
                    cap, operator_pay_to=x402.recipient(),
                ) or None,
                "seller_id": cap.publisher_id or cap.source_hub_name or cap.source_hub,
                "seller_kind": "publisher" if cap.publisher_id else "hub",
                "stake_usd": cap.stake_usd or None,
                "demo": cap.is_demo,
                "offerable": capability_is_publicly_offerable(cap) and route.sellable,
                "route_status": route.status,
                "route_age_s": route.age_s,
                "input_required": input_required,
                "input_hint": input_hint,
            })

        total = len(filtered)
        window = filtered[offset:] if page <= 0 else filtered[offset:offset + page]
        interpretation = interpret_intent(intent)
        return {
            "query": intent,
            "category": category_key or None,
            "matches": window,
            "total": total,
            "offset": offset,
            "limit": 0 if page <= 0 else page,
            "has_more": (offset + len(window)) < total,
            # Sellers listed from their own x402 discovery document with their consent, as
            # this hub last saw their 402 (spec §2.7). Never mixed into `matches`: they are not
            # catalogue rows, not routable through this hub and not signed by their seller.
            "observed": _observed_matches(
                intent, budget, hub, category_key, 10 if page <= 0 else min(page, 10),
            ),
            "search": {
                "mode": "hybrid-semantic-v1",
                "languages": ["en", "ru", "es", "fr", "zh"],
                "interpreted_concepts": list(interpretation.concepts),
                "latency_ms": round((time.perf_counter() - search_started) * 1000.0, 2),
                "query_stays_local": True,
            },
            "total_hubs_searched": db.peer_count() + 1,
            "protocol_version": "v2",
        }

    return SimpleNamespace(
        search=search,
    )
