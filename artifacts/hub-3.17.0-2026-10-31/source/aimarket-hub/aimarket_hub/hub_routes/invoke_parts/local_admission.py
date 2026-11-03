"""POST /invoke, local branch, up to the provider call: a capability this hub serves itself.

`_invoke_local` runs the phases in order: the safety pre-check, the capability, the quote, a
seller-direct payment and the paywall, the verification plan, the escrow authorization, the
reservation and the trial; then, inside one try whose `finally` is `_local_unwind`, it hands
over to the delivery phases in `local_delivery`.
"""

from __future__ import annotations

from types import SimpleNamespace
import contextlib
import os
import secrets
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from aimarket_hub import verified_settlement, x402
from aimarket_hub.fulfillment import capability_is_fulfillable
from aimarket_hub.sandbox_trials import consume_sandbox_trial, free_tier_covers, model_budget_refusal, sandbox_stub_invoke_enabled


async def _invoke_local(d: SimpleNamespace, call: _Call):
    """Gates and payment, then execution and settlement inside one try whose `finally`
    hands back whatever the call did not earn."""
    refused = _local_safety_precheck(d, call)
    if refused is not None:
        return refused

    # ── Sandbox trial (widget try-before-buy) ───────────
    if call.sandbox_mode:
        if call.x_payment_channel:
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": "sandbox_conflict",
                "detail": "Do not send X-Payment-Channel with X-AIMarket-Sandbox-Visitor",
                "protocol_version": "v2",
            })
    # The trial is NOT taken here. Eight refusals sit between this point and the
    # first attempt to run anything — invalid ids, unknown capability, "federated,
    # not local", payment_required, payment_failed — and a debit taken here survived
    # every one of them. Measured on production: five invokes with an omitted
    # source_hub, each answered with the exact hint needed to fix the call, emptied a
    # caller's 5/5 allowance without ever running a capability. Charging for
    # validation is the one thing a free tier must not do, so the debit moved to
    # immediately before execution and the ledger gained a release for the exits
    # after it (see the `finally` at the end of this branch).

    # ── Execute ─────────────────────────────────────────
    t0 = time.time()
    factory_url = os.environ.get("AIFACTORY_PUBLIC_URL", "").strip()
    local = _Local(t0=t0, factory_url=factory_url)
    _local_capability(d, call, local)
    for phase in (_local_quote, _local_seller_direct, _local_plan_verification):
        refused = phase(d, call, local)
        if refused is not None:
            return refused

    # ── Reserve the price BEFORE executing (auth leg of auth/capture) ─────
    # INVARIANT: the provider never performs billable work the ledger has not
    # already reserved. A pre-flight balance *read* could not hold that line —
    # N concurrent invokes on one channel all observed the same sufficient
    # balance, so the losers received their 402 only AFTER the provider had
    # done (and had to be paid for) the work. hold_channel() moves the cents
    # out of `balance` atomically under the ledger lock, so exactly as many
    # invokes proceed as the channel can actually pay for.
    #
    # The reservation is resolved on every exit path:
    #   success (plain invoke)  -> capture_hold  (recorded debit)
    #   success (Pay-on-Verified) -> stays held; the verdict captures/releases
    #   anything else           -> release_hold in the `finally` below
    # No rail switched on → free tier: charge nothing and never reserve/debit.
    # With EITHER rail on, a listed price is money.
    local.price = 0.0 if (call.sandbox_mode or not call.price_rail_active) else local.list_price
    for phase in (_local_escrow_authorization, _local_reserve, _local_admit):
        refused = phase(d, call, local)
        if refused is not None:
            return refused

    try:
        return await _local_deliver(d, call, local)
    finally:
        _local_unwind(d, call, local)


def _local_safety_precheck(d: SimpleNamespace, call: _Call):
    """The input's safety check: a 403 with a signed rejection receipt, or None."""
    body, x_payment_channel = call.body, call.x_payment_channel
    plugins, builtin_safety, signer = d.plugins, d.builtin_safety, d.signer
    # ── Safety check: plugins first, then built-in ───────
    block = plugins.run_pre_checks(body.input, {
        "product_id": body.product_id,
        "capability_id": body.capability_id,
        "channel_id": x_payment_channel,
    })
    if not block:
        # Built-in safety gate as fallback
        verdict = builtin_safety.pre_invoke_check(body.input)
        if not verdict.passed:
            block = {
                "blocked": True,
                "category": verdict.category,
                "reason": verdict.reason,
                "refund": True,
                "plugin": "builtin-safety",
            }

    if block:
        rejection_receipt = {
            "type": "safety_rejection",
            "product_id": body.product_id,
            "capability_id": body.capability_id,
            "channel_id": x_payment_channel,
            "category": block.get("category"),
            "reason": block.get("reason"),
            "plugin": block.get("plugin"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "refunded": True,
            "nonce": f"blocked_{int(time.time())}_{body.product_id[:8]}",
        }
        with contextlib.suppress(Exception):
            rejection_receipt["signature"] = signer.sign_receipt(rejection_receipt)
        return JSONResponse(status_code=403, content={
            "success": False,
            "error": "safety_blocked",
            "category": block.get("category"),
            "reason": block.get("reason"),
            "blocked_by": block.get("plugin"),
            "rejection_receipt": rejection_receipt,
            "refund": {"refunded": True, "reason": "plugin_blocked"},
            "protocol_version": "v2",
        })
    return None


def _local_capability(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    """The capability this call runs, or the HTTP error saying why there is none to run."""
    db, body, _is_safe_path = d.db, call.body, d._is_safe_path
    factory_url = local.factory_url
    if not _is_safe_path(body.product_id) or not _is_safe_path(body.capability_id):
        raise HTTPException(status_code=400, detail="Invalid product or capability ID")

    cap = db.get_capability(body.product_id, body.capability_id)
    if cap is None:
        cap = db.find_by_capability_id(body.capability_id)
    if cap is None:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {body.capability_id}")

    # find_by_capability_id is deliberately unfiltered by source_hub, so a
    # capability that exists here only as a crawled peer listing (crawler stores
    # those under source_hub=<peer url>; local publishes are always "local")
    # resolves on this branch even though source_hub="local" asked for LOCAL
    # execution. Two things went wrong when it did: the caller's omitted
    # source_hub surfaced as `502 Factory returned 404`, blaming the factory for
    # a routing mistake, and a peer listing that happens to carry an invoke_url
    # was proxied directly — skipping the federated tail's peer approval,
    # reservation and routing fee. Name the hub to route through instead.
    if (cap.source_hub or "local") != "local":
        raise HTTPException(
            status_code=400,
            detail=(
                f"{body.capability_id} is federated, not local — retry with "
                f'source_hub="{cap.source_hub}", the value '
                f"/ai-market/v2/search returns for this capability."
            ),
        )

    local.invoke_url = (cap.invoke_url or "").strip()

    # Refuse before demanding payment when there is provably nothing to attempt.
    # A caller holding a stale id still reaches this branch — the storefront
    # filters only decide what is advertised — and the paywall below fires before
    # anything asks whether execution is possible, so the refusal a buyer meets
    # first is "pay me", not "this does not run here".
    #
    # Deliberately narrow, and it mirrors the four execution branches below:
    # invoke_url, a static JSON pack, the configured factory, and the explicit
    # offline stub. A row with no invoke_url and no pack can still be served
    # through the last two, which `fulfillment.py` explains it cannot judge from
    # the row alone, so this fires only when every attempt is impossible. Where
    # the factory does answer the attempt goes ahead and the money is protected
    # instead by the hold being released on failure — see
    # TestFailedExecutionIsNotBilled, which pins that.
    if (
        not capability_is_fulfillable(cap)
        and not factory_url
        and not sandbox_stub_invoke_enabled()
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                f"{body.capability_id} is listed but not executable on this hub: "
                "no invoke_url, no static pack and no execution backend. It is "
                "excluded from the manifest, /search and /prices — the listing "
                "you have is stale."
            ),
        )
    local.cap = cap


def _local_quote(d: SimpleNamespace, call: _Call, local: _Local):
    """The list price, whether a seller-direct sale makes it real money, and the buyer's cap."""
    body, request, sandbox_mode = call.body, call.request, call.sandbox_mode
    cap, _bind_listing_payee = local.cap, d._bind_listing_payee
    list_price = float(cap.price_per_call_usd or 0.0)
    seller_payee = _bind_listing_payee(request, cap)
    local.list_price, local.seller_payee = list_price, seller_payee
    if (
        list_price > 0
        and seller_payee
        and x402.accept_enabled()
        and x402.enabled()
        and not sandbox_mode
    ):
        # The catalogue sale is live: this listing has a seller to pay.
        call.price_rail_active = True
    if body.max_price_usd is not None and list_price > body.max_price_usd:
        return JSONResponse(status_code=409, content={
            "success": False,
            "error": "price_limit_exceeded",
            "detail": "the capability price changed after selection; search again",
            "maximum_price_usd": body.max_price_usd,
            "current_price_usd": list_price,
            "protocol_version": "v2",
        })
    return None


def _local_seller_direct(d: SimpleNamespace, call: _Call, local: _Local):
    """Settle an X-Payment sent to the seller, then refuse an unpaid call on a priced
    capability."""
    body, sandbox_mode, credits_on, crypto_on = call.body, call.sandbox_mode, call.credits_on, call.crypto_on
    x402_payment, x402_raw, x_payment_nonce, x_payment_secret = (
        call.x402_payment, call.x402_raw, call.x_payment_nonce, call.x_payment_secret)
    x_payment_channel, credit_account, price_rail_active = (
        call.x_payment_channel, call.credit_account, call.price_rail_active)
    cap, seller_payee = local.cap, local.seller_payee
    _settle_market_payment, _payment_ways, _payment_hint = (
        d._settle_market_payment, d._payment_ways, d._payment_hint)
    # SEC-02: paid capabilities must be paid for. Without a payment channel
    # the debit below is silently skipped (remaining=None), i.e. a free
    # invoke. In production, require X-Payment-Channel before executing so
    # the upstream capability is never run for free.
    # A signed authorization is checked HERE, before the provider runs, for the
    # same reason the credit hold is taken here: work done for a payment that turns
    # out to be invalid is work nobody pays for.
    # The refuse/allow decision lives in unpaid_invoke.py so MOMUS's
    # unpaid_invoke_refused probe has a file Factory remediation can patch.
    from aimarket_hub.unpaid_invoke import must_refuse_unpaid_paid_capability

    if x402_payment is not None and cap.price_per_call_usd > 0 and not sandbox_mode:
        local.x402_accepted = _settle_market_payment(
            raw=x402_raw,
            payload=x402_payment,
            cap=cap,
            price_usd=cap.price_per_call_usd,
            capability_id=body.capability_id,
            header_nonce=(x_payment_nonce or "").strip(),
            header_secret=(x_payment_secret or "").strip(),
        )
        if local.x402_accepted.get("error"):
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_invalid",
                "detail": local.x402_accepted["error"],
                "needed": cap.price_per_call_usd,
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            })
        call.consumer_hub_label = _label_x402_paid(d, call)
        call.payer_wallet = str(local.x402_accepted.get("payer") or "")

    if must_refuse_unpaid_paid_capability(
        price_usd=cap.price_per_call_usd,
        sandbox_mode=sandbox_mode,
        price_rail_active=price_rail_active,
        payment_channel=x_payment_channel,
        credit_account=credit_account,
        x402_accepted=local.x402_accepted,
    ):
        return JSONResponse(status_code=402, content={
            "success": False,
            "error": "payment_required",
            "detail": _payment_hint(credits_on, crypto_on, seller=bool(seller_payee)),
            "needed": cap.price_per_call_usd,
            **_payment_ways(credits_on, crypto_on, seller=bool(seller_payee)),
            "protocol_version": "v2",
        })
    return None


def _local_plan_verification(d: SimpleNamespace, call: _Call, local: _Local):
    """Pay-on-Verified, planned before the provider runs; a 400 for a malformed block."""
    body, crypto_on, sandbox_mode, x_payment_channel = (
        call.body, call.crypto_on, call.sandbox_mode, call.x_payment_channel)
    cap, x402_accepted, _release_market_payment = local.cap, local.x402_accepted, d._release_market_payment
    # ── Pay-on-Verified: plan the opt-in BEFORE executing the provider ────
    # Validating here (not after execution) means a malformed verify block
    # (e.g. requested with an empty intent) is rejected without first running
    # — and paying for — the billable capability (free-work griefing).
    vs_plan = None
    if body.verify is not None:
        vs_plan = verified_settlement.plan(
            body.verify,
            list_price=cap.price_per_call_usd,
            crypto_on=crypto_on,
            sandbox_mode=sandbox_mode,
            channel_id=x_payment_channel,
            capability_id=body.capability_id,
        )
        if vs_plan.error:
            # Also above the try: a bad verification plan is the hub refusing, and
            # the buyer's payment must not be consumed by that refusal.
            _release_market_payment(x402_accepted)
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": "verify_invalid",
                "detail": vs_plan.error,
                "protocol_version": "v2",
            })
        if not vs_plan.active and vs_plan.skipped_envelope is None:
            vs_plan = None  # requested: false — behave exactly like no block
    local.vs_plan = vs_plan
    return None


def _local_escrow_authorization(d: SimpleNamespace, call: _Call, local: _Local):
    """An escrow-backed channel's signed authorization, verified and stored before any work,
    and the receipt id the whole call is booked under."""
    body, crypto_on, sandbox_mode = call.body, call.crypto_on, call.sandbox_mode
    x_payment_channel, credit_account = call.x_payment_channel, call.credit_account
    price, vs_plan, x402_accepted = local.price, local.vs_plan, local.x402_accepted
    logger, _authorization_too_short = d.logger, d._authorization_too_short
    # ── Escrow-backed channels: the buyer's on-chain authorization ────────
    # A channel funded through AIMarketEscrow can only be collected on chain with
    # a DebitAuthorization signed by its depositor, so a paid invoke without one is
    # work this hub could never be paid for. Validated BEFORE the provider runs, so
    # a bad authorization costs a 402 rather than an unpaid delivery. Entirely
    # inert for transfer-funded channels, which is all of them until an operator
    # enables the bridge.
    escrow_binding = ""
    if crypto_on and not sandbox_mode and x_payment_channel:
        with contextlib.suppress(Exception):
            escrow_binding = invoke.channel_escrow_binding(x_payment_channel)

    # Only when the escrow channel is the rail that pays: a call already paid on chain
    # (X-Payment) or bought with credits (X-API-Key) is not charged to the channel,
    # so an authorization stored for it would claim money the ledger never took —
    # and refusing it here would burn an X-Payment claim that already settled.
    escrow_pays = not credit_account and not (
        isinstance(x402_accepted, dict) and bool(x402_accepted.get("ok")))
    if escrow_binding and price > 0 and escrow_pays:
        auth_error = None
        if body.payment_authorization is None:
            auth_error = (
                "this channel is backed by an on-chain escrow: a signed "
                "payment_authorization is required for a paid invoke"
            )
        elif vs_plan is not None and vs_plan.active and vs_plan.paid and _authorization_too_short(
                body.payment_authorization):
            # Refused BEFORE any work: a pass would become final after the appeal
            # window, and the sweep could then not collect an expired signature.
            auth_error = (
                "payment_authorization expires before a verified call can be collected: "
                f"sign a deadline at least {int(verified_settlement.min_authorization_deadline_s())} s "
                "from now (pay_on_verified.authorization_min_lifetime_s)"
            )
        else:
            try:
                from aimarket_hub.escrow_bridge import authorization as bridge_auth
                from aimarket_hub.escrow_bridge import store as bridge_store
            except Exception as exc:
                logger.error("escrow-backed invoke but the bridge is unavailable: %s", exc)
                auth_error = "escrow settlement is not available on this hub"
        if auth_error is None:
            # The buyer chooses the receiptId (they must sign it before the invoke
            # exists), and the hub then uses that SAME id as the ledger receipt —
            # so the on-chain replay key and the off-chain one are literally the
            # same string and cannot drift apart.
            try:
                local.accepted_authorization = bridge_auth.verify_and_store(
                    payload=body.payment_authorization,
                    ledger_channel_id=x_payment_channel,
                    escrow_channel_id=escrow_binding,
                    expected_amount_usd=price,
                    expected_receipt_id=str(
                        (body.payment_authorization or {}).get("receiptId")
                        or (body.payment_authorization or {}).get("receipt_id")
                        or ""
                    ),
                    authorizations=bridge_store.AuthorizationStore(),
                )
            except Exception as exc:
                auth_error = str(exc)
        if auth_error is not None:
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_authorization_required",
                "detail": auth_error,
                "needed": price,
                "protocol_version": "v2",
            })

    local.nonce = (
        local.accepted_authorization.row.receipt_id
        if local.accepted_authorization is not None
        else f"rcpt_{secrets.token_hex(16)}"
    )
    return None


def _local_withdraw_escrow_window(d: SimpleNamespace, local: _Local, reason: str) -> None:
    logger = d.logger
    # The buyer's authorization was stored before the work as the running total
    # of its nonce window. A call that is not delivered must not stay in it: the
    # mirror would never collect the window, and every later call would have to
    # sign for it again. Restores the authorization it replaced.
    if local.accepted_authorization is None:
        return
    try:
        from aimarket_hub.escrow_bridge import authorization as bridge_auth
        from aimarket_hub.escrow_bridge import store as bridge_store

        bridge_auth.withdraw(local.accepted_authorization.row.receipt_id,
                             bridge_store.AuthorizationStore(), reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.error("invoke: withdrawing escrow authorization %s raised: %s",
                     local.accepted_authorization.row.receipt_id[:14], exc)


def _local_reserve(d: SimpleNamespace, call: _Call, local: _Local):
    """Reserve the price on the rail that pays, before anything runs: one call, one charge."""
    crypto_on, credits_on, sandbox_mode = call.crypto_on, call.credits_on, call.sandbox_mode
    credits_ledger, credit_account = call.credits_ledger, call.credit_account
    x_payment_channel, x_payment_channel_secret = call.x_payment_channel, call.x_payment_channel_secret
    cap, price, nonce, x402_accepted = local.cap, local.price, local.nonce, local.x402_accepted
    _pays_a_third_party, _payment_ways = d._pays_a_third_party, d._payment_ways
    # ONE call, ONE charge — whichever rail carried it.
    #
    # A 402 advertises every way to pay (`_payment_ways`), and a client that
    # answers it with X-Payment while its standing X-API-Key rides along on the
    # same request — which is simply what an HTTP client does — used to be charged
    # on BOTH: USDC to the seller on chain, and then the full list price held and
    # captured from its prepaid credits. The ledger leg has no refund path, so the
    # second charge was permanent. The same request shape also reached three
    # `return`s between the settlement and the try below, each of which left the
    # on-chain claim consumed for a call that never ran.
    #
    # A verified seller-direct settlement is payment in full. Nothing else is
    # reserved on top of it.
    settled_on_chain = isinstance(x402_accepted, dict) and bool(x402_accepted.get("ok"))

    # A credit line buys the operator's OWN resources. A listing whose seller has
    # to be paid for real is bought on the rail that actually pays them, so the
    # operator never funds a stranger's sale out of a limit they gave away.
    if price > 0 and not settled_on_chain and credit_account and _pays_a_third_party(cap):
        return JSONResponse(status_code=402, content={
            "success": False,
            "error": "payment_required",
            "detail": (
                "this listing pays its seller directly, so it cannot be bought "
                "with hub credits — pay on chain with X-Payment"
            ),
            "needed": price,
            **_payment_ways(False, crypto_on),
            "protocol_version": "v2",
        })

    if price > 0 and not settled_on_chain and credit_account and credits_ledger is not None:
        pay_result = credits_ledger.hold(credit_account, price, nonce)
        if pay_result.get("error"):
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_required",
                "detail": pay_result.get("error"),
                "needed": price,
                "balance": credits_ledger.balance(credit_account),
                **_payment_ways(credits_on, crypto_on),
                "protocol_version": "v2",
            })
        local.reserved = True
        local.hold_rail = "credits"
        local.remaining = pay_result.get("remaining_balance", 0)
    elif price > 0 and not settled_on_chain and x_payment_channel:
        pay_result = invoke.hold_channel(
            x_payment_channel, price, receipt_id=nonce,
            secret=x_payment_channel_secret or "",
        )
        if pay_result.get("error"):
            _local_withdraw_escrow_window(d, local, "the channel refused the hold")
            # Only the ledger's authenticated insufficient-balance result may
            # disclose a balance; never look it up after an authorization failure.
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_required",
                "detail": pay_result.get("error"),
                "needed": price,
                **({"balance": pay_result["balance"]} if "balance" in pay_result else {}),
                "protocol_version": "v2",
            })
        local.reserved = True
        local.hold_rail = "channel"
        local.remaining = pay_result.get("remaining_balance", 0)
    elif crypto_on and not settled_on_chain and not sandbox_mode and x_payment_channel:
        # Free capability on a real channel: nothing to reserve, but keep the
        # zero-amount debit so the channel secret is still authenticated and
        # the response can report the buyer's balance (legacy behaviour).
        pay_result = invoke.debit_channel(
            x_payment_channel, 0.0, receipt_id=nonce,
            secret=x_payment_channel_secret or "",
        )
        if pay_result.get("error"):
            return JSONResponse(status_code=402, content={
                "success": False,
                "error": "payment_failed",
                "detail": pay_result.get("error"),
                "needed": price,
                "protocol_version": "v2",
            })
        local.remaining = pay_result.get("remaining_balance", 0)
    return None


def _local_release_reservation(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    credits_ledger, logger = call.credits_ledger, d.logger
    reserved, nonce, hold_rail = local.reserved, local.nonce, local.hold_rail
    # The hold taken above, for an exit ABOVE the try whose `finally` would
    # otherwise release it. Through a mandate or allowance proxy this is also
    # what returns the mandate reservation: left held, every refused call would
    # eat into perDay/total for good.
    _local_withdraw_escrow_window(d, local, "the call was refused before it ran")
    if not reserved:
        return
    try:
        released = (
            credits_ledger.release_hold(nonce)
            if hold_rail == "credits" and credits_ledger is not None
            else invoke.release_hold(nonce)
        )
        if released.get("error"):
            logger.error("invoke: failed to release reservation %s: %s", nonce, released["error"])
    except Exception as exc:  # noqa: BLE001
        logger.error("invoke: release of reservation %s raised: %s", nonce, exc)


def _local_admit(d: SimpleNamespace, call: _Call, local: _Local):
    """The last refusals before anything runs: incomplete input, then the free tier's trial."""
    body, sandbox_mode, x_sandbox_visitor, client_ip = (
        call.body, call.sandbox_mode, call.x_sandbox_visitor, call.client_ip)
    x402_accepted, list_price, _release_market_payment = (
        local.x402_accepted, local.list_price, d._release_market_payment)
    # Payment is settled; before anything is attempted, is the request even complete?
    #
    # This returns ABOVE the try whose `finally` releases everything, and the
    # ordering is deliberate and load-bearing — asked before the paywall it would
    # answer 400 to an unpaid call on a priced capability and break x402, which
    # `deploy_hub_rebuild.sh` probes for. So the release is made here explicitly
    # rather than by moving the gate: a buyer who left out a field has still paid.
    short = _refuse_incomplete_input(d, call)
    if short is not None:
        _release_market_payment(x402_accepted)
        _local_release_reservation(d, call, local)
        return short

    # Validation is over; something is actually going to be attempted. Take the trial
    # now, and treat it as a reservation released by the `finally` below on any exit
    # that does not deliver — the same shape the payment hold above already uses.
    if sandbox_mode:
        if not free_tier_covers(body.capability_id):
            _release_market_payment(x402_accepted)
            _local_release_reservation(d, call, local)
            # Refused BEFORE the trial is touched: a capability the free tier does not
            # cover must not cost the caller an allowance to discover that. Every call to
            # these composes an answer with a paid model, so serving one free hands a
            # stranger our model bill — and the visitor id is self-chosen, so the
            # per-caller cap would not even bound it.
            return JSONResponse(
                status_code=402, content={
                    "success": False,
                    **model_budget_refusal(body.capability_id),
                    "protocol_version": "v2",
                }
            )
    # A capability listed at $0 costs nobody anything, so it takes no trial. It used
    # to: every hub that routes to a peer sends a sandbox visitor header, so a FREE
    # SKU burned the caller's lifetime allowance of three, and from the fourth call on
    # answered 429 `trial_quota_exhausted` — for good. hub.attestedmemory.net routing
    # hunt's free `signal.leaderboard@v1` hit exactly that, and the assay on hunt read
    # the 502 as the attested hub's fault and held it at `review`.
    if sandbox_mode and list_price > 0:
        trial = consume_sandbox_trial(x_sandbox_visitor or "", client_ip=client_ip)
        if trial.get("error"):
            _release_market_payment(x402_accepted)
            _local_release_reservation(d, call, local)
            code = 429 if trial["error"] in ("trial_quota_exhausted", "rate_limit_exceeded") else 400
            return JSONResponse(status_code=code, content={
                "success": False,
                "error": trial["error"],
                "detail": trial.get("detail", ""),
                "sandbox": trial,
                "protocol_version": "v2",
            })
        local.trial_visitor = x_sandbox_visitor or ""
        local.sandbox_meta = {"sandbox": True, **{k: trial[k] for k in ("remaining", "used", "max_trials") if k in trial}}
    return None


# Imported after the phases on purpose: invoke.py imports these modules to call the
# branches, and any of them may load first. The channel-ledger functions are read as
# invoke.<name> at call time because that is where they are patched.
from aimarket_hub.hub_routes import invoke  # noqa: E402
from aimarket_hub.hub_routes.invoke import (  # noqa: E402
    _Call,
    _Local,
    _label_x402_paid,
    _refuse_incomplete_input,
)
from aimarket_hub.hub_routes.invoke_parts.local_delivery import (  # noqa: E402
    _local_deliver,
    _local_unwind,
)
