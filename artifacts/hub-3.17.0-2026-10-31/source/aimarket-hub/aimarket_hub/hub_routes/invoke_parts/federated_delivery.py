"""POST /invoke, federated branch, from the peer call on: the call, settlement, the routing
fee, the answer, and `_fed_unwind` (the branch's `finally`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import contextlib
import os
import secrets
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse
import httpx

from aimarket_hub import oracle_paid_tier, provider_request_auth
from aimarket_hub.invoke_outcome import classify_invoke_outcome
from aimarket_hub.models import InvocationStat
from aimarket_hub.sandbox_trials import release_sandbox_trial


async def _fed_deliver(d: SimpleNamespace, call: _Call, fed: _Fed):
    """Ask the peer; if it delivered, settle the price and the routing fee, and answer."""
    body, peer, _peer_invoke_endpoint = call.body, fed.peer, d._peer_invoke_endpoint
    fed.started = time.time()

    # Transport selection: a peer that advertises `mcp_endpoint` in its
    # /.well-known/ai-market.json expects the {capability_id, input} envelope
    # there. A peer that advertises none gets the legacy
    # /capabilities/{product}/{cap}/invoke path with the bare input.
    # Resolved from what the peer publishes, for EVERY peer — see
    # _peer_invoke_endpoint for why a category allow-list was the wrong test.
    mcp_endpoint = await _peer_invoke_endpoint(peer)
    if _fed_tool_endpoint(fed):
        # Sold at the tool's own URL on the peer: the bare input goes there (see
        # _fed_call_peer), so nothing below may treat the call as an envelope invoke.
        mcp_endpoint = None
    headers = _fed_peer_headers(d, call, fed)
    if fed.sells and mcp_endpoint:
        # Only where this hub is the seller of record (AIMARKET_SELLS_FOR): it has taken
        # the price or a trial, and the signature tells a gated provider so. For a peer
        # it only brokers, the peer bills the buyer, and signing would vouch for a call
        # nobody paid for. See aimarket_hub/provider_request_auth.py.
        admission = provider_request_auth.signed_headers(
            d.signer, hub_url=d.config.hub_url, audience=mcp_endpoint,
            capability_id=body.capability_id, input_payload=body.input,
        )
        headers.update(admission)
        headers.update(_payer_statement(
            d, call, admission, input_payload=body.input, x402_accepted=fed.x402_accepted,
            hold_rail=fed.hold_rail, reserved=fed.reserved,
        ))

    # Payment is settled and the hold is taken; before crossing the federation,
    # is the request even complete? A second of round trip to be told "lat/lon
    # required" is a second nobody needs to spend.
    short = _refuse_incomplete_input(d, call)
    if short is not None:
        return short

    resp = await _fed_call_peer(d, call, fed, mcp_endpoint, headers)
    passed_on = _fed_passthrough_402(d, call, fed, resp)
    if passed_on is not None:
        return passed_on
    result_data, hearth_bill = _fed_read_result(d, call, fed, resp, mcp_endpoint)

    # Apply the same accepted-output boundary as local invokes.  A federated
    # response that a safety plugin or the built-in gate rejects must neither
    # be billed nor receive a successful final work receipt.
    blocked = _post_check(d, result_data, {
        "product_id": body.product_id,
        "capability_id": body.capability_id,
        "provider_hub": body.source_hub,
    })
    if blocked is not None:
        return blocked

    price, refused = _fed_record(d, call, fed, result_data, hearth_bill)
    _fed_settle_routing_fee(d, call, fed, price, refused)
    return _fed_answer(d, call, fed, resp, result_data, refused)


def _fed_peer_headers(d: SimpleNamespace, call: _Call, fed: _Fed) -> dict[str, str]:
    """What the peer is told about the call: who routes it and how it is paid for."""
    rate_key, x402_raw, payment_signature = call.rate_key, call.x402_raw, call.payment_signature
    x_payment_nonce, x_payment_secret = call.x_payment_nonce, call.x_payment_secret
    fed_peer_key, fed_x402_accepted, fed_price = fed.peer_key, fed.x402_accepted, fed.price
    config, _opaque_buyer = d.config, d._opaque_buyer
    headers: dict[str, str] = {
        "X-AIMarket-Routing-Hub": config.hub_url,
        "X-AIMarket-Routing-Fee": str(config.routing_fee_bps),
        # Every buyer arrives at the peer from this hub's one address, so a peer that
        # rate-limits per address gave all of our buyers one shared bucket: one of them
        # could spend it for everybody. This names the buyer to the peer without saying
        # who they are — see _opaque_buyer.
        "X-AIMarket-Buyer": _opaque_buyer(rate_key),
    }
    # Upstream peers (ATLAS, oracles, …) do not share this hub's payment ledger.
    # Forwarding the buyer's X-Payment-Channel there is meaningless and leaves the
    # peer on a shared IP free-tier that exhausts quickly. Prefer a stable hub
    # federation visitor, or an optional hub-owned peer channel when configured.
    peer_ch = (os.environ.get("AIMARKET_PEER_PAYMENT_CHANNEL") or "").strip()
    peer_sec = (os.environ.get("AIMARKET_PEER_PAYMENT_CHANNEL_SECRET") or "").strip()
    if fed_peer_key:
        # The peer authenticates the hub even when a buyer's transfer pays.
        # Payment verification still takes precedence on the receiving side.
        headers["X-API-Key"] = fed_peer_key
    settled_here = bool(fed_x402_accepted and fed_x402_accepted.get("ok"))
    if x402_raw and (settled_here or not fed_peer_key):
        # Seller-direct: the buyer paid the listing's payout_address.
        # Forward the proof so a hearth (HESTIA) can verify the same
        # transfer. Do not substitute a sandbox visitor — that would
        # drop the payment and re-bill the buyer.
        #
        # Next to OUR key only when this hub settled that payment on this
        # request: the peer reads "key + payment" as "the hub verified this
        # against its own invoice". Forwarded unverified (a sandbox call, a
        # zero price, rails off) it let a caller with nobody's secret redeem —
        # or burn — a payment someone else made.
        headers["X-Payment"] = x402_raw
        headers["X-PAYMENT"] = x402_raw
        if payment_signature:
            headers["PAYMENT-SIGNATURE"] = payment_signature
        if settled_here:
            # Name the authorization this hub verified (its own invoice's nonce):
            # the peer claims that payment, not the whole transaction. The buyer's
            # secret stays here — it opens OUR invoice, nobody else's business.
            if fed_x402_accepted.get("nonce"):
                headers["X-Payment-Nonce"] = str(fed_x402_accepted["nonce"])
        else:
            if x_payment_nonce:
                headers["X-Payment-Nonce"] = x_payment_nonce
            if x_payment_secret:
                # A hearth that minted the quote (its own till) settles only for the
                # holder of the secret its nonce commits to — the nonce itself is
                # public on chain. The buyer got the secret in that hearth's 402.
                headers["X-Payment-Secret"] = x_payment_secret
    elif fed_peer_key:
        # The only header here that can actually settle: this hub's own credit
        # account on the peer. The buyer paid us; we pay them.
        headers["X-API-Key"] = fed_peer_key
        # What this hub charged its buyer for the call. A hearth selling a tenant
        # on its owner's behalf (hestia/hub_billing.py) refuses a call that earned
        # the owner nothing — a free trial — rather than serve it unpaid.
        headers["X-AIMarket-Hub-Charged"] = f"{fed_price:.6f}"
    elif peer_ch:
        headers["X-Payment-Channel"] = peer_ch
        if peer_sec:
            headers["X-Payment-Channel-Secret"] = peer_sec
    else:
        import hashlib as _hashlib

        fed_visitor = (os.environ.get("AIMARKET_FEDERATION_VISITOR") or "").strip() or (
            "hub-fed-" + _hashlib.sha256((config.hub_url or "hub").encode()).hexdigest()[:20]
        )
        headers["X-AIMarket-Sandbox-Visitor"] = fed_visitor
    return headers


def _fed_tool_endpoint(fed: _Fed) -> str:
    """The peer's own URL for this tool (Capability.peer_endpoint), or "".

    Checked against the peer's origin again on every call, not only when the crawl indexed
    it: the row is ours, but what makes it safe to call is that it sits on the peer, and a
    row written by an older hub, or edited, must not send a buyer's call anywhere else.
    """
    url = str(getattr(fed.cap, "peer_endpoint", "") or "").strip()
    if not url or fed.peer is None:
        return ""
    from aimarket_hub.federation_transport import peer_tool_endpoint

    return url if peer_tool_endpoint({"endpoint": url}, fed.peer.url) == url else ""


async def _fed_call_peer(d: SimpleNamespace, call: _Call, fed: _Fed, mcp_endpoint: Any,
                         headers: dict[str, str]):
    body, peer, config, _is_safe_path = call.body, fed.peer, d.config, d._is_safe_path
    # ── Transport (the ONLY part that differs between peer kinds) ──────────
    # Everything after this — 402 passthrough, error mapping, envelope
    # normalization, stats, routing fee, return — is shared. It used to live
    # inside the legacy `else`, so an oracle peer fell out of the handler with no
    # return at all: HTTP 200 `null`, no invocation recorded, no routing fee
    # collected, and the `if mcp_endpoint` normalization below was dead code
    # (mcp_endpoint is falsy by construction inside that branch).
    try:
        from aimarket_hub.outbound_http import safe_post

        # A broker's routing fee is not payment for the oracle's computation.
        oracle_paid = bool((fed.sells or fed.resells) and oracle_paid_tier.funded(
            price=fed.price, sandbox=call.sandbox_mode, reserved=fed.reserved,
            hold_rail=fed.hold_rail, x402_accepted=fed.x402_accepted,
        ))
        tool_endpoint = _fed_tool_endpoint(fed)
        if tool_endpoint:
            # An x402 seller that answers at each tool's own URL and has no invoke route
            # (mach402.dev, agent-exec.448c.org). Same bare input as the legacy path, and the
            # same 402 passthrough and result handling below.
            resp = await safe_post(tool_endpoint, json=body.input, headers=headers, oracle_paid=oracle_paid)
        elif mcp_endpoint:
            # `source_hub` tells the far side where the call came from — EXCEPT on a
            # peer hub's own /invoke, where that field selects the peer's routing
            # branch. Sending our URL there asks it to route the call back to us,
            # which is a loop, not a purchase; "local" asks it to serve its own
            # capability, which is what was bought.
            to_peer_hub = mcp_endpoint.rstrip("/").endswith("/ai-market/v2/invoke")
            resp = await safe_post(
                mcp_endpoint,
                json={
                    "capability_id": body.capability_id,
                    "input": body.input,
                    "product_id": body.product_id,
                    "source_hub": "local" if to_peer_hub else config.hub_url,
                },
                headers=headers,
                oracle_paid=oracle_paid,
            )
        else:
            # product_id / capability_id are interpolated into the upstream path,
            # so they get the same traversal guard the local branch applies.
            if not _is_safe_path(body.product_id) or not _is_safe_path(body.capability_id):
                raise HTTPException(status_code=400, detail="Invalid product or capability ID")
            provider_url = f"{peer.url}/capabilities/{body.product_id}/{body.capability_id}/invoke"
            resp = await safe_post(provider_url, json=body.input, headers=headers, oracle_paid=oracle_paid)
    except ValueError as exc:
        # ONLY safe_post's own refusal reaches here: an SSRF-unsafe / blocked-network
        # target, i.e. a request this hub declines to make. That is a client-visible
        # 400. A malformed provider RESPONSE is a different fault and maps to 502
        # below — the two must not share this handler (they did before, so a peer
        # returning non-JSON was reported to the caller as their own bad request).
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Provider unreachable: {exc}") from exc
    return resp


def _fed_passthrough_402(d: SimpleNamespace, call: _Call, fed: _Fed, resp: Any):
    """The peer's own 402, passed on verbatim — or a 502 when it was this hub's to pay."""
    request, peer, fed_resells = call.request, fed.peer, fed.resells
    logger, _peer_payment_headers = d.logger, d._peer_payment_headers
    # ── Shared settlement tail ─────────────────────────────────────────────
    if resp.status_code == 402:
        # Payment passthrough, identical for both transports: the peer priced the
        # call and wants payment, no work was performed, so we charge no routing
        # fee and record no invocation. A non-JSON 402 body still surfaces as a 402
        # (the status is the signal) rather than becoming a confusing 502.
        try:
            content = resp.json()
        except ValueError:
            content = {
                "success": False,
                "error": "payment_required",
                "detail": f"peer {peer.url} returned 402 with a non-JSON body",
                "protocol_version": "v2",
            }
        if fed_resells:
            # We were supposed to be the one paying. A 402 here is OUR account at the
            # peer being empty or refused, not the buyer's problem — and passing the
            # peer's terms back would tell the buyer to go fund an account somewhere
            # they never chose to deal with. The reservation is released by the
            # `finally`, so this costs them nothing.
            logger.error(
                "resale: peer %s refused this hub's own credit key with 402 — "
                "top up the hub's account there (AIMARKET_PEER_API_KEYS)", peer.url,
            )
            request.state.x402_passthrough = True
            return JSONResponse(status_code=502, content={
                "success": False,
                "error": "upstream_unpaid",
                "detail": (
                    f"this hub resells {peer.url} and its account there could not pay "
                    "for the call — nothing was charged to you"
                ),
                "protocol_version": "v2",
            })
        # This 402 is the PEER's, verbatim. Enriching it would replace their payment
        # terms with ours — telling the payer to send our amount to our address for
        # someone else's capability. Mark it so the x402 middleware leaves it alone.
        request.state.x402_passthrough = True
        # Verbatim includes its headers: an x402 V2 seller answers with an empty body
        # and the whole offer in PAYMENT-REQUIRED, so forwarding the body alone handed
        # the buyer `{}` and no way to pay (2026-10-14). A client that reads only the
        # body — an agent behind the MCP gateway — gets the same offer decoded into it:
        # the seller's own terms, added, never ours.
        passed = _peer_payment_headers(resp)
        if isinstance(content, dict) and not content.get("accepts"):
            from aimarket_hub.federation_assay import x402_header_offer

            offer = x402_header_offer(passed)
            if offer and isinstance(offer.get("accepts"), list):
                content = {**content, **{k: offer[k] for k in
                                         ("x402Version", "accepts", "resource", "error")
                                         if k in offer}}
        return JSONResponse(status_code=402, content=content, headers=passed)
    return None


def _fed_read_result(d: SimpleNamespace, call: _Call, fed: _Fed, resp: Any, mcp_endpoint: Any):
    """The peer's answer as an object envelope, priced as this hub charged it."""
    fed_sells, fed_resells, fed_price = fed.sells, fed.resells, fed.price
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Provider returned {resp.status_code}",
        )

    try:
        result_data = resp.json()
    except ValueError as exc:
        # Provider fault, not caller fault → 502 (see the ValueError note above).
        raise HTTPException(
            status_code=502,
            detail=f"Provider returned a non-JSON body ({resp.status_code})",
        ) from exc
    if not isinstance(result_data, dict):
        # The accounting below is keyed on an object envelope. Refuse rather than
        # crash on a bare list/scalar body.
        raise HTTPException(
            status_code=502,
            detail="Provider returned a non-object JSON body",
        )
    # A hearth's attestation of whose agent did the work, for this hub only: it is
    # read at capture below and never goes on to the buyer.
    hearth_bill = result_data.pop("hub_billing", None)

    # Normalize the AIMarket-v2 oracle envelope to the fields the hub's
    # accounting/return path expects (it has `ok`/`receipt`, not top-level
    # `success`/`latency_ms`/`price_usd`). This now actually runs for the
    # mcp_endpoint transport — which is the only place it was ever meant to.
    if mcp_endpoint:
        rcpt = result_data.get("receipt") or {}
        if not isinstance(rcpt, dict):
            rcpt = {}
        result_data.setdefault("success", bool(result_data.get("ok", True)))
        result_data.setdefault("latency_ms", rcpt.get("latency_ms", 0))
        result_data.setdefault("price_usd", rcpt.get("price_usd", 0))

    # What the BUYER is told they paid must be what this hub actually charged them.
    # `price_usd` above is the peer's self-reported number, and a peer that does not
    # bill reports none — so a sale settled at the list price came back to the caller
    # as `"price_usd": 0` while their balance went down. Measured on a real call:
    # $0.004 debited, zero reported. Same defect the invocation stat already carries a
    # fix for, on the path the buyer actually reads.
    #
    # Only where this hub is the seller of record. For a third-party peer that bills
    # the buyer itself, the peer's own number is the true one and must not be
    # overwritten with ours.
    if fed_sells or fed_resells:
        result_data["price_usd"] = fed_price
    return result_data, hearth_bill


def _fed_record(d: SimpleNamespace, call: _Call, fed: _Fed, result_data: dict[str, Any],
                hearth_bill: Any):
    """Classify the answer, capture the hold if the peer delivered, and record the call."""
    body, credits_ledger, peer = call.body, call.credits_ledger, fed.peer
    fed_sells, fed_resells, fed_price, fed_started = fed.sells, fed.resells, fed.price, fed.started
    fed_reserved, fed_nonce, fed_hold_rail = fed.reserved, fed.nonce, fed.hold_rail
    db, logger, _as_float, _observe_answer = d.db, d.logger, d._as_float, d._observe_answer
    _MAX_REPORTED_PRICE_USD, _MAX_REPORTED_LATENCY_MS = d._MAX_REPORTED_PRICE_USD, d._MAX_REPORTED_LATENCY_MS
    _credit_hearth_owner = d._credit_hearth_owner
    # A peer controls these numbers, so coerce defensively: a string/None price
    # would otherwise blow up the fee arithmetic (500) or the stat insert, and a
    # merely huge finite latency (1e30) is fatal to the SQLite INTEGER column.
    price = _as_float(result_data.get("price_usd"), max_value=_MAX_REPORTED_PRICE_USD)
    # ── The stat records what THIS hub settled, never the peer's word ──────────
    # Same rule the AWR receipt below already follows, and the same number the local
    # branch records. Where this hub is the seller of record (AIMARKET_SELLS_FOR),
    # `fed_price` IS the charge — 0 for a sandbox/crypto-off call, the list price for
    # a paid one — and it is captured a few lines below BEFORE this row is written.
    # Peers that answer with a bare product envelope carry no price at all
    # (ATLAS returns `{"ok": …}`, BASANOS `{"success": true, "result": …}`), so a
    # $0.02 sale of theirs reached /stats/live, the live feed and every revenue
    # aggregate over `invocation_stats` as $0.00 — while the buyer's channel was
    # correctly debited. `price` (the peer's self-reported number) stays as it was:
    # it is only the fee-basis cap below, which is exactly where NOT trusting the
    # peer is the point.
    # ── Did the peer refuse? ──────────────────────────────────────────────
    # `success: false` — the `ok: false` the envelope above is normalized from —
    # is an honest refusal: ATLAS answers `point_id required` that way when the
    # buyer's input is incomplete, GAIA when an upstream relay is offline. The
    # local branch has never billed one (it fails closed and hands the hold back).
    # This branch captured the hold unconditionally a few lines below and marked
    # the sandbox trial as earned on the way out, so the SAME refusal cost a
    # paying buyer the full list price and a free caller one of their three
    # trials. The peer's envelope still goes back untouched with its
    # `refuse_reason` — that is what tells the caller what to fix — and only the
    # settlement changes.
    #
    # EXPLICIT false only, exactly as the local branch reads it: a legacy
    # factory-product peer returns a bare result with no `success`/`ok` field at
    # all, and treating a missing flag as a refusal would stop paying for work
    # those peers really did.
    refused = result_data.get("success") is False or result_data.get("ok") is False
    schema = None
    with contextlib.suppress(Exception):
        listed_cap = db.get_capability(
            body.product_id, body.capability_id, source_hub=peer.url,
        )
        if listed_cap is None:
            listed_cap = db.find_by_capability_id(body.capability_id)
        schema = getattr(listed_cap, "input_schema", None)
    outcome = classify_invoke_outcome(
        delivered=not refused,
        refuse_reason=str(
            result_data.get("refuse_reason") or result_data.get("error") or ""
        ),
        input_payload=body.input,
        input_schema=schema,
    )
    charged_price = 0.0 if refused else (
        _as_float(fed_price, max_value=_MAX_REPORTED_PRICE_USD) if fed_sells else price
    )
    # Latency has the same shape — those peers report none, and the hub has been
    # timing the round trip since `fed_started`. A number the peer omitted is
    # unknown, not 0 ms.
    peer_latency_ms = int(_as_float(
        result_data.get("latency_ms"), max_value=_MAX_REPORTED_LATENCY_MS,
    ))
    stat = InvocationStat(
        capability_id=body.capability_id,
        product_id=body.product_id,
        source_hub=body.source_hub,
        price_usd=charged_price,
        latency_ms=peer_latency_ms or int((time.time() - fed_started) * 1000),
        success=outcome == "ok",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        consumer_hub=call.consumer_hub_label,
        outcome=outcome,
        caller_class=_caller_class_now(d, call),
        purpose=body.purpose,
    )
    # The peer did the work, so the hold becomes a debit. Fail CLOSED if the ledger
    # refuses: withholding the output is better than serving billable work the ledger never
    # recorded as paid, and the reservation is handed back below.
    # Not on a refusal: `fed_settled` stays false, so the `finally` releases the
    # hold and the buyer pays nothing.
    if fed_reserved and not refused:
        fed_capture = (
            credits_ledger.capture_hold(fed_nonce)
            if fed_hold_rail == "credits" and credits_ledger is not None
            else invoke.capture_hold(fed_nonce)
        )
        if fed_capture.get("error"):
            logger.error(
                "federated invoke: capture of reservation %s failed: %s",
                fed_nonce, fed_capture.get("error"),
            )
            raise HTTPException(
                status_code=502,
                detail="settlement failed: reservation could not be captured",
            )
        fed.settled = True
        if hearth_bill is not None and (fed_sells or fed_resells) and fed_price > 0:
            _credit_hearth_owner(peer, hearth_bill, body.capability_id, fed_price)

    # Bookkeeping must never be able to destroy delivered work. At this point the
    # peer has answered, the money side is settled, and the caller is owed the
    # result — but `record_invocation` writes a row, and on 2026-09-05 that write
    # raised `sqlite3.OperationalError: database is locked` on
    # independentai.network/hub and turned EIGHT OUT OF EIGHT successful federated
    # invokes into a bare 500. The caller lost an answer that had already been
    # fetched from the peer, over a metrics row.
    #
    # A lost stat is a hole in a chart. A lost answer is the product failing.
    try:
        db.record_invocation(stat)
    except Exception as exc:
        logger.error(
            "invocation stat NOT recorded for %s (the call itself succeeded): %s",
            getattr(stat, "capability_id", "?"), exc,
        )
    if outcome == "ok" and not refused:
        _observe_answer(db, body.source_hub, body, result_data)
    return price, refused


def _fed_settle_routing_fee(d: SimpleNamespace, call: _Call, fed: _Fed, price: float,
                            refused: bool) -> None:
    body, credit_account, credits_ledger = call.body, call.credit_account, call.credits_ledger
    x_payment_channel, x_payment_channel_secret = call.x_payment_channel, call.x_payment_channel_secret
    peer, listed, listed_price, fed_settled, fed_sells = fed.peer, fed.listed, fed.listed_price, fed.settled, fed.sells
    fed_fee_nonce, fed_fee_rail, fed_fee_reserved_usd = fed.fee_nonce, fed.fee_rail, fed.fee_reserved_usd
    db, config, logger = d.db, d.config, d.logger
    _as_float, _MAX_REPORTED_PRICE_USD = d._as_float, d._MAX_REPORTED_PRICE_USD
    # ── Routing fee: the basis is the PUBLISHED price, never the peer's word ──
    # The fee is a percentage of `price_usd`, and `price_usd` arrives in the peer's
    # own response body — so billing on it let the remote side choose how much of
    # THIS hub's consumer's channel to spend. Verified against the pre-cap code: a
    # peer answering `price_usd: 49000` took $490 out of a $500 channel on a single
    # invoke, for a capability the buyer never saw a price for.
    # The consent anchor is what this hub itself published for the routed
    # capability (the crawler stores the peer's catalog under source_hub=peer.url,
    # which is exactly what /catalog served the buyer). Cap the basis there; with no
    # catalogued price there is no agreed amount, so we charge nothing rather than
    # trusting the peer — fail closed on the money, not on the routing.
    # `listed` / `listed_price` were resolved before the peer was called, because
    # the fee is reserved up front now. Re-resolve only if that pass skipped it
    # (seller-of-record, sandbox, or a zero fee schedule), so a hub that charges
    # nothing still logs the same diagnostics it always did.
    if listed is None and listed_price == 0.0:
        listed = db.get_capability(
            body.product_id, body.capability_id, source_hub=peer.url,
        )
        if listed is None:
            # Same fallback the local branch makes for a caller that omits or
            # mis-specifies product_id — but scoped to the ROUTED peer's own listings,
            # so it can never resolve to a pricier capability published by someone else.
            listed = next(
                (c for c in db.list_capabilities(source_hub=peer.url)
                 if c.capability_id == body.capability_id),
                None,
            )
        listed_price = _as_float(
            getattr(listed, "price_per_call_usd", 0.0),
            max_value=_MAX_REPORTED_PRICE_USD,
        ) if listed is not None else 0.0
    # No delivery, no brokerage: a refusal earns this hub nothing either, so the
    # basis is zero regardless of what the peer put in its body.
    fee_basis = 0.0 if refused else min(price, listed_price)
    if listed is None and price > 0:
        logger.warning(
            "routing_fee: peer %s reported $%.6f for %s/%s but this hub has no "
            "catalogued price for it — charging no routing fee",
            peer.url, price, body.product_id, body.capability_id,
        )
    elif price > listed_price:
        logger.warning(
            "routing_fee: peer %s reported $%.6f for %s/%s over the catalogued "
            "$%.6f — fee basis capped at the published price",
            peer.url, price, body.product_id, body.capability_id, listed_price,
        )

    routing_fee = round(fee_basis * config.routing_fee_bps / 10000, 6)
    if fed_settled and fed_sells:
        # This hub already billed the full list price for a peer that does not charge, so
        # it is the seller here, not a broker between two parties. Taking a routing fee on
        # top would bill the same call twice.
        #
        # NOT true of a resale (`fed_resells`): there the hub pays the peer its price out
        # of the hub's own account and bills the buyer the same catalogued number, so the
        # fee is the entire margin. Zeroing it there would mean brokering at cost.
        routing_fee = 0.0
    # Settle the reservation taken before routing. Three outcomes, and none of
    # them is "serve anyway and log": captured when the peer delivered at the price
    # we quoted, released when it refused or turned out to be free, and
    # released-then-debited for the smaller amount when the peer charged less than
    # its own catalogue said.
    if fed_fee_nonce:
        _fee_ledger_capture = (
            credits_ledger.capture_hold
            if fed_fee_rail == "credits" and credits_ledger is not None
            else invoke.capture_hold
        )
        _fee_ledger_release = (
            credits_ledger.release_hold
            if fed_fee_rail == "credits" and credits_ledger is not None
            else invoke.release_hold
        )
        if routing_fee <= 0:
            _fee_ledger_release(fed_fee_nonce)
        elif abs(routing_fee - fed_fee_reserved_usd) < 1e-9:
            fee_capture = _fee_ledger_capture(fed_fee_nonce)
            if fee_capture.get("error"):
                logger.error(
                    "routing_fee: capture of reservation %s failed: %s",
                    fed_fee_nonce, fee_capture.get("error"),
                )
                raise HTTPException(
                    status_code=502,
                    detail="settlement failed: routing fee could not be captured",
                )
            logger.info("routing_fee: collected $%.6f (%d bps) via %s",
                        routing_fee, config.routing_fee_bps, fed_fee_rail)
        else:
            _fee_ledger_release(fed_fee_nonce)
            if fed_fee_rail == "credits" and credits_ledger is not None:
                fee_result = credits_ledger.debit(
                    credit_account, routing_fee,
                    receipt_id=f"route_{secrets.token_hex(8)}", note="routing fee",
                )
            else:
                fee_result = invoke.debit_channel(
                    x_payment_channel, routing_fee,
                    receipt_id=f"route_{secrets.token_hex(8)}",
                    secret=x_payment_channel_secret or "",
                )
            if fee_result.get("error"):
                logger.error("routing_fee: could not debit %s via %s: %s",
                             routing_fee, fed_fee_rail, fee_result.get("error"))
            else:
                logger.info("routing_fee: collected $%.6f (peer charged under its "
                            "catalogued price) via %s", routing_fee, fed_fee_rail)
        fed.fee_nonce = ""


def _fed_answer(d: SimpleNamespace, call: _Call, fed: _Fed, resp: Any, result_data: dict[str, Any],
                refused: bool):
    body, config, plugins, _peer_payment_headers = call.body, d.config, d.plugins, d._peer_payment_headers
    fed_sandbox_meta, federated_verify_env, fed_started = fed.sandbox_meta, fed.verify_env, fed.started
    fed_price, fed_list_price, fed_nonce, fed_settled = fed.price, fed.list_price, fed.nonce, fed.settled
    result_data["routed_via"] = config.hub_url
    result_data["routing_fee_bps"] = config.routing_fee_bps
    if fed_sandbox_meta:
        result_data["sandbox"] = fed_sandbox_meta
    if federated_verify_env is not None:
        result_data["verification"] = federated_verify_env

    # The routing hub now issues the same portable AWR class for peer work as
    # for local work.  It signs the peer envelope (including its own gateway
    # receipt/attestation) while naming the actual provider hub.  Charged price
    # is the amount THIS hub settled, never the peer's self-reported list price.
    if bool(result_data.get("success", False)):
        fed_elapsed_ms = int((time.time() - fed_started) * 1000)
        receipt_artifacts = plugins.run_receipt_hooks(result_data, {
            "product_id": body.product_id,
            "capability_id": body.capability_id,
            "input": body.input,
            "provider_hub": body.source_hub,
            "latency_ms": fed_elapsed_ms,
            "price_usd": fed_price,
            "list_price_usd": fed_list_price,
            "status": "succeeded",
            "nonce": fed_nonce,
            "settlement_status": "captured" if fed_settled else "free",
            "gateway_receipt": result_data.get("receipt"),
        })
        provenance_receipt = receipt_artifacts.get("provenance")
        if provenance_receipt:
            result_data["provenance_receipt"] = provenance_receipt
    # The trial is earned by a DELIVERED result, not by a response. Set on the way
    # out rather than at the point of consumption, because everything between them
    # can still fail — and left false for a refusal, so the `finally` hands the
    # allowance back the way ATLAS's own gate hands back its own.
    fed.trial_delivered = not refused
    # A seller paid directly over x402 answers with its settlement (PAYMENT-RESPONSE);
    # x402 clients read it to confirm the payment, so it travels back with the result.
    paid_headers = _peer_payment_headers(resp)
    if paid_headers:
        from fastapi.encoders import jsonable_encoder

        return JSONResponse(content=jsonable_encoder(result_data), headers=paid_headers)
    return result_data


def _fed_unwind(d: SimpleNamespace, call: _Call, fed: _Fed) -> None:
    """Hand back what an undelivered call holds: the X-Payment claim, the trial, the escrow
    window, the price reservation and the routing-fee reservation."""
    credits_ledger, logger, _release_market_payment = call.credits_ledger, d.logger, d._release_market_payment
    fed_trial_delivered, fed_x402_accepted, fed_trial_visitor = (
        fed.trial_delivered, fed.x402_accepted, fed.trial_visitor)
    fed_authorization, fed_settled, fed_reserved = fed.authorization, fed.settled, fed.reserved
    fed_nonce, fed_hold_rail, fed_fee_nonce, fed_fee_rail = fed.nonce, fed.hold_rail, fed.fee_nonce, fed.fee_rail
    if not fed_trial_delivered:
        # Seller-direct has no hold to release — the money went to the seller — but
        # the CLAIM was burned at settlement. The local branch returns it on every
        # undelivered exit; this branch never did, so a peer 502, an incomplete input
        # or a refusal consumed the buyer's tx hash for a call that never ran.
        _release_market_payment(fed_x402_accepted)
    if fed_trial_visitor and not fed_trial_delivered:
        # Same discipline, and same rule about `finally`: never raise out of it, never
        # be silent about a failure to hand the reservation back.
        try:
            released = release_sandbox_trial(fed_trial_visitor)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "federated invoke: releasing the sandbox trial for %s raised: %s",
                fed_trial_visitor, exc,
            )
        else:
            if released.get("error"):
                logger.error(
                    "federated invoke: failed to release the sandbox trial for %s: %s",
                    fed_trial_visitor, released["error"],
                )
    if fed_authorization is not None and not fed_settled:
        _fed_withdraw_window(d, fed, "the call was not delivered")
    if fed_reserved and not fed_settled:
        # Must not raise out of `finally` — that would mask the real error — but must
        # never be silent either.
        try:
            fed_release = (
                credits_ledger.release_hold(fed_nonce)
                if fed_hold_rail == "credits" and credits_ledger is not None
                else invoke.release_hold(fed_nonce)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "federated invoke: release of reservation %s raised: %s",
                fed_nonce, exc,
            )
        else:
            if fed_release.get("error"):
                logger.error(
                    "federated invoke: failed to release reservation %s: %s",
                    fed_nonce, fed_release.get("error"),
                )
    # The routing-fee reservation has the same rule as the price reservation: it is
    # taken before the peer is called, so every exit between the reservation and the
    # settlement above must hand it back. `fed_fee_nonce` is cleared once settled, so
    # this only fires on the paths that never got there.
    if fed_fee_nonce:
        try:
            fee_release = (
                credits_ledger.release_hold(fed_fee_nonce)
                if fed_fee_rail == "credits" and credits_ledger is not None
                else invoke.release_hold(fed_fee_nonce)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "federated invoke: release of routing-fee reservation %s raised: %s",
                fed_fee_nonce, exc,
            )
        else:
            if fee_release.get("error"):
                logger.error(
                    "federated invoke: failed to release routing-fee reservation %s: %s",
                    fed_fee_nonce, fee_release.get("error"),
                )


# Imported after the phases on purpose: invoke.py imports these modules to call the
# branches, and any of them may load first. The channel-ledger functions are read as
# invoke.<name> at call time because that is where they are patched.
from aimarket_hub.hub_routes import invoke  # noqa: E402
from aimarket_hub.hub_routes.invoke import (  # noqa: E402
    _Call,
    _Fed,
    _caller_class_now,
    _post_check,
    _refuse_incomplete_input,
)
from aimarket_hub.hub_routes.invoke_parts.local_delivery import _payer_statement  # noqa: E402
from aimarket_hub.hub_routes.invoke_parts.federated_admission import (  # noqa: E402
    _fed_withdraw_window,
)
