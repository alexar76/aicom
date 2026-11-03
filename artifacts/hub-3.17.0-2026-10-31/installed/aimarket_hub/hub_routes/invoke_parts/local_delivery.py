"""POST /invoke, local branch, from the provider call on: execution, the delivery checks,
settlement, the receipt, bookkeeping, the answer, and `_local_unwind` (the branch's `finally`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import json
import os
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse
import httpx

from aimarket_hub import invoke_funding, oracle_paid_tier, provider_request_auth, subcontract
from aimarket_hub.acex_storage import LedgerNotConfigured
from aimarket_hub.models import InvocationStat
from aimarket_hub.sandbox_trials import release_sandbox_trial, sandbox_demo_result, sandbox_stub_invoke_enabled


async def _local_deliver(d: SimpleNamespace, call: _Call, local: _Local):
    """Run the capability; if it delivered, settle, sign, record and answer."""
    body = call.body
    result = await _local_execute(d, call, local)
    local.elapsed_ms = int((time.time() - local.t0) * 1000)
    _local_refuse_undelivered(d, call, local, result)

    # ── Post-check: plugins first, then built-in ────────
    blocked = _post_check(d, result, {
        "product_id": body.product_id,
        "capability_id": body.capability_id,
    })
    if blocked is not None:
        return blocked

    _local_settle(d, call, local)
    _local_sign_receipt(d, call, local)
    _local_register_verification(d, call, local, result)
    _local_record(d, call, local, result)
    acex_revenue, acex_audit_rewards = _local_accrue_acex(d, call, local)
    await _local_await_verdict(d, call, local)
    local.x402_settlement = _x402_settlement(d, call, local)
    provenance_receipt = _local_provenance(d, call, local, result)
    return _local_answer(d, call, local, result, provenance_receipt, acex_revenue, acex_audit_rewards)


async def _local_execute(d: SimpleNamespace, call: _Call, local: _Local):
    """The capability's output, from whichever of the four backends serves it."""
    body = call.body
    cap, factory_url, invoke_url = local.cap, local.factory_url, local.invoke_url
    if invoke_url:
        result = await _local_call_provider(d, call, local)
    elif not factory_url and sandbox_stub_invoke_enabled():
        # Explicit opt-in offline/CI stub (AIMARKET_SANDBOX_STUB_INVOKE=1).
        # Default-off so production never silently returns fake results;
        # covers both sandbox visitors and local demo invokes without a backend.
        result = sandbox_demo_result(body.capability_id, body.product_id, body.input)
    elif (cap.prompt_template or "").strip().startswith("{"):
        # Hub-local static packs (e.g. security-rules.sec-feed) — JSON stored
        # in prompt_template, no external invoke_url required.
        try:
            result = json.loads(cap.prompt_template)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"capability prompt_template is not valid JSON: {exc}",
            ) from exc
    elif not factory_url:
        raise HTTPException(
            status_code=503,
            detail="No execution backend configured. Set AIFACTORY_PUBLIC_URL "
                   "to the factory API address (e.g. http://127.0.0.1:8081)."
        )
    else:
        result = await _local_call_factory(d, call, local)
    return result


def _payer_statement(
    d: SimpleNamespace, call: _Call, admission: dict[str, str], *, input_payload: Any,
    x402_accepted: dict[str, Any] | None, hold_rail: str, reserved: bool,
) -> dict[str, str]:
    """Who paid for this admitted call, signed next to its admission, or {}.

    For a provider that hands something to one buyer: GAIA leases a plug to the payer of
    its "on" (provider_request_auth.py, "The payer statement"). Only a payer this hub
    checked: the x402 `authorization.from` the chain settled, or, when the price is held
    on a channel whose secret this call presented, the wallet that proved control of that
    channel's deposit at open. A trial, hub credits and a demo-credit channel name nobody,
    and the buyer is anonymous there. Never raises: a fault leaves the statement out.
    """
    try:
        if (not admission or call.sandbox_mode
                or not provider_request_auth.payer_statement_wanted(call.body.capability_id)):
            return {}
        payer, rail = "", ""
        if isinstance(x402_accepted, dict) and x402_accepted.get("ok") and call.payer_wallet:
            payer, rail = call.payer_wallet, "x402"
        elif reserved and hold_rail == "channel" and call.x_payment_channel:
            payer, rail = invoke.channel_payer(call.x_payment_channel), "channel"
        if not payer:
            return {}
        return provider_request_auth.payer_headers(
            d.signer, admission, capability_id=call.body.capability_id,
            input_payload=input_payload, payer=payer, rail=rail,
        )
    except Exception:  # noqa: BLE001 — never fail the buyer's call over who they are
        d.logger.exception("payer statement for %s left out", call.body.capability_id)
        return {}


async def _local_call_provider(d: SimpleNamespace, call: _Call, local: _Local):
    """The listing's own invoke_url, with the provider's signature checked."""
    body, request, sandbox_mode = call.body, call.request, call.sandbox_mode
    x_payment_channel, funding = call.x_payment_channel, call.funding
    cap, invoke_url = local.cap, local.invoke_url
    supply_security, hub_jobs = d.supply_security, d.hub_jobs
    TrustOracleUnavailable, _provider_channel_ref = d.TrustOracleUnavailable, d._provider_channel_ref
    try:
        sanitized = supply_security.sanitize_input(body.input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        supply_security.check_invoke_trust(cap)
    except TrustOracleUnavailable as exc:
        # LUMEN down / unreachable (including the oracle answering 403)
        # is a hub-dependency failure, not "this caller is forbidden".
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        from urllib.parse import urlparse

        from aimarket_hub.outbound_http import (
            invoke_gateway_hosts,
            resolve_invoke_url,
            safe_post,
        )

        provider_headers = {
            # A reference, never the id: see _provider_channel_ref.
            "X-Payment-Channel": _provider_channel_ref(x_payment_channel),
            "X-AIMarket-Sandbox": "1" if sandbox_mode else "",
        }
        operation_id = getattr(request.state, "seller_operation_id", None)
        if operation_id:
            provider_headers["Idempotency-Key"] = operation_id
            provider_headers["X-AIMarket-Operation-Id"] = operation_id
        # The job token (and, for a funded job, its grant) plus the agent and
        # principal a mandate vouches for — mandates.md §5.4, §6.1-6.2. Only on
        # this local branch: none of it is ever forwarded to a peer.
        if funding is not None:
            provider_headers.update(funding.provider_headers(hub_jobs))
            if subcontract.GRANT_HEADER in provider_headers and not invoke_funding.grant_may_travel_to(invoke_url):
                provider_headers.pop(subcontract.GRANT_HEADER)
                d.logger.warning("subcontract: grant withheld from %s (plain http outside the operator's hosts)",
                               urlparse(invoke_url).hostname)
        # Private Hub→provider token: only for operator-named local
        # gateway hosts (e.g. kova-api). Use the post-rewrite host so
        # localhost→gateway remaps still get the token. Never forward
        # to federated / public URLs.
        capability_token = os.environ.get("AIMARKET_CAPABILITY_TOKEN", "").strip()
        target_host = (urlparse(resolve_invoke_url(invoke_url)).hostname or "").lower()
        if capability_token and target_host in set(invoke_gateway_hosts()):
            provider_headers["X-AIMarket-Internal-Token"] = capability_token
        # Signed with this hub's key, so a provider behind a price gate
        # (oracle_core.price_gate) can tell this hub admitted the call: the paywall or the
        # trial above has already run. Over the registered invoke_url, before any
        # gateway rewrite, because that is the name the provider knows itself by.
        admission = provider_request_auth.signed_headers(
            d.signer, hub_url=d.config.hub_url, audience=invoke_url,
            capability_id=body.capability_id, input_payload=sanitized,
        )
        provider_headers.update(admission)
        provider_headers.update(_payer_statement(
            d, call, admission, input_payload=sanitized, x402_accepted=local.x402_accepted,
            hold_rail=local.hold_rail, reserved=local.reserved,
        ))

        ir = await safe_post(
            invoke_url,
            json={
                "input": sanitized,
                "product_id": body.product_id,
                "capability_id": body.capability_id,
            },
            headers=provider_headers,
            invoke=True,
            oracle_paid=oracle_paid_tier.funded(
                price=local.price, sandbox=sandbox_mode, reserved=local.reserved,
                hold_rail=local.hold_rail, x402_accepted=local.x402_accepted,
            ),
        )
        if ir.status_code == 200:
            try:
                payload = ir.json()
            except ValueError as exc:
                # Same rule as the federated tail: a body the provider
                # could not serialize is a PROVIDER fault (502), not a
                # 500 from this hub and not the caller's bad request.
                local.provider_invoke_failed = True
                raise HTTPException(
                    status_code=502,
                    detail=f"Provider at {invoke_url} returned a non-JSON body",
                ) from exc
            if not isinstance(payload, dict):
                local.provider_invoke_failed = True
                raise HTTPException(
                    status_code=502,
                    detail=f"Provider at {invoke_url} returned a non-object JSON body",
                )
            result = payload.get("result", payload.get("output", payload))
            sig = ir.headers.get("X-Provider-Signature", "")
            try:
                supply_security.verify_provider_response(
                    cap, result, sig,
                    product_id=body.product_id,
                    input_payload=sanitized,
                )
            except ValueError as exc:
                local.provider_invoke_failed = True
                if cap.publisher_id:
                    supply_security.record_invoke(
                        publisher_id=cap.publisher_id,
                        consumer_id=x_payment_channel or "",
                        success=False,
                        product_id=body.product_id,
                        capability_id=body.capability_id,
                    )
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        else:
            local.provider_invoke_failed = True
            # Only a provider-side 5xx counts as a genuine provider fault
            # worth recording (and slashing after the consecutive-failure
            # threshold in record_invoke). A 4xx reflects bad consumer
            # input, so it must never penalize the provider's stake.
            if cap.publisher_id and ir.status_code >= 500:
                supply_security.record_invoke(
                    publisher_id=cap.publisher_id,
                    consumer_id=x_payment_channel or "",
                    success=False,
                    product_id=body.product_id,
                    capability_id=body.capability_id,
                )
            raise HTTPException(
                status_code=502,
                detail=f"Provider returned {ir.status_code}: {ir.text[:200]}",
            )
    except (httpx.RequestError, ValueError) as exc:
        # Transient provider unreachability / timeout is NOT proof of
        # misbehavior. A ValueError here is the outbound safety layer
        # refusing an unsafe/unresolvable destination; it is likewise a
        # delivery failure, not an uncaught Hub 500 and not slash evidence.
        # The invoke still fails for the consumer and the hold is released.
        local.provider_invoke_failed = True
        raise HTTPException(
            status_code=502,
            detail=f"Provider unreachable at {invoke_url}: {exc}",
        ) from exc
    return result


async def _local_call_factory(d: SimpleNamespace, call: _Call, local: _Local):
    """The configured factory, or the offline stub where that is explicitly enabled."""
    body, sandbox_mode = call.body, call.sandbox_mode
    x_payment_channel, funding = call.x_payment_channel, call.funding
    factory_url, hub_jobs, logger, _provider_channel_ref = (
        local.factory_url, d.hub_jobs, d.logger, d._provider_channel_ref)
    try:
        async with httpx.AsyncClient(timeout=30) as fc:
            fr = await fc.post(
                f"{factory_url}/capabilities/{body.product_id}/{body.capability_id}/invoke",
                json={"input": body.input},
                headers={
                    "X-Payment-Channel": _provider_channel_ref(x_payment_channel),
                    "X-AIMarket-Sandbox": "1" if sandbox_mode else "",
                    **(funding.provider_headers(hub_jobs) if funding is not None else {}),
                },
            )
            if fr.status_code == 200:
                result = fr.json()
            elif sandbox_stub_invoke_enabled():
                logger.info(
                    "Factory %s for %s/%s — stub invoke (AIMARKET_SANDBOX_STUB_INVOKE)",
                    fr.status_code, body.product_id, body.capability_id,
                )
                result = sandbox_demo_result(
                    body.capability_id, body.product_id, body.input,
                )
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Factory returned {fr.status_code}: {fr.text[:200]}"
                )
    except httpx.RequestError as exc:
        if sandbox_mode and sandbox_stub_invoke_enabled():
            result = sandbox_demo_result(body.capability_id, body.product_id, body.input)
        else:
            raise HTTPException(
                status_code=502,
                detail=f"Factory unreachable at {factory_url}: {exc}"
            ) from exc
    return result


def _local_refuse_undelivered(d: SimpleNamespace, call: _Call, local: _Local, result: Any) -> None:
    body, logger = call.body, d.logger
    # ── Provider said it did not deliver ──────────────────────────────
    # The AIMarket-v2 envelope carries an explicit `ok: false` when the
    # work failed honestly (a GAIA relay whose upstream is offline, an
    # empty CAP feed). That is not a 200: billing it would debit the
    # buyer and hand them a signed receipt reading `success: true` over
    # an error body. Fail closed here — the reservation is still
    # unresolved, so `finally` hands the money back untouched.
    # Only an EXPLICIT false counts; most results carry no `ok` at all.
    if isinstance(result, dict) and (
        result.get("ok") is False or result.get("success") is False
    ):
        # An honest "I could not read" is correct provider behaviour, not
        # misbehaviour: skip the success recording, do not slash the stake.
        local.provider_invoke_failed = True
        provider_error = str(
            result.get("error") or result.get("detail") or "provider reported failure"
        )[:200]
        logger.info(
            "invoke: provider %s/%s returned ok=false (%s) — no debit",
            body.product_id, body.capability_id, provider_error,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Provider did not deliver: {provider_error}",
        )


def _local_settle(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    credits_ledger, logger, _pay_publisher_share = call.credits_ledger, d.logger, d._pay_publisher_share
    vs_plan, reserved, hold_rail, nonce = local.vs_plan, local.reserved, local.hold_rail, local.nonce
    cap, price, x402_accepted = local.cap, local.price, local.x402_accepted
    # ── Payment: settle the reservation taken before execution ────────────
    # The money was already moved out of the buyer's balance (auth leg).
    # Delivery succeeded and the post-checks passed, so the reservation now
    # either becomes a recorded debit (plain invoke) or stays held for the
    # Metis verdict (Pay-on-Verified).
    # `hold_rail == "channel"` is part of the condition, not an afterthought.
    # `plan()` decides `paid` from the PRESENCE of an X-Payment-Channel header,
    # while the hold above is taken on whichever rail won — and when a caller
    # sends BOTH X-API-Key and X-Payment-Channel, credits wins. The deferred
    # path then hands ownership to a verified_settlements row that records only
    # a channel_id, and `_finalize` resolves it with the CHANNEL ledger's
    # capture_hold/release_hold, which have no such reservation. The credits hold
    # was therefore neither captured nor released: the buyer's money stayed
    # frozen and the envelope's promised refund never happened. The two
    # predicates the old comment said were equivalent had already drifted.
    # A non-channel hold is simply not deferrable, so it settles now.
    if vs_plan is not None and vs_plan.active and vs_plan.paid \
            and (not reserved or hold_rail == "channel"):
        # Deferred settlement: the hold STAYS reserved. Ownership passes to
        # the verified_settlements row at register() below, which is where
        # `resolved` flips — until then `finally` still owns the release.
        if not reserved:
            # A "paid" verified settlement with no money behind it: refuse
            # rather than register it.
            logger.error(
                "invoke: verified settlement planned for %s without a reservation",
                nonce,
            )
            raise HTTPException(
                status_code=502,
                detail="settlement failed: no reservation backs the verified invoke",
            )
    elif reserved:
        capture = (
            credits_ledger.capture_hold(nonce)
            if hold_rail == "credits" and credits_ledger is not None
            else invoke.capture_hold(nonce)
        )
        if capture.get("error") or capture.get("already") not in (None, "captured"):
            # The ledger refused to convert OUR OWN reservation into a debit
            # (it existed a moment ago). Something is wrong with the ledger
            # state, so fail closed: withhold the output and let `finally`
            # hand the reservation back, rather than serving billable work
            # that the ledger never recorded as paid. "Already released" is
            # the same failure without an error field: something freed the
            # hold under a running call, and the answer would go out free.
            logger.error(
                "invoke: capture of reservation %s failed: %s",
                nonce, capture.get("error"),
            )
            raise HTTPException(
                status_code=502,
                detail="settlement failed: reservation could not be captured",
            )
        # The reservation is now a recorded debit — nothing left to release.
        local.resolved = True
        # Credits-rail residual only. A seller-direct settle already
        # paid the listing's payout_address on chain.
        if not (x402_accepted and x402_accepted.get("rail") == "seller_direct"):
            _pay_publisher_share(cap, price, nonce)


def _local_sign_receipt(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    body, sandbox_mode, signer = call.body, call.sandbox_mode, d.signer
    nonce, price, list_price, elapsed_ms = local.nonce, local.price, local.list_price, local.elapsed_ms
    receipt_payload = {
        "nonce": nonce,
        "product_id": body.product_id,
        "capability_id": body.capability_id,
        "price_usd": price,
        "list_price_usd": list_price,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Fields the signature canonical covers — included so the receipt
        # is self-contained and a consumer can recompute + verify it.
        "success": True,
        "latency_ms": elapsed_ms,
    }
    if sandbox_mode:
        receipt_payload["sandbox"] = True
    # Self-contained, verifiable receipt: signed fields + signature block.
    local.receipt = {**receipt_payload, "signature": signer.sign_receipt(receipt_payload)}


def _local_register_verification(d: SimpleNamespace, call: _Call, local: _Local, result: Any) -> None:
    body, x_payment_channel, verify_svc = call.body, call.x_payment_channel, d.verify_svc
    vs_plan, reserved, hold_rail, nonce = local.vs_plan, local.reserved, local.hold_rail, local.nonce
    cap, price = local.cap, local.price
    # ── Pay-on-Verified: register the pending settlement BEFORE any other ──
    # bookkeeping. register() commits the durable verified_settlements row
    # that makes an escrow hold recoverable (the startup reconciler re-queues
    # pending rows). If it raises, the hold has no owner yet — the `finally`
    # below releases it so a crash can't lock the buyer's funds.
    if vs_plan is not None and vs_plan.active:
        # Deferred only when a CHANNEL hold is what backs the call: that is the
        # hold the settlement worker captures or releases. A buyer who also sent
        # X-API-Key was reserved — and above, already captured — on credits;
        # registered as paid with the channel id, the worker then looked for a
        # channel hold that never existed and (since a failed ledger move no
        # longer signs an outcome) left the row in `finalizing` for good.
        deferred = bool(vs_plan.paid and reserved and hold_rail == "channel")
        local.verification_env = verify_svc.register(
            nonce=nonce,
            product_id=body.product_id,
            capability_id=body.capability_id,
            channel_id=(x_payment_channel or "") if deferred else "",
            provider_id=cap.publisher_id or "",
            price_usd=price,
            intent=vs_plan.intent,
            output=result,
            mode=vs_plan.mode,
            receipt=local.receipt,
            advisory=not deferred,
        )
        # The durable settlement row now owns the hold (and the startup
        # reconciler will finish it after a crash) — stop releasing it here.
        local.resolved = True


def _local_record(d: SimpleNamespace, call: _Call, local: _Local, result: Any) -> None:
    body, x_payment_channel = call.body, call.x_payment_channel
    cap, invoke_url, price, elapsed_ms = local.cap, local.invoke_url, local.price, local.elapsed_ms
    db, logger, supply_security, _observe_answer = d.db, d.logger, d.supply_security, d._observe_answer
    stat = InvocationStat(
        capability_id=body.capability_id,
        product_id=body.product_id,
        source_hub="local",
        price_usd=price,
        latency_ms=elapsed_ms,
        success=True,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        consumer_hub=call.consumer_hub_label,
        outcome="ok",
        caller_class=_caller_class_now(d, call),
        purpose=body.purpose,
    )
    # Bookkeeping must never be able to destroy delivered work: the answer is
    # already produced here, and `record_invocation` only writes a metrics row.
    # See the federated path for the incident this comes from.
    try:
        db.record_invocation(stat)
    except Exception as exc:
        logger.error("invocation stat NOT recorded (call succeeded): %s", exc)
    _observe_answer(db, "local", body, result)

    if invoke_url and cap.publisher_id and not local.provider_invoke_failed:
        supply_security.record_invoke(
            publisher_id=cap.publisher_id,
            consumer_id=x_payment_channel or "",
            success=True,
            product_id=body.product_id,
            capability_id=body.capability_id,
        )


def _local_accrue_acex(d: SimpleNamespace, call: _Call, local: _Local):
    body, sandbox_mode, logger = call.body, call.sandbox_mode, d.logger
    price, vs_deferred = local.price, local.vs_deferred
    # ── ACEX revenue routing (factory → hub → ACEX leg) ──────
    # Feed the listing's CapShares pool only with revenue ACTUALLY earned:
    # gate on the charged `price` (0 when sandbox OR crypto off), not the
    # list price. Otherwise a crypto-off deployment — which debits nothing
    # and settles nothing on-chain — would still accrue phantom list-price
    # revenue to shareholders/auditors.
    # A verified hold defers revenue accrual to capture time: only money the
    # verdict actually captured may feed CapShares pools / audit rewards
    # (verified_settlement._accrue_acex mirrors these two blocks).
    acex_revenue = None
    if not sandbox_mode and price > 0 and not vs_deferred:
        try:
            from aimarket_hub import acex_ipo
            accrued = acex_ipo.accrue_revenue(body.product_id, price)
            if accrued.get("ok"):
                acex_revenue = {
                    "to_pool_usd": accrued["to_pool_usd"],
                    "revenue_share_bps": accrued["revenue_share_bps"],
                }
        except LedgerNotConfigured:
            pass                     # ACEX is off on this hub by configuration (logged once)
        except Exception as exc:
            logger.warning("ACEX accrue failed for %s: %s", body.product_id, exc)

    acex_audit_rewards = None
    if not sandbox_mode and price > 0 and not vs_deferred:
        try:
            from aimarket_hub import acex_audit
            audit_acc = acex_audit.accrue_audit_rewards(body.product_id, price)
            if audit_acc.get("ok"):
                acex_audit_rewards = {
                    "to_auditors_usd": audit_acc["to_auditors_usd"],
                    "audit_fee_bps": audit_acc["audit_fee_bps"],
                    "bridge": audit_acc.get("bridge"),
                }
        except LedgerNotConfigured:
            pass
        except Exception as exc:
            logger.warning("ACEX audit accrue failed for %s: %s", body.product_id, exc)
    return acex_revenue, acex_audit_rewards


async def _local_await_verdict(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    x_payment_channel, verify_svc = call.x_payment_channel, d.verify_svc
    vs_plan, nonce = local.vs_plan, local.nonce
    # ── Pay-on-Verified: resolve the buyer's chosen sync/async mode ───────
    if vs_plan is not None:
        if vs_plan.active and vs_plan.wait:
            # Sync opt-in: hold the response until the verdict, bounded.
            # On timeout we return the pending envelope (NOT an error) —
            # the buyer falls back to GET /verification/{nonce}.
            vs_resolved = await verify_svc.wait_for(nonce, timeout=vs_plan.wait_timeout_s)
            if vs_resolved:
                local.verification_env = vs_resolved.get("verification") or local.verification_env
                local.receipt = vs_resolved.get("receipt") or local.receipt
                local.vs_rejection = vs_resolved.get("rejection_receipt")
                # The verdict may have released the hold back to the balance;
                # recompute so remaining_balance never under-reports (a stale
                # post-hold figure would hide the refund from the buyer).
                if local.remaining is not None and (local.verification_env or {}).get("status") == "refunded":
                    _bal = invoke.channel_balance(x_payment_channel)
                    if _bal is not None:
                        local.remaining = _bal
        elif not vs_plan.active:
            # Skipped (below floor / disabled): legacy settlement, envelope says why.
            local.verification_env = vs_plan.skipped_envelope
            local.receipt["verification"] = local.verification_env


def _local_provenance(d: SimpleNamespace, call: _Call, local: _Local, result: Any):
    body, funding = call.body, call.funding
    plugins, config, hub_jobs = d.plugins, d.config, d.hub_jobs
    price, list_price, nonce, reserved, elapsed_ms = local.price, local.list_price, local.nonce, local.reserved, local.elapsed_ms
    receipt, verification_env, vs_deferred = local.receipt, local.verification_env, local.vs_deferred
    # ── Final artifacts: after safety and settlement are stable ─────────
    # Receipt issuance used to happen inside run_post_checks(), before the
    # built-in gate and before capture.  Besides leaving receipts behind for
    # blocked outputs, that call only carried product/capability ids, so AWR
    # committed to an empty input, local provider, zero latency and zero price.
    # The final hook sees the exact accepted output and the economics the hub
    # can actually attest.  A deferred Pay-on-Verified hold is deliberately
    # not described as captured; its later verdict owns that statement.
    verification_status = str((verification_env or {}).get("status") or "")
    if vs_deferred:
        # A synchronous Pay-on-Verified request can already be settled or
        # refunded by the time this final hook runs.  Commit to the money
        # outcome we actually know, never to the original asking price as
        # though it had necessarily reached the provider.
        artifact_price = price if verification_status == "settled" else 0.0
        artifact_settlement = (
            "captured" if verification_status == "settled"
            else "refunded" if verification_status == "refunded"
            else "pending"
        )
    else:
        artifact_price = price
        artifact_settlement = (
            "captured" if reserved and price > 0 else "free"
        )

    receipt_context = {
        "product_id": body.product_id,
        "capability_id": body.capability_id,
        "input": body.input,
        "provider_hub": config.hub_url,
        "latency_ms": elapsed_ms,
        "price_usd": artifact_price,
        "list_price_usd": list_price,
        "status": "succeeded",
        "nonce": nonce,
        "settlement_status": artifact_settlement,
        "gateway_receipt": receipt,
        # The work receipts of the subcontractors this call hired (mandates.md
        # §6.4): the provenance receipt lists them in AWR/2 `parents`, so the job
        # tree is committed to by digest, not just reported.
        "parents": funding.receipt_parents(hub_jobs) if funding is not None else [],
    }
    if local.x402_settlement is not None:
        # Paid over x402: the work receipt's settlement is the x402 receipt itself
        # (awr/adoption/x402-receipt/PROFILE.md), not a ledger hold this call never had.
        from aimarket_hub import x402_offer_receipt

        binding = x402_offer_receipt.awr_settlement(local.x402_settlement)
        if binding is not None:
            receipt_context["settlement"] = binding
    receipt_artifacts = plugins.run_receipt_hooks(result, receipt_context)
    provenance_receipt = (
        receipt_artifacts.get("provenance")
        # Compatibility for an older external provenance plugin that still
        # mutates the result in post_check. New issuers must use the final
        # hook; keeping the read fallback avoids silently dropping receipts
        # during a rolling hub/plugin upgrade.
        or result.pop("_provenance_receipt", None)
    )
    return provenance_receipt


def _local_answer(d: SimpleNamespace, call: _Call, local: _Local, result: Any, provenance_receipt: Any,
                  acex_revenue: Any, acex_audit_rewards: Any) -> JSONResponse:
    plugins = d.plugins
    price, list_price, elapsed_ms, sandbox_meta = local.price, local.list_price, local.elapsed_ms, local.sandbox_meta
    receipt, remaining, verification_env, vs_rejection = (
        local.receipt, local.remaining, local.verification_env, local.vs_rejection)
    response_body = {
        "success": True,
        "result": result,
        "receipt": receipt,
        "price_usd": price,
        "list_price_usd": list_price,
        "latency_ms": elapsed_ms,
        "safety_checked": True,
        "plugins_checked": plugins.count(),
        "protocol_version": "v2",
    }
    if sandbox_meta:
        response_body.update(sandbox_meta)
    if provenance_receipt:
        response_body["provenance_receipt"] = provenance_receipt
    if acex_revenue is not None:
        response_body["acex_revenue"] = acex_revenue
    if acex_audit_rewards is not None:
        response_body["acex_audit_rewards"] = acex_audit_rewards
    if remaining is not None:
        response_body["remaining_balance"] = remaining
    if verification_env is not None:
        # HTTP 200 even on a refunded verdict: the SERVICE succeeded and the
        # buyer keeps the output — the money outcome lives in the envelope
        # (quality escrow, not censorship; contrast the safety-gate 403,
        # which withholds output).
        response_body["verification"] = verification_env
    if vs_rejection is not None:
        response_body["rejection_receipt"] = vs_rejection
    # The caller keeps the output, so the trial was earned. Note this sits
    # alongside the verification envelope above: a refunded quality verdict still
    # delivered the result, and the free tier follows the money here rather than
    # inventing a second definition of "delivered".
    local.delivered = True
    headers = None
    if local.x402_settlement is not None:
        from aimarket_hub import x402

        response_body["x402_settlement"] = local.x402_settlement
        headers = {"PAYMENT-RESPONSE": x402.encode_header(local.x402_settlement),
                   "Access-Control-Expose-Headers": "PAYMENT-RESPONSE"}
    return JSONResponse(status_code=200, content=response_body, headers=headers)


def _x402_settlement(d: SimpleNamespace, call: _Call, local: _Local) -> dict[str, Any] | None:
    """For a call paid over x402 to the seller and delivered: the x402 SettlementResponse, with
    the signed receipt of the Offer and Receipt extension. The answer carries it in the body
    (``x402_settlement``) and as the PAYMENT-RESPONSE header x402 clients read; the work
    receipt carries its receipt as `settlement`. Never raises: a fault leaves the settlement
    out, never the buyer's result."""
    accepted = local.x402_accepted
    if not (isinstance(accepted, dict) and accepted.get("ok") and accepted.get("rail") == "seller_direct"):
        return None
    try:
        from aimarket_hub import x402, x402_offer_receipt

        if not x402_offer_receipt.enabled():
            return None
        base = (d.config.hub_url or "").rstrip("/")
        url = call.request.url
        resource_url = f"{base}{url.path}{('?' + url.query) if url.query else ''}" if base else str(url)
        return x402_offer_receipt.settlement_response(
            d.signer, network=x402.caip2(), resource_url=resource_url,
            payer=str(accepted.get("payer") or call.payer_wallet or ""),
            transaction=str(accepted.get("tx_hash") or ""),
        )
    except Exception:  # noqa: BLE001
        d.logger.exception("x402 settlement response for %s left out", call.body.capability_id)
        return None


def _local_unwind(d: SimpleNamespace, call: _Call, local: _Local) -> None:
    """Hand back what an undelivered call holds: the trial, the X-Payment claim, the
    reservation."""
    credits_ledger, logger, _release_market_payment = call.credits_ledger, d.logger, d._release_market_payment
    trial_visitor, delivered, x402_accepted = local.trial_visitor, local.delivered, local.x402_accepted
    reserved, resolved, nonce, hold_rail = local.reserved, local.resolved, local.nonce, local.hold_rail
    if trial_visitor and not delivered:
        # Same rules as the reservation release below: never raise out of
        # `finally`, never fail silently. The safety-gate 403 promises a refund
        # in its response body — this is what makes that promise true for a free
        # caller as well as a paying one.
        try:
            trial_release = release_sandbox_trial(trial_visitor)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "invoke: releasing the sandbox trial for %s raised: %s",
                trial_visitor, exc,
            )
        else:
            if trial_release.get("error"):
                logger.error(
                    "invoke: failed to release the sandbox trial for %s: %s",
                    trial_visitor, trial_release["error"],
                )
    # The same for a seller-direct payment, which until now had no release at
    # all: `_settle_market_payment` burns both replay keys the moment the
    # receipt verifies, so a provider 502, a safety block, a failed capture or
    # any exception left the buyer having paid for a call that never ran and
    # holding a nonce that could never be presented again. The money is with
    # the seller either way — this returns the CLAIM, so the payment is
    # redeemable on a retry instead of consumed for nothing.
    if not delivered:
        _release_market_payment(x402_accepted)

    # Single release point for the pre-execution reservation. Runs on EVERY
    # exit between reserve and settle — the provider 502s, the safety
    # post-block 403 (whose response promises a refund, so this is what
    # makes that promise true), a failed capture, a failed verify
    # registration, or any unexpected exception. release_hold is a no-op
    # once the hold has been captured or already released, so a late
    # exception on an already-settled invoke cannot double-refund.
    if reserved and not resolved:
        _local_withdraw_escrow_window(d, local, "the call was not delivered")
        # Must not raise out of `finally` (it would mask the real error),
        # but must never be silent either: an unreleased reservation is the
        # buyer's money in limbo, and it blocks channel close.
        try:
            release = (
                credits_ledger.release_hold(nonce)
                if hold_rail == "credits" and credits_ledger is not None
                else invoke.release_hold(nonce)
            )
        except Exception as exc:
            logger.error(
                "invoke: release of reservation %s raised: %s", nonce, exc,
            )
        else:
            if release.get("error"):
                logger.error(
                    "invoke: failed to release reservation %s: %s",
                    nonce, release.get("error"),
                )


# Imported after the phases on purpose: invoke.py imports these modules to call the
# branches, and any of them may load first. The channel-ledger functions are read as
# invoke.<name> at call time because that is where they are patched.
from aimarket_hub.hub_routes import invoke  # noqa: E402
from aimarket_hub.hub_routes.invoke import (  # noqa: E402
    _Call,
    _Local,
    _caller_class_now,
    _post_check,
)
from aimarket_hub.hub_routes.invoke_parts.local_admission import (  # noqa: E402
    _local_withdraw_escrow_window,
)
