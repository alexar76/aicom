"""Federation: announce (the knock), peers, preview, assay, inbound log, crawl, approve,
delete, repin.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException

from aimarket_hub import realm
from aimarket_hub.api_models import AnnounceRequest
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.federation_assay import assay_blockers
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer
from aimarket_hub.slash_sync import SlashRegistry
from aimarket_hub.trust import TrustScorer
from aimarket_hub.paging import page_limit


# Peers in a federation preview: the default page and the most one request may read.
PREVIEW_PAGE = 200
PREVIEW_PAGE_MAX = 500

# Inbound federation log rows: the default page and the most one request may read.
INBOUND_PAGE = 100
INBOUND_PAGE_MAX = 500


def register(
    *,
    _is_admin_bearer: Callable[..., Any],
    _require_admin: Callable[..., Any],
    config: HubConfig,
    db: HubDatabase,
    late: SimpleNamespace,
    router: APIRouter,
    signer: Signer,
    slash_registry: SlashRegistry,
    trust_scorer: TrustScorer,
) -> SimpleNamespace:
    """Attach the /federation routes to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        logger,
    )

    # ── Federation ──────────────────────────────────────────────

    def _pending_peer_cap() -> int:
        """How many quarantined peers an unauthenticated caller may create.

        Two caps are documented and only one was ever read. Both announce doors passed
        ``federation_gossip_max_observed`` (2000) — pinned by ``test_pending_queue_is_capped``
        — while ``AIMARKET_FEDERATION_OPEN_MAX_PENDING`` (documented as "hard cap on pending
        peers: an open door is also a write amplifier", default 50) was referenced nowhere in
        the package. An operator who set it got silence.

        So: honour it when it is EXPLICITLY set, and otherwise keep the cap this hub already
        enforces. Lowering a live federation's effective ceiling from 2000 to 50 unasked is
        the operator's call, not this function's — but a knob that does nothing is a trap
        either way.
        """
        raw = os.environ.get("AIMARKET_FEDERATION_OPEN_MAX_PENDING", "").strip()
        if raw:
            return config.federation_open_max_pending
        return config.federation_gossip_max_observed

    def _validate_hub_url(url: str) -> None:
        """Reject URLs pointing to internal/private hosts (SSRF prevention).

        Uses the same DNS-resolving safety check as the crawler — protects
        against DNS rebinding (evil.com → 192.168.x.x) and IPv4-mapped IPv6.
        """
        from aimarket_hub.crawler import _url_is_safe

        if not url:
            raise HTTPException(status_code=400, detail="hub_url is required")
        if any(c in url for c in "\r\n\t"):
            raise HTTPException(status_code=400, detail="Invalid characters in URL")
        if not _url_is_safe(url):
            raise HTTPException(
                status_code=400,
                detail=f"URL resolves to restricted network or invalid scheme: {url[:40]}...",
            )

    @router.post("/federation/announce")
    async def federation_announce(
        body: AnnounceRequest,
        authorization: str = Header(default=""),
    ):
        """Register a peer.

        Two doors, and they lead to different places. With an admin token the
        operator adds a peer directly, as before. Without one, anyone may announce
        a public address — and lands in quarantine: ``status=pending``,
        ``trusted=False``. A sandbox assay then runs in the background; a pass
        auto-admits. Open federation changes who may knock, never who is trusted
        on the knock itself.
        """
        # Public announcements are observations, not admission. Like a blockchain
        # address seen on the network, a syntactically safe public Hub is always made
        # visible in quarantine; credentials are still required to trust it.
        open_mode = not _is_admin_bearer(authorization)
        if not (realm.peer_inside(body.hub_url) and realm.peer_inside(body.well_known_url or body.hub_url)):
            # Worded like the SSRF refusal on purpose: a knock from outside must not learn
            # that it reached a sealed bubble rather than a hub that will not federate.
            raise HTTPException(
                status_code=400,
                detail=f"hub_url is not admissible to this federation: {body.hub_url[:40]}",
            )
        if open_mode:
            _validate_hub_url(body.hub_url)
            if body.well_known_url:
                _validate_hub_url(body.well_known_url)
            url = body.hub_url.rstrip("/")
            outcome = db.announce_peer(
                Peer(
                    url=url,
                    name=(body.hub_name or url)[:200],
                    capabilities_count=0,  # a stranger's self-reported count is not evidence
                    well_known_url=body.well_known_url or f"{url}/.well-known/ai-market.json",
                    # NO key from an unauthenticated caller. announce_peer refuses to overwrite a
                    # peer it already knows — but for a hub this instance has never met, storing
                    # the announcer's key would let a stranger ESTABLISH the pin for someone
                    # else's URL. The real hub's genuine key would then look like a takeover and
                    # the crawl would abort forever. A pin is set by an operator or by a crawl
                    # this hub performed itself, never by a claim arriving over HTTP.
                    public_key="",
                    depth=1,
                    discoverer="announce:open",
                ),
                max_pending=_pending_peer_cap(),
            )
            if outcome == "rejected_cap":
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Pending peer queue is full "
                        f"({_pending_peer_cap()}). The operator must "
                        f"approve or reject waiting peers before new ones are accepted."
                    ),
                )
            # A hub that crawled us before it knocked is already a pending row ("known"), and
            # the knock used to schedule nothing: it waited for the next crawl cycle, an hour
            # on modelmarket.dev, with `assay_scheduled: false` (found end to end, 2026-10-12).
            # A known PENDING peer is assayed on its knock too, within the same politeness
            # floors the crawl applies (`_assay_due`), so knocking again buys no extra probes.
            knock_assay = outcome == "added"
            if outcome == "known" and config.federation_assay:
                from aimarket_hub.federation_assay import _assay_due

                known = db.get_peer(url)
                if known is not None and str(getattr(known, "status", "") or "") == "pending":
                    knock_assay = _assay_due(db.get_peer_assay(url) or {})[0]
            if knock_assay and config.federation_assay:
                assay_url = url

                async def _assay_knock() -> None:
                    try:
                        from aimarket_hub.federation_assay import run_assay
                        await run_assay(assay_url, config=config, db=db, signer=signer)
                    except Exception as exc:
                        logger.warning("post-announce assay of %s failed: %s", assay_url, exc)

                asyncio.create_task(_assay_knock())
            return {
                "acknowledged": True,
                "peer_added": outcome == "added",
                "status": "known" if outcome == "known" else "pending",
                "trusted": False,
                "assay_scheduled": bool(knock_assay and config.federation_assay),
                # Where the knocking operator reads the verdict. The dossier was always public;
                # nothing told them it existed, so a `review` was silent (2026-10-12).
                "assay_url": (
                    f"{config.hub_url.rstrip('/')}/ai-market/v2/federation/assay?"
                    + urlencode({"url": url})
                ),
                "note": _knock_promise(),
            }
        _require_admin(authorization)
        _validate_hub_url(body.hub_url)
        if body.well_known_url:
            _validate_hub_url(body.well_known_url)
        peer = Peer(
            url=body.hub_url,
            name=body.hub_name or body.hub_url,
            capabilities_count=body.capabilities_count,
            last_crawl=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            well_known_url=body.well_known_url,
            public_key=body.signer_public_key,
            depth=1,
            discoverer="announce",
        )
        db.upsert_peer(peer)
        return {"acknowledged": True, "peer_added": True}

    def _peer_declared(p) -> dict[str, Any]:
        """What the PEER says about itself — kept in its own envelope on purpose.

        Every field here was published by the peer and copied verbatim. Flattening it into
        the row would let a consumer read `id` as an answer when it is a claim, which is
        the mistake this envelope exists to make impossible to write by accident.
        """
        return {
            "description": p.description,
            "hub_version": p.hub_version,
            "id": p.declared_id,
            # Display only. Routing re-resolves the endpoint per invoke
            # (federation_transport), because a stored one is stale the moment a peer moves.
            "mcp_endpoint": p.mcp_endpoint,
        }

    def _knock_promise() -> str:
        """What THIS hub will actually do with a knock, in its current configuration.

        The two knock-facing notes used to be fixed strings promising that "a sandbox assay
        runs automatically" and "a pass indexes this hub without an operator click". Neither
        clause is true everywhere it was printed. Measured 2026-09-05:
        `hunt.modelmarket.dev` runs with AIMARKET_FEDERATION_ASSAY=0 and still told two
        knockers an assay was scheduled - both had waited with no verdict at all; and
        `hub.modelmarket.dev` told CHARON a pass would admit it, while CHARON sat at
        verdict=pass, quarantined, for a day, because that hub has no judge token.

        A federation runs on what hubs tell each other. A note that describes a different
        hub's configuration is not a nicety to fix later - it is the wrong answer to
        "what happens next", given to the one party who cannot check.
        """
        assay_on = bool(getattr(config, "federation_assay", True))
        auto = bool(getattr(config, "federation_auto_admit", True)
                    and getattr(config, "federation_judge_key", ""))
        if not assay_on:
            return ("Recorded in quarantine. Automatic assay is switched off on this hub, so "
                    "no verdict will be reached on its own: an operator must review and "
                    "Approve.")
        if auto:
            return ("Recorded in quarantine. A sandbox assay runs automatically; a pass "
                    "indexes this hub without an operator click. Fail or review stay pending "
                    "for the operator desk.")
        return ("Recorded in quarantine. A sandbox assay runs automatically, but this hub has "
                "no judge token, so a pass is a scorecard rather than an admission: an "
                "operator must Approve. Fail or review stay pending too.")

    def _publishable_pending_peers(db_: Any) -> list[Any]:
        """Pending peers this hub is willing to show the public.

        An ALIAS of a hub already active here is withheld. Without that, the observation
        layer is a loop: `http://108.165.32.182:9083` is the competing lab's own address by
        raw IP, we observed it, we published it, their hub read it back from us and published
        it again — so a plaintext address neither hub advertises for itself kept circulating
        through the federation and kept being adopted as a peer. Nothing self-declared it;
        gossip sustained it alone.

        ONE rule, three surfaces: `/.well-known` observed_hubs, the public pending list on
        `/federation/peers`, and the landing block those feed. Filtering only the first left
        the raw IP rendered on the public landing page with a red "assay failed" badge — the
        same second-entry-point mistake this guard exists to stop.

        Only crawled peers carry a key, so this withholds exactly the aliases we can prove
        and leaves every genuine unknown visible. An operator sees the full list.

        The FIRST alias to check is our own. A hub is not a peer of itself, so it is absent
        from its own peer table and `active_peer_with_public_key` can never match it - which
        is how `http://108.165.32.182:9083` came to sit on the competing lab's own landing
        page as an unapproved hub with a red "assay failed" badge, signed with the very key
        that page is served under. Measured 2026-09-05: the pending row's advertised key, the
        raw-IP endpoint's key and this hub's own `signer_public_key` were the same string.
        Its own key is the one identity a hub can never be wrong about, so it is checked
        first and without a database lookup.
        """
        own_key = ""
        try:
            own_key = (signer.public_key_b64 or "").strip()
        except Exception:  # pragma: no cover - a hub with no signer has no self to confuse
            own_key = ""
        out = []
        for peer in db_.list_pending_peers():
            key = (getattr(peer, "public_key", "") or "").strip()
            advertised = (getattr(peer, "advertised_public_key", "") or "").strip()
            if own_key and own_key in (key, advertised):
                continue
            if key and db_.active_peer_with_public_key(key, exclude_url=peer.url):
                continue
            out.append(peer)
        return out

    late._pending_peer_cap = _pending_peer_cap
    late._publishable_pending_peers = _publishable_pending_peers

    @router.get("/federation/peers")
    async def list_peers(authorization: str = Header(default="")):
        peers = db.list_peers()
        # The operator sees aliases; the public does not.
        pending_rows = (
            db.list_pending_peers()
            if _is_admin_bearer(authorization)
            else _publishable_pending_peers(db)
        )
        from aimarket_hub.peer_identity import identity_for

        return {
            "peers": [
                {
                    "url": p.url,
                    "name": p.name,
                    "capabilities_count": p.capabilities_count,
                    "last_crawl": p.last_crawl,
                    "trust_score": p.trust_score,
                    "depth": p.depth,
                    "categories": p.categories,
                    "well_known_url": p.well_known_url,
                    "trusted": p.trusted,
                    "public_key": p.public_key,
                    "status": p.status,
                    "pin_reject_reason": p.pin_reject_reason,
                    "advertised_public_key": p.advertised_public_key,
                    # Which of OUR nodes this is, from the operator's pin — "" for every
                    # peer they never pinned, which is every stranger. A consumer that
                    # folds a peer onto a local node reads THIS, never `declared.id`.
                    **identity_for(p, config),
                    "declared": _peer_declared(p),
                }
                for p in peers
            ],
            "count": len(peers),
            # Peers that knocked but were never approved. Kept in their own key so
            # every existing consumer of "peers" keeps its exact meaning — approved
            # hubs — and nothing starts treating a stranger as a member of the
            # federation by accident.
            "pending": [
                {
                    "url": p.url,
                    "name": p.name,
                    "first_seen": p.first_seen,
                    "last_crawl": p.last_crawl,
                    "discoverer": p.discoverer,
                    "well_known_url": p.well_known_url,
                    "categories": p.categories,
                    "trusted": False,
                    "status": "pending",
                    # TWO counts, because they are two different things and a UI that
                    # shows one of them silently shows the wrong one. `preview_` is what
                    # this hub actually read and signature-checked from the peer's
                    # manifest (capped by AIMARKET_FEDERATION_PREVIEW_MAX_CAPS, so it can
                    # be lower than the truth); `declared_` is the peer's own number out
                    # of its well-known — a claim, never a fact we established. Nothing
                    # is indexed either way.
                    "preview_capabilities": db.count_preview_capabilities(p.url),
                    "declared_capabilities": p.capabilities_count,
                    "assay_verdict": assay.get("verdict"),
                    "assay_ran_at": assay.get("ran_at") or "",
                    # What keeps it from `pass`, by check id — the page explains each id
                    # in the reader's language; `detail` is the assay's own words.
                    "assay_blockers": assay_blockers(assay),
                    **identity_for(p, config),
                    "declared": _peer_declared(p),
                }
                for p in pending_rows
                for assay in (db.get_peer_assay(p.url) or {},)
            ],
            "pending_count": len(pending_rows),
            "open_federation": bool(config.federation_open),
            "observation_gossip": True,
        }

    @router.get("/federation/preview")
    async def federation_preview(url: str = "", limit: int = 200):
        """What a PENDING peer says it offers — quarantined, never live.

        These rows come from ``peer_preview_capabilities``, a table that search,
        routing, invoke and the published manifest do not read. Showing them lets an
        operator judge a stranger by its catalogue instead of by its URL, without
        that catalogue becoming reachable. Every row is returned with
        ``quarantined: true``; a client that renders them next to real capabilities
        without saying so is misrepresenting this hub.
        """
        limit = page_limit(limit, default=PREVIEW_PAGE, maximum=PREVIEW_PAGE_MAX)
        return {
            "capabilities": db.list_preview_capabilities(url.strip().rstrip("/"), limit=limit),
            "count": db.count_preview_capabilities(url.strip().rstrip("/")),
            "quarantined": True,
            "note": (
                "Preview only. These capabilities are not indexed, not searchable "
                "and not invocable until a sandbox assay passes or an operator "
                "approves their peer."
            ),
        }

    def _assay_payload(dossier: dict | None, url: str = "") -> dict:
        if not dossier:
            return {
                "url": url,
                "verdict": None,
                "trusted": False,
                "indexed": False,
                "auto_promoted": False,
                "quarantined": True,
                "checks": [],
                "sandbox": {},
                "note": (
                    "No assay yet. " + _knock_promise()
                    + " POST /ai-market/v2/federation/assay (admin) runs one now."
                ),
            }
        dossier = dict(dossier)
        target = str(dossier.get("url") or url or "").strip().rstrip("/")
        peer = db.get_peer(target) if target else None
        trusted = bool(peer and peer.trusted)
        sandbox = dossier.get("sandbox") if isinstance(dossier.get("sandbox"), dict) else {}
        dossier["trusted"] = trusted
        dossier["indexed"] = trusted
        dossier["quarantined"] = not trusted
        dossier["auto_promoted"] = bool(sandbox.get("auto_promoted") or dossier.get("auto_promoted"))
        return dossier

    @router.get("/federation/assay")
    async def federation_assay_get(url: str = ""):
        """Last post-quarantine assay dossier — public, like preview.

        A ``pass`` with auto-admit on (default) sets ``trusted`` and the next
        crawl indexes. Names and descriptions are never scored.
        """
        target = url.strip().rstrip("/")
        return _assay_payload(db.get_peer_assay(target) if target else None, target)

    @router.post("/federation/assay")
    async def federation_assay_run(body: dict, authorization: str = Header(default="")):
        """Run the sandbox assay on a pending (or any public) hub URL.

        Admin-only: it makes outbound fetches. A pass auto-admits when
        ``AIMARKET_FEDERATION_AUTO_ADMIT`` is on (default).
        """
        _require_admin(authorization)
        if not config.federation_assay:
            raise HTTPException(status_code=503, detail="federation assay is disabled")
        target = (body.get("url") or "").strip()
        if not target:
            raise HTTPException(status_code=400, detail="url is required")
        from aimarket_hub.federation_assay import run_assay
        dossier = await run_assay(target, config=config, db=db, signer=signer)
        return _assay_payload(dossier, dossier.get("url") or target)

    @router.get("/federation/inbound")
    async def federation_inbound(authorization: str = Header(default=""), limit: int = 100):
        """Hubs that have crawled THIS hub, by their own self-declared URL.

        Admin-only: it is a list of who reads us, which is the operator's business
        and nobody else's. No client IPs are stored — only the hub URL a crawler
        volunteers in ``X-AIMarket-Crawler`` and its User-Agent.
        """
        _require_admin(authorization)
        return {
            "inbound": db.list_inbound_federation(limit=page_limit(limit, default=INBOUND_PAGE, maximum=INBOUND_PAGE_MAX)),
        }

    @router.post("/federation/crawl")
    async def trigger_crawl(authorization: str = Header(default="")):
        _require_admin(authorization)
        from aimarket_hub.crawler import Crawler
        crawler = Crawler(
            config=config, db=db, signer=signer, trust_scorer=trust_scorer,
            slash_registry=slash_registry,
        )
        try:
            stats = await crawler.crawl(clear_first=False)
        finally:
            await crawler.close()
        return {"status": "complete", "stats": stats}

    @router.post("/federation/peers/approve")
    async def approve_peer(body: dict, authorization: str = Header(default="")):
        """Operator approval (anti-TOFU): mark a discovered peer trusted so its manifests get
        indexed on the next crawl. Admin-only. Body: {url, trusted?: bool (default true)}."""
        _require_admin(authorization)
        url = (body.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        trusted = bool(body.get("trusted", True))
        if trusted and config.federation_assay_require:
            assay = db.get_peer_assay(url)
            if not assay or assay.get("verdict") != "pass":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "assay_required: last assay must verdict pass before approve "
                        "(AIMARKET_FEDERATION_ASSAY_REQUIRE=1). "
                        "POST /ai-market/v2/federation/assay first. An LLM verdict is not accepted."
                    ),
                )
        if trusted:
            # The auto-admit path checks this in `admit_peer`; this door did not, and it is
            # the actual click — the competing-lab hub sat ACTIVE at
            # http://108.165.32.182:9083 and PENDING as https://hub.modelmarket.dev, one
            # Approve away from being crawled and re-exported twice under one identity.
            existing = db.get_peer(url)
            key = (getattr(existing, "public_key", "") or "").strip() if existing else ""
            twin = db.active_peer_with_public_key(key, exclude_url=url) if key else None
            if twin:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"duplicate_identity: this signing key is already active at {twin}. "
                        "One hub, one peer row — admitting both would index and re-export the "
                        f"same catalogue twice. Remove {twin} first if this address should "
                        "replace it (DELETE /ai-market/v2/federation/peers?url=...)."
                    ),
                )
        if not db.set_peer_trusted(url, trusted):
            raise HTTPException(status_code=404, detail=f"peer not found: {url}")
        promoted = False
        cleared = 0
        if trusted:
            # Leaving the peer at status="pending" would keep it out of the peer
            # list it now belongs in, and leaving preview rows behind would show a
            # stale quarantined copy beside the real catalogue the next crawl indexes.
            promoted = db.promote_pending_peer(url)
            cleared = db.clear_preview_capabilities(url)
        return {
            "url": url,
            "trusted": trusted,
            "status": "updated",
            "promoted_from_pending": promoted,
            "preview_rows_cleared": cleared,
            "note": (
                "Manifests are indexed on the next crawl — POST /federation/crawl to "
                "do it now." if trusted else "Peer left untrusted; nothing is indexed."
            ),
        }

    @router.delete("/federation/peers")
    async def delete_peer(url: str, authorization: str = Header(default="")):
        """Reject a peer outright: remove the row and its preview catalogue.

        The pending queue needs an exit as well as an entrance. Without this an operator
        could approve waiting peers but never dismiss them, so an unauthenticated party
        could fill the queue to its cap and hold it shut against everyone else.
        """
        _require_admin(authorization)
        url = (url or "").strip().rstrip("/")
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        if not db.delete_peer(url):
            raise HTTPException(status_code=404, detail=f"peer not found: {url}")
        return {"url": url, "deleted": True}

    @router.post("/federation/peers/repin")
    async def repin_peer(body: dict, authorization: str = Header(default="")):
        """Operator re-pin after a legitimate peer key rotation — classical, PQ, or both.

        Fail-closed crawler rejects ``public key changed`` forever unless an admin
        updates the pin here. Seed pins (``AIMARKET_SEED_PUBKEYS``) only apply on
        first contact — they do not rotate an existing DB pin.

        Body: ``{url, public_key?, pq_public_key?, trusted?: true,
        previous_public_key?: str, previous_pq_public_key?: str, crawl?: true}``.
        At least one of ``public_key`` / ``pq_public_key`` is required — a peer can rotate its
        ML-DSA key alone, and requiring the classical one for that would invite an operator to
        paste the current value back in, which is a chance to paste the wrong one. The
        ``previous_*`` fields are optimistic concurrency (must match the current pin when set —
        keep the old value for rollback).
        """
        _require_admin(authorization)
        url = (body.get("url") or "").strip()
        public_key = (body.get("public_key") or "").strip()
        pq_public_key = (body.get("pq_public_key") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        if not public_key and not pq_public_key:
            raise HTTPException(
                status_code=400,
                detail="public_key or pq_public_key is required",
            )
        trusted_raw = body.get("trusted", True)
        trusted = None if trusted_raw is None else bool(trusted_raw)
        previous = body.get("previous_public_key")
        if previous is not None:
            previous = str(previous).strip()
        previous_pq = body.get("previous_pq_public_key")
        if previous_pq is not None:
            previous_pq = str(previous_pq).strip()
        try:
            result = db.repin_peer_public_key(
                url,
                public_key or None,
                trusted=trusted,
                previous_public_key=previous,
                pq_public_key=pq_public_key or None,
                previous_pq_public_key=previous_pq,
            )
        except ValueError as exc:
            detail = str(exc)
            code = 404 if detail.startswith("peer not found") else 400
            raise HTTPException(status_code=code, detail=detail) from exc

        crawl_stats = None
        if bool(body.get("crawl", True)):
            from aimarket_hub.crawler import Crawler
            crawler = Crawler(
                config=config, db=db, signer=signer, trust_scorer=trust_scorer,
                slash_registry=slash_registry,
            )
            try:
                crawl_stats = await crawler.crawl(clear_first=False)
            finally:
                await crawler.close()
        return {"status": "repinned", "peer": result, "crawl": crawl_stats}

    # ── Observed sellers (spec §2.7, observed_sellers.py) ────────

    @router.get("/federation/observed-sellers")
    async def observed_sellers_list():
        """x402 sellers this hub lists from their own discovery document, with their consent.

        Public. Every probed route says what its last unpaid 402 named and whether it is
        served now. Nothing here is signed by a seller, and this hub is not in their payment
        path: a buyer calls the seller and pays per the 402 it gets.
        """
        from aimarket_hub import observed_sellers as _observed

        return {
            "tier": _observed.TIER,
            "enabled": _observed.enabled(),
            "observed_by": config.hub_url,
            "interval_s": _observed.interval_s(),
            "ttl_s": _observed.ttl_s(),
            "vouches_for": (
                "only that, at observed_at, an unpaid request to url returned a 402 naming this "
                "amount, asset, network and payTo"
            ),
            "how_to_buy": _observed.HOW_TO_BUY,
            "sellers": [
                _observed.public_seller(s, hub_url=config.hub_url)
                for s in db.list_observed_sellers()
            ],
            "spec": "aimarket-protocol/spec.md §2.7",
            "protocol_version": "v2",
        }

    @router.post("/federation/observed-sellers")
    async def observed_sellers_add(body: dict, authorization: str = Header(default="")):
        """Record a seller's consent, then observe it at once. Admin-only.

        Body: ``origin``; ``consent`` ``{by, at, how?, note?}``; ``routes`` (URLs on the
        origin; default every route the discovery document lists, up to the cap); ``pay_to``
        (the recipient the seller confirmed; default: pinned on first sight); ``name``.
        Re-posting with a new ``pay_to`` is how the operator re-confirms a changed recipient;
        re-posting without one keeps the pin.
        """
        _require_admin(authorization)
        from aimarket_hub import observed_sellers as _observed

        if not _observed.enabled():
            raise HTTPException(status_code=503, detail="observed sellers are disabled on this hub")
        origin = _observed.normalize_origin(str(body.get("origin") or ""))
        if not origin:
            raise HTTPException(status_code=400, detail="origin must be an https URL")
        _validate_hub_url(origin)
        try:
            consent = _observed.clean_consent(body.get("consent"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raw_routes = body.get("routes") or []
        if not isinstance(raw_routes, list):
            raise HTTPException(status_code=400, detail="routes must be a list of URLs")
        routes = [str(u).strip() for u in raw_routes if str(u).strip()]
        foreign = [u for u in routes if not _observed.same_origin(u, origin)]
        if foreign:
            raise HTTPException(status_code=400, detail=f"route is not on {origin}: {foreign[0][:120]}")
        if len(routes) > _observed.max_routes():
            raise HTTPException(
                status_code=400, detail=f"at most {_observed.max_routes()} routes per seller",
            )
        pay_to = str(body.get("pay_to") or "").strip()
        if pay_to and (len(pay_to) > 128 or any(c.isspace() for c in pay_to)):
            raise HTTPException(status_code=400, detail="pay_to is not an address")
        existing = db.get_observed_seller(origin) or {}
        db.upsert_observed_seller(
            origin,
            consent=consent,
            allowed_routes=routes,
            pinned_pay_to=pay_to or existing.get("pinned_pay_to") or "",
            name=str(body.get("name") or "").strip(),
        )
        summary = await _observed.observe_due(db, hub_url=config.hub_url, origin=origin)
        seller = db.get_observed_seller(origin) or {"origin": origin}
        return {
            "status": "recorded",
            "observation": summary,
            "seller": _observed.public_seller(seller, hub_url=config.hub_url),
            "consent": seller.get("consent") or consent,
        }

    @router.post("/federation/observed-sellers/observe")
    async def observed_sellers_observe(body: dict | None = None, authorization: str = Header(default="")):
        """Observe one seller (``origin``) or all of them now. Admin-only: outbound requests."""
        _require_admin(authorization)
        from aimarket_hub import observed_sellers as _observed

        target = _observed.normalize_origin(str((body or {}).get("origin") or ""))
        if (body or {}).get("origin") and not target:
            raise HTTPException(status_code=400, detail="origin must be an https URL")
        return await _observed.observe_due(
            db, hub_url=config.hub_url, origin=target, force=not target,
        )

    @router.delete("/federation/observed-sellers")
    async def observed_sellers_withdraw(origin: str = "", authorization: str = Header(default="")):
        """Consent withdrawn: the seller and its observations are deleted. Admin-only."""
        _require_admin(authorization)
        from aimarket_hub import observed_sellers as _observed

        target = _observed.normalize_origin(origin)
        if not target:
            raise HTTPException(status_code=400, detail="origin must be an https URL")
        if not db.delete_observed_seller(target):
            raise HTTPException(status_code=404, detail="not an observed seller")
        return {"status": "withdrawn", "origin": target}

    return SimpleNamespace(
        _publishable_pending_peers=_publishable_pending_peers,
    )
