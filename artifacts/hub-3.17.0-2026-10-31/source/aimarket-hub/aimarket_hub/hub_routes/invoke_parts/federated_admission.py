"""POST /invoke, federated branch, up to the peer call: a capability another hub serves.

`_invoke_federated` runs the phases in order: the peer, the quote and routing fee, the escrow
authorization, payment or trial, the routing-fee reservation; then, inside one try whose
`finally` is `_fed_unwind`, it hands over to the delivery phases in `federated_delivery`.
"""

from __future__ import annotations

from types import SimpleNamespace
import contextlib
import secrets

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from aimarket_hub import credits, verified_settlement
from aimarket_hub.sandbox_trials import consume_sandbox_trial, free_tier_covers, model_budget_refusal


async def _invoke_federated(d: SimpleNamespace, call: _Call):
    """Route to the peer; bill where this hub is the seller, broker where it is not."""
    fed = _Fed()
    _fed_peer(d, call, fed)
    await _fed_quote(d, call, fed)
    for phase in (_fed_price_ceiling, _fed_escrow_authorization, _fed_seller_direct,
                  _fed_trial_or_hold, _fed_reserve_routing_fee):
        refused = phase(d, call, fed)
        if refused is not None:
            return refused

    # Everything from here to the return is wrapped so the hold is ALWAYS handed back.
    # There are nine exits between this point and the response — a peer 402, an unreachable
    # provider, a non-JSON body, an SSRF refusal, a failed capture — and an unreleased
    # reservation is the buyer's money in limbo that also blocks channel close. The local
    # branch above has the same guard for the same reason; adding an exit here without one
    # would be silent, so the shape is structural rather than a release at each return.
    try:
        return await _fed_deliver(d, call, fed)
    finally:
        _fed_unwind(d, call, fed)


def _fed_peer(d: SimpleNamespace, call: _Call, fed: _Fed) -> None:
    """The admitted peer the call is routed to."""
    db, body = d.db, call.body
    # Federated invoke — route to provider hub.
    # Pay-on-Verified is a LOCAL-settlement feature (the escrow hold and the
    # Metis verdict both live on this hub). A verify block on a federated invoke
    # cannot be honoured — the routing fee is debited immediately and the remote
    # hub owns execution — so surface an explicit skipped envelope rather than
    # silently charging the buyer as if verification applied.
    if body.verify is not None and getattr(body.verify, "requested", False):
        fed.verify_env = verified_settlement.skipped_envelope_for(
            body.verify, reason="federated_unsupported", capability_id=body.capability_id,
        )
    peer = db.get_peer(body.source_hub)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer hub not found")
    # Existing is not the same as admitted. A peer ROW needs no credential at all to
    # appear: POST /ai-market/v2/federation/announce without an admin bearer, or merely a
    # GET of our own well-known carrying an `X-AIMarket-Crawler` header — both land
    # `status="pending"`. Quarantine means nothing this peer claims is indexed, listed or
    # served, and this branch nonetheless made it a live outbound transport for an
    # anonymous caller, with that caller's `input` in the body.
    #
    # The gate is STATUS, deliberately not `trusted`. `trusted` reads like the right flag
    # ("operator-approved … manifests indexed only if True") and `admit_peer` and the
    # admin trust route both set it — but the admin ANNOUNCE door does not, so requiring
    # it here would refuse the operator's own documented "add a peer directly" flow.
    # `status == "active"` is what actually separates an admitted peer from a quarantined
    # one. See SECURITY notes: that `trusted` is left False by one of the two admin doors
    # is its own inconsistency, and not one to change from inside the invoke path.
    peer_status = str(getattr(peer, "status", "active") or "active")
    if peer_status != "active":
        raise HTTPException(
            status_code=403,
            detail=f"peer is not admitted for routing (status={peer_status})",
        )
    fed.peer = peer


async def _fed_quote(d: SimpleNamespace, call: _Call, fed: _Fed) -> None:
    """What the routed capability costs here, who bills it, and the routing fee on top."""
    body, request, sandbox_mode, price_rail_active = call.body, call.request, call.sandbox_mode, call.price_rail_active
    x402_raw, credit_account, x_payment_channel = call.x402_raw, call.credit_account, call.x_payment_channel
    peer, db, config = fed.peer, d.db, d.config
    _bind_listing_payee, _peer_sells_direct = d._bind_listing_payee, d._peer_sells_direct
    _as_float, _MAX_REPORTED_PRICE_USD = d._as_float, d._MAX_REPORTED_PRICE_USD
    # ── Trial, then payment, for a capability this hub BROKERS ────────────────
    # Until 2026-07-30 neither ran here: the payment gate lives in the `local` branch
    # above, and this branch only forwarded X-Payment-Channel and passed a peer's own 402
    # through. That was coherent for a third-party peer — it bills, this hub takes
    # `routing_fee_bps` — and wrong for the peers that actually exist. `oracle_core`
    # enforces nothing (no 402, no price check anywhere in it), so 42 of the 47 catalogued
    # capabilities were free to call while advertising a price, and the 1% routing fee was
    # a broker's cut of a sale that never happened.
    #
    # All the payment machinery — channels, holds, the ledger, escrow — is in this hub.
    # Building it into seventeen oracles to make them bill their own operator would be
    # absurd, so for a peer that does not charge, THIS HUB is the seller of record.
    #
    # The trial comes first and is the whole reason this is safe to turn on: a bot that
    # has just installed the bridge still gets its free calls, and only then meets a 402
    # that says what to do. Without it, switching the gate on would close the on-ramp the
    # bridge exists to open.
    # Scoped to the ROUTED peer, exactly like the `listed` lookup below — whose comment
    # already says it "can never resolve to a pricier capability published by someone
    # else". `find_by_capability_id` ignores product_id AND source_hub and returns
    # `ORDER BY trust_score DESC LIMIT 1`, and capability_ids collide here by design (its
    # own docstring says it exists because federated oracle caps share ids). So the price
    # QUOTED, HELD and CAPTURED could come from a different peer's row: a $7.50 capability
    # was billed at another peer's $0.01, and where that other row was priced 0 the
    # `fed_price > 0` gate never fired and the paid call was served for nothing.
    fed_cap = db.get_capability(
        body.product_id, body.capability_id, source_hub=peer.url,
    )
    if fed_cap is None:
        fed_cap = next(
            (c for c in db.list_capabilities(source_hub=peer.url)
             if c.capability_id == body.capability_id),
            None,
        )
    fed_list_price = float(getattr(fed_cap, "price_per_call_usd", 0.0) or 0.0) if fed_cap else 0.0
    if fed_cap is not None:
        _bind_listing_payee(request, fed_cap)
    # Only for a peer this hub is DECLARED seller for (AIMARKET_SELLS_FOR). For anyone else
    # the broker shape is untouched: the peer bills, this hub forwards the channel and takes
    # its routing fee, and a 200 from the peer says nothing about whether it charged.
    fed_sells = config.sells_on_behalf_of(body.source_hub)
    # A key at the peer means this hub can actually settle with it, so it may resell:
    # charge the buyer the catalogued price, pay the peer out of its own account there,
    # keep the routing fee as the spread. Without one, a peer that charges cannot be
    # bought through this hub at all — its 402 lands on a buyer with no account there.
    fed_peer_key = config.peer_api_key(body.source_hub)
    fed_resells = bool(fed_peer_key)
    fed_price = 0.0 if (
        sandbox_mode or not price_rail_active or not (fed_sells or fed_resells)
    ) else fed_list_price
    if (fed_sells or fed_resells) and price_rail_active and not sandbox_mode \
            and fed_cap is None:
        # This hub is the one billing, and it has no catalogued price from this peer for
        # this capability. Guessing from another row is what produced the mispricing
        # above; charging 0 would serve a paid capability free. Say so instead.
        raise HTTPException(
            status_code=404,
            detail=(
                f"no catalogued price for {body.capability_id} at {peer.url} — "
                "the peer's catalogue has not been crawled for this capability"
            ),
        )

    listed = None
    listed_price = 0.0
    expected_fee = 0.0
    if not fed_sells and not sandbox_mode and config.routing_fee_bps > 0:
        listed = db.get_capability(
            body.product_id, body.capability_id, source_hub=peer.url,
        )
        if listed is None:
            listed = next(
                (c for c in db.list_capabilities(source_hub=peer.url)
                 if c.capability_id == body.capability_id),
                None,
            )
        listed_price = _as_float(
            getattr(listed, "price_per_call_usd", 0.0),
            max_value=_MAX_REPORTED_PRICE_USD,
        ) if listed is not None else 0.0
        expected_fee = round(listed_price * config.routing_fee_bps / 10000, 6)

    # No routing fee on a direct x402 sale (owner, 2026-10-14). In the broker shape — this
    # hub neither sells for the peer (AIMARKET_SELLS_FOR) nor resells it (a key there) — a
    # priced capability is paid one way only: the buyer pays the seller's own x402 door and
    # this hub relays the offer and the payment. Demanding a fee first made that two
    # payments for one call, the first to us for a sale we take no part in; x402 clients
    # pay one 402, so the sale did not happen (seen end to end on production 2026-10-14).
    # It is waived, for a peer that declares seller-direct payment, when the buyer pays
    # the seller over x402 and when the buyer brings no payment at all, so the seller's
    # door is what they meet. A buyer who brings this
    # hub's own rail (a credit key or a channel) and no x402 payment still pays it — the
    # same as before — though a seller that bills will answer 402, and the hold is
    # released.
    fed_direct_x402 = (
        not fed_sells and not fed_resells and expected_fee > 0
        and (bool(x402_raw) or not (credit_account or x_payment_channel))
        # Only for a peer that says, in its own well-known, that its buyers pay it
        # directly. A peer that bills nobody (an oracle serving its priced catalogue for
        # free) is not a direct sale, and waiving the fee there let a caller who simply
        # sent no payment be brokered for nothing.
        and await _peer_sells_direct(peer)
    )
    if fed_direct_x402:
        expected_fee = 0.0
    fed.cap, fed.list_price, fed.price = fed_cap, fed_list_price, fed_price
    fed.sells, fed.peer_key, fed.resells = fed_sells, fed_peer_key, fed_resells
    fed.listed, fed.listed_price, fed.expected_fee = listed, listed_price, expected_fee


def _fed_price_ceiling(d: SimpleNamespace, call: _Call, fed: _Fed):
    """The total the buyer is charged, and a 409 when it is over their max_price_usd."""
    body, credit_account, x402_raw = call.body, call.credit_account, call.x402_raw
    fed_price, expected_fee, _ceil_to_cents = fed.price, fed.expected_fee, d._ceil_to_cents
    # What the buyer will be charged in total, and therefore what an escrow-backed
    # channel has to authorize. The authorization used to cover `fed_price` alone while
    # the fee was taken separately — so a brokered or resold capability could not be
    # bought on the only funding rail production has: the buyer signed the price, the
    # fee had nothing behind it, and the invoke was refused `routing_fee_unpayable`
    # after the money was already deposited. Quoting one number and charging another is
    # the bug; the quote is the total now, in every 402 on this path.
    #
    # Quantized to whole cents because BOTH ends already are: the ledger bills
    # `max(1, ceil(usd*100))` cents and `escrow_verify.usd_to_base_units` converts the
    # signed amount the same way. Quoting $0.0101 asks the buyer to sign a number their
    # own signature can never match — the verifier demands the $0.02 it ceils to, the
    # client re-signs the quote, and the purchase deadlocks with the deposit already on
    # chain. One number, and it is the one everything downstream rounds to.
    fed_authorized_total = _ceil_to_cents(fed_price + expected_fee)
    fed.authorized_total = fed_authorized_total
    # Credit price and fee are separate millicent holds, not cent-denominated
    # escrow authorizations. Compare the ceiling with the money this rail takes.
    ceiling_total = fed_authorized_total
    if credit_account and not x402_raw:
        ceiling_total = credits.mc_to_usd(credits.usd_to_mc(fed_price) + credits.usd_to_mc(expected_fee))
    elif x402_raw:
        ceiling_total = round(fed_price + expected_fee, 6)
    if body.max_price_usd is not None and ceiling_total > body.max_price_usd:
        return JSONResponse(status_code=409, content={
            "success": False,
            "error": "price_limit_exceeded",
            "detail": "the routed price changed after selection; search again",
            "maximum_price_usd": body.max_price_usd,
            "current_price_usd": ceiling_total,
            "protocol_version": "v2",
        })
    return None


def _fed_escrow_authorization(d: SimpleNamespace, call: _Call, fed: _Fed):
    """The buyer's signed authorization for an escrow-backed channel, and the receipt id."""
    body, crypto_on, sandbox_mode, x_payment_channel = (
        call.body, call.crypto_on, call.sandbox_mode, call.x_payment_channel)
    fed_authorized_total, fed_price, expected_fee = fed.authorized_total, fed.price, fed.expected_fee
    logger = d.logger
    # ── An escrow-backed channel needs a signed authorization HERE too ───────────────
    # The local branch above has required one since the bridge landed; this branch did
    # not, and every capability in the catalogue is federated — so every paid sale took
    # the buyer's cents off-chain with a hub-generated receipt id and left nothing that
    # could ever be collected on chain. `usedAmount` stayed 0 in the escrow, the depositor
    # could reclaim a consumed deposit, and the operator's revenue existed only as
    # `used_cents` in a SQLite file. Found on 2026-08-24 by buying one real invoke and
    # looking for the authorization it should have produced: the ledger showed a captured
    # hold, the bridge store was empty.
    #
    # The receipt id is the buyer's, not ours: the contract's replay key (`usedReceipts`)
    # and the ledger's receipt then are literally the same string and cannot drift.
    if crypto_on and not sandbox_mode and x_payment_channel:
        with contextlib.suppress(Exception):
            fed.escrow_binding = invoke.channel_escrow_binding(x_payment_channel)

    # The TOTAL, not the price: for a brokered peer the price is zero and the fee is
    # the whole charge, and gating on the price skipped the authorization block while
    # the fee block below still demanded one — a 402 telling the buyer to sign
    # something this code would never read.
    if fed.escrow_binding and fed_authorized_total > 0:
        fed_auth_error = None
        if body.payment_authorization is None:
            fed_auth_error = (
                "this channel is backed by an on-chain escrow: a signed "
                "payment_authorization is required for a paid invoke"
            )
        else:
            try:
                from aimarket_hub.escrow_bridge import authorization as bridge_auth
                from aimarket_hub.escrow_bridge import store as bridge_store
            except Exception as exc:
                logger.error(
                    "escrow-backed federated invoke but the bridge is unavailable: %s", exc)
                fed_auth_error = "escrow settlement is not available on this hub"
        if fed_auth_error is None:
            try:
                fed.authorization = bridge_auth.verify_and_store(
                    payload=body.payment_authorization,
                    ledger_channel_id=x_payment_channel,
                    escrow_channel_id=fed.escrow_binding,
                    expected_amount_usd=fed_authorized_total,
                    expected_receipt_id=str(
                        (body.payment_authorization or {}).get("receiptId")
                        or (body.payment_authorization or {}).get("receipt_id")
                        or ""
                    ),
                    authorizations=bridge_store.AuthorizationStore(),
                )
            except Exception as exc:
                fed_auth_error = str(exc)
        if fed_auth_error is not None:
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_authorization_required",
                "detail": fed_auth_error,
                # The TOTAL: sign this, not the list price, or the fee has nothing
                # behind it and the next attempt is refused for the difference.
                "needed": fed_authorized_total,
                "price_usd": fed_price,
                "routing_fee_usd": expected_fee,
                "protocol_version": "v2",
            })

    fed.nonce = (
        fed.authorization.row.receipt_id
        if fed.authorization is not None
        else f"rcpt_{secrets.token_hex(16)}"
    )
    return None


def _fed_withdraw_window(d: SimpleNamespace, fed: _Fed, reason: str) -> None:
    logger = d.logger
    # Same rule as the local branch: the buyer's running-total authorization was
    # stored before the work, so a call that is not delivered leaves it at once and
    # the authorization it replaced is the window's claim again.
    if fed.authorization is None:
        return
    try:
        from aimarket_hub.escrow_bridge import authorization as bridge_auth
        from aimarket_hub.escrow_bridge import store as bridge_store

        bridge_auth.withdraw(fed.authorization.row.receipt_id,
                             bridge_store.AuthorizationStore(), reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.error("federated invoke: withdrawing escrow authorization %s raised: %s",
                     fed.authorization.row.receipt_id[:14], exc)


def _fed_refuse(d: SimpleNamespace, fed: _Fed, response: JSONResponse) -> JSONResponse:
    _fed_withdraw_window(d, fed, "the call was refused before it ran")
    return response


def _fed_seller_direct(d: SimpleNamespace, call: _Call, fed: _Fed):
    """Settle an X-Payment to the seller of a federated sale this hub bills."""
    body, sandbox_mode, credits_on, crypto_on = call.body, call.sandbox_mode, call.credits_on, call.crypto_on
    x402_payment, x402_raw, x_payment_nonce, x_payment_secret = (
        call.x402_payment, call.x402_raw, call.x_payment_nonce, call.x_payment_secret)
    x_payment_channel, credit_account = call.x_payment_channel, call.credit_account
    fed_price, fed_cap, fed_authorization = fed.price, fed.cap, fed.authorization
    _settle_market_payment, _payment_ways = d._settle_market_payment, d._payment_ways
    # Seller-direct (x402 / X-Payment) on a federated sale this hub bills.
    # The local branch settles this before the provider runs; this branch
    # used to ignore the header and unbind the payee, so search advertised
    # a wallet the invoke then called listing_not_sellable.
    if (
        x402_payment is not None
        and fed_price > 0
        and not sandbox_mode
        and fed_cap is not None
        and (x_payment_channel or credit_account or fed_authorization is not None)
    ):
        # One rail per call. Settling the chain AND holding a channel billed one call
        # twice; skipping the hold instead left an escrow authorization "covering" a
        # routing fee nothing ever reserved, so the fee was never collected. Refused
        # before the tx is claimed, so the buyer's payment stays redeemable.
        return _fed_refuse(d, fed, JSONResponse(status_code=400, content={
            "success": False,
            "error": "payment_rails_conflict",
            "detail": "send X-Payment or a payment channel / credit key, not both",
            "protocol_version": "v2",
        }))
    if (
        x402_payment is not None
        and fed_price > 0
        and not sandbox_mode
        and fed_cap is not None
    ):
        fed.x402_accepted = _settle_market_payment(
            raw=x402_raw,
            payload=x402_payment,
            cap=fed_cap,
            price_usd=fed_price,
            capability_id=body.capability_id,
            header_nonce=(x_payment_nonce or "").strip(),
            header_secret=(x_payment_secret or "").strip(),
        )
        if fed.x402_accepted.get("error"):
            return _fed_refuse(d, fed, JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_invalid",
                "detail": fed.x402_accepted["error"],
                "needed": fed_price,
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            }))
        call.consumer_hub_label = _label_x402_paid(d, call)
        call.payer_wallet = str(fed.x402_accepted.get("payer") or "")
    return None


def _fed_trial_or_hold(d: SimpleNamespace, call: _Call, fed: _Fed):
    """The free tier's trial, or the 402, or the hold on the buyer's credits or channel."""
    body, request, sandbox_mode, price_rail_active = call.body, call.request, call.sandbox_mode, call.price_rail_active
    x_sandbox_visitor, client_ip, credits_on, crypto_on = call.x_sandbox_visitor, call.client_ip, call.credits_on, call.crypto_on
    x_payment_channel, x_payment_channel_secret = call.x_payment_channel, call.x_payment_channel_secret
    credit_account, credits_ledger = call.credit_account, call.credits_ledger
    fed_sells, fed_resells, fed_cap, fed_list_price = fed.sells, fed.resells, fed.cap, fed.list_price
    fed_price, expected_fee, fed_authorized_total = fed.price, fed.expected_fee, fed.authorized_total
    fed_x402_accepted, fed_authorization, fed_nonce = fed.x402_accepted, fed.authorization, fed.nonce
    _unbind_payee, _payment_hint, _payment_ways = d._unbind_payee, d._payment_hint, d._payment_ways
    # Resold peers too: this hub pays them out of its own account at the peer, so a
    # visitor that skipped the trial here got unlimited calls on the operator's bill.
    if sandbox_mode and (fed_sells or fed_resells):
        if x_payment_channel:
            return _fed_refuse(d, fed, JSONResponse(status_code=400, content={
                "success": False,
                "error": "sandbox_conflict",
                "detail": "Do not send X-Payment-Channel with X-AIMarket-Sandbox-Visitor",
                "protocol_version": "v2",
            }))
        if not free_tier_covers(body.capability_id):
            # Refused BEFORE the trial is touched: a capability the free tier does not
            # cover must not cost the caller an allowance to discover that. Every call to
            # these composes an answer with a paid model, so serving one free hands a
            # stranger our model bill — and the visitor id is self-chosen, so the
            # per-caller cap would not even bound it.
            return _fed_refuse(d, fed, JSONResponse(
                status_code=402, content={
                    "success": False,
                    **model_budget_refusal(body.capability_id),
                    "protocol_version": "v2",
                }
            ))
        # Free at the source, as catalogued from THIS peer: no trial, same reason as the
        # local branch. An uncatalogued capability (fed_cap None) still takes one — its
        # price is unknown, and waving it through would serve a priced one for nothing.
        if not (fed_cap is not None and fed_list_price <= 0):
            trial = consume_sandbox_trial(x_sandbox_visitor or "", client_ip=client_ip)
            if trial.get("error"):
                code = 429 if trial["error"] in ("trial_quota_exhausted", "rate_limit_exceeded") else 400
                return _fed_refuse(d, fed, JSONResponse(status_code=code, content={
                    "success": False,
                    "error": trial["error"],
                    "detail": trial.get("detail", ""),
                    "sandbox": trial,
                    "protocol_version": "v2",
                }))
            # Held, not spent — see the `finally` below. The paid branch a few lines down
            # takes a hold so a peer that 402s or times out costs the buyer nothing; a free
            # caller was instead debited at the door and kept the debit through all nine
            # downstream exits. Five clear "retry with source_hub=..." hints in a row emptied
            # a real caller's allowance on production before this was paired.
            fed.trial_visitor = x_sandbox_visitor or ""
            fed.sandbox_meta = {"sandbox": True, **{
                k: trial[k] for k in ("remaining", "used", "max_trials") if k in trial
            }}
    elif (
        price_rail_active
        and fed_price > 0
        and not x_payment_channel
        and not credit_account
        and fed_x402_accepted is None
    ):
        # AIMARKET_SELLS_FOR: this hub is the seller of record, fee is 0,
        # one payee. Keep the listing wallet bound so the x402 middleware
        # can mint a nonce and attach accepts. Unbinding here emptied
        # pay_to and the middleware rewrote a real sale into
        # listing_not_sellable (gaia.weather.read / platon.random live).
        # Broker + routing fee still cannot name one payTo — no second
        # payee is invented; that path stays an unbound 402.
        if expected_fee > 0:
            _unbind_payee(request)
        return _fed_refuse(d, fed, JSONResponse(status_code=402, content={
            "success": False,
            "error": "payment_required",
            "detail": _payment_hint(credits_on, crypto_on),
            "needed": fed_price if expected_fee <= 0 else fed_authorized_total,
            "price_usd": fed_price,
            "routing_fee_usd": expected_fee,
            **_payment_ways(credits_on, crypto_on),
            "protocol_version": "v2",
        }))
    elif (
        fed_price > 0 and credit_account and credits_ledger is not None
        and fed_x402_accepted is None
    ):
        # `fed_x402_accepted is None`: a buyer who paid on chain AND sent a key would
        # otherwise be charged twice for one call — the local branch guards the same way.
        fed_hold = credits_ledger.hold(credit_account, fed_price, fed_nonce)
        if fed_hold.get("error"):
            return _fed_refuse(d, fed, JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_required",
                "detail": fed_hold.get("error"),
                "needed": fed_price,
                "balance": credits_ledger.balance(credit_account),
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            }))
        fed.reserved = True
        fed.hold_rail = "credits"
    elif (
        (fed_price > 0 or fed_authorization is not None) and x_payment_channel
        and fed_x402_accepted is None
    ):
        # A HOLD, not a debit, and before the peer is asked to do anything — the same
        # order the local branch uses. Captured once the peer has actually served the
        # call, released by the `finally` below on every other path, so a peer that 402s,
        # times out or returns garbage never costs the buyer anything.
        #
        # Behind an authorization it is ONE hold for the whole authorized total, under
        # the receipt id the buyer signed. The bridge's invariant is that the cents the
        # ledger debits under that receipt equal the units the signature covers
        # (escrow_bridge/mirror.py, guard 2); a second hold under a `fee_…` receipt the
        # store has never seen leaves the signed row permanently over-collecting, so it
        # is BLOCKED forever — the buyer served and debited off chain, nothing
        # collectable on chain, which is worse than the refusal this replaced.
        fed_hold = invoke.hold_channel(
            x_payment_channel,
            fed_authorized_total if fed_authorization is not None else fed_price,
            receipt_id=fed_nonce,
            secret=x_payment_channel_secret or "",
        )
        if fed_hold.get("error"):
            return _fed_refuse(d, fed, JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_required",
                "detail": fed_hold.get("error"),
                "needed": fed_price,
                **({"balance": fed_hold["balance"]} if "balance" in fed_hold else {}),
                "protocol_version": "v2",
            }))
        fed.reserved = True
        fed.hold_rail = "channel"
    return None


def _fed_unwind_before_try(d: SimpleNamespace, call: _Call, fed: _Fed) -> None:
    """Hand back what is already held on an exit that sits before the `try` below.

    Its `finally` only covers the peer call, so the routing-fee refusals that follow
    left a credit or channel hold for the price in place and burned a verified
    seller-direct claim — the buyer's money in limbo for a call never made.
    """
    credits_ledger, logger, _release_market_payment = call.credits_ledger, d.logger, d._release_market_payment
    fed_reserved, fed_settled, fed_nonce, fed_hold_rail = fed.reserved, fed.settled, fed.nonce, fed.hold_rail
    fed_x402_accepted = fed.x402_accepted
    _fed_withdraw_window(d, fed, "the call was refused before it ran")
    if fed_reserved and not fed_settled:
        try:
            undo = (
                credits_ledger.release_hold(fed_nonce)
                if fed_hold_rail == "credits" and credits_ledger is not None
                else invoke.release_hold(fed_nonce)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("federated invoke: early release of %s raised: %s", fed_nonce, exc)
        else:
            if undo.get("error"):
                logger.error(
                    "federated invoke: early release of %s failed: %s",
                    fed_nonce, undo.get("error"),
                )
    _release_market_payment(fed_x402_accepted)


def _fed_reserve_routing_fee(d: SimpleNamespace, call: _Call, fed: _Fed):
    """The routing fee, reserved before the peer is asked to do anything."""
    request, price_rail_active, credits_on, crypto_on = call.request, call.price_rail_active, call.credits_on, call.crypto_on
    credit_account, credits_ledger = call.credit_account, call.credits_ledger
    x_payment_channel, x_payment_channel_secret = call.x_payment_channel, call.x_payment_channel_secret
    expected_fee, fed_price, fed_authorized_total = fed.expected_fee, fed.price, fed.authorized_total
    fed_authorization, fed_escrow_binding = fed.authorization, fed.escrow_binding
    config, _bind_hub_fee_payee, _payment_hint, _payment_ways = (
        d.config, d._bind_hub_fee_payee, d._payment_hint, d._payment_ways)
    # ── Routing fee: RESERVED before the peer is asked to do anything ────────────
    # It used to be collected after the fact, and only `if x_payment_channel and
    # routing_fee > 0` — so a buyer who simply left the header out paid nothing, and a
    # failed debit was a `logger.warning` with the result served anyway: the one
    # fail-OPEN money path in a file where every other one fails closed. A brokerage
    # that is opt-in for the payer is not a brokerage, and a node whose only revenue
    # line works that way has no P&L.
    #
    # The basis is the price THIS hub published for the routed capability — the same
    # consent anchor the post-hoc code used, just read early enough to act on it. A
    # peer that turns out to charge less is refunded when the fee is settled below, and
    # a peer this hub is seller of record for owes no fee at all (it has already billed
    # the full list price, so a fee on top would bill the same call twice).
    if expected_fee > 0 and price_rail_active and fed_authorization is not None:
        # Already inside the single authorized hold above. Reserving it again here would
        # both double-charge the buyer and split the ledger record across two receipts.
        # The fee is recognised out of the captured total; the settlement tail's fee
        # block is a no-op because `fed_fee_nonce` stays empty.
        pass
    elif expected_fee > 0 and price_rail_active:
        fee_nonce = f"fee_{secrets.token_hex(8)}"
        if credit_account and credits_ledger is not None:
            fee_hold = credits_ledger.hold(credit_account, expected_fee, fee_nonce)
            fee_rail = "credits"
        elif x_payment_channel and (not fed_escrow_binding or fed_authorization is not None):
            # An escrow-backed channel is allowed here now, but ONLY behind an
            # authorization the buyer signed for price + fee (see fed_authorized_total).
            # Without one the fee would be an accrual with nothing on chain to collect
            # it, which is what the refusal below exists to prevent.
            fee_hold = invoke.hold_channel(
                x_payment_channel, expected_fee, receipt_id=fee_nonce,
                secret=x_payment_channel_secret or "",
            )
            fee_rail = "channel"
        else:
            # No payer, or an escrow-backed channel with no authorization covering the
            # fee. The escrow case is refused rather than accrued: collecting on chain
            # needs a DebitAuthorization the buyer signed for THIS amount, and an
            # uncollectable accrual is a number in SQLite pretending to be revenue.
            if not fed_escrow_binding:
                _bind_hub_fee_payee(request, expected_fee)
            _fed_unwind_before_try(d, call, fed)
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "routing_fee_unpayable" if fed_escrow_binding else "payment_required",
                "detail": (
                    "this hub charges a routing fee to broker another hub's capability; "
                    + (
                        "this escrow-backed channel's authorization does not cover it — "
                        "sign a payment_authorization for the total in `needed`"
                        if fed_escrow_binding
                        else _payment_hint(credits_on, crypto_on)
                    )
                ),
                "needed": fed_authorized_total if fed_escrow_binding else expected_fee,
                "price_usd": fed_price,
                "routing_fee_usd": expected_fee,
                "routing_fee_bps": config.routing_fee_bps,
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            })
        if fee_hold.get("error"):
            _fed_unwind_before_try(d, call, fed)
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_required",
                "detail": f"routing fee could not be reserved: {fee_hold.get('error')}",
                "needed": expected_fee,
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            })
        fed.fee_nonce = fee_nonce
        fed.fee_rail = fee_rail
        fed.fee_reserved_usd = expected_fee
    return None


# Imported after the phases on purpose: invoke.py imports these modules to call the
# branches, and any of them may load first. The channel-ledger functions are read as
# invoke.<name> at call time because that is where they are patched.
from aimarket_hub.hub_routes import invoke  # noqa: E402
from aimarket_hub.hub_routes.invoke import _Call, _Fed, _label_x402_paid  # noqa: E402
from aimarket_hub.hub_routes.invoke_parts.federated_delivery import (  # noqa: E402
    _fed_deliver,
    _fed_unwind,
)
