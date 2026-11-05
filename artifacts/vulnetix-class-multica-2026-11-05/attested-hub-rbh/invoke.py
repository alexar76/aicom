"""POST /invoke: local, federated and pipeline calls, with payment, escrow, settlement and
receipts.

`_invoke_core` reads the caller and how it means to pay once (`_read_call`, into a `_Call`),
then runs one of two branches, each a sequence of phases over its own explicit state:

- `_invoke_local` (state `_Local`): the safety pre-check, the capability, the quote, a
  seller-direct payment and the paywall, the verification plan, the escrow authorization,
  the reservation and the trial; then, inside one try whose `finally` is `_local_unwind`,
  execution, the delivery checks, settlement, the receipt, bookkeeping and the answer.
- `_invoke_federated` (state `_Fed`): the peer, the quote and routing fee, the escrow
  authorization, payment or trial, the routing-fee reservation; then, inside one try whose
  `finally` is `_fed_unwind`, the peer call, settlement, the routing fee and the answer.

Every phase takes `d`, the collaborators `register` was handed plus api.py's helpers. The
channel-ledger functions (`hold_channel`, `capture_hold`, `channel_escrow_binding`, …) are
read from this module's globals, which is where tests patch them.
"""


from __future__ import annotations

import contextlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import logging as _rb_logging

from aimarket_hub import receipt_binding

from aimarket_hub import credits, invoke_funding, provider_buyer_ref, provider_request_auth, settle, verified_settlement, x402
from aimarket_hub.api_models import InvokeRequest
from aimarket_hub.channels import (
    capture_hold,
    channel_balance,
    channel_escrow_binding,
    channel_payer,
    debit_channel,
    hold_channel,
    release_hold,
)
from aimarket_hub.config import HubConfig
from aimarket_hub.credits import CreditsLedger
from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable
from aimarket_hub.invoke_outcome import (
    classify_invoke_outcome,
    missing_required_inputs,
    OUTCOME_INCOMPLETE,
)
from aimarket_hub.mandates import MandateStore
from aimarket_hub.models import InvocationStat
from aimarket_hub.plugin import PluginRegistry
from aimarket_hub.safety_gate import SafetyGate
from aimarket_hub.sandbox_trials import (
    consume_sandbox_trial,
    free_tier_covers,
    model_budget_refusal,
    release_sandbox_trial,
    sandbox_demo_result,
    sandbox_enabled,
    sandbox_stub_invoke_enabled,
)
from aimarket_hub.signing import Signer
from aimarket_hub.subcontract import JobStore
from aimarket_hub.supply_security import SupplySecurity
from aimarket_hub.verified_settlement import VerifiedSettlementService



@dataclass
class _Call:
    """Who is calling and how they mean to pay, read once by `_read_call` for both branches."""

    body: InvokeRequest
    request: Request
    x_payment_channel: str | None
    x_payment_channel_secret: str | None
    x_sandbox_visitor: str | None
    payment_signature: str | None
    x_payment_nonce: str | None
    x_payment_secret: str | None
    authorization: str
    sandbox_mode: bool
    crypto_on: bool
    credits_on: bool
    credits_ledger: Any
    credit_account: str
    funding: Any
    x402_payment: dict[str, Any] | None
    x402_raw: str
    price_rail_active: bool
    consumer_hub_label: str
    client_ip: str
    forwarded_call: bool
    rate_key: str
    payer_wallet: str = ""  # the verified x402 payer, once there is one
    # Another hub routed this call here (X-AIMarket-Routing-Hub). Its credits or channel are that hub's,
    # not the buyer's, so they never name an owner for the operator's providers (provider_buyer_ref).
    routed_by_hub: bool = False


@dataclass
class _Local:
    """One local invoke, from the capability lookup to `_local_unwind`."""

    t0: float
    factory_url: str
    cap: Any = None
    invoke_url: str = ""
    provider_invoke_failed: bool = False
    list_price: float = 0.0
    seller_payee: Any = None
    x402_accepted: dict[str, Any] | None = None
    vs_plan: Any = None
    price: float = 0.0
    accepted_authorization: Any = None
    nonce: str = ""
    reserved: bool = False   # a ledger hold on `nonce` is outstanding
    resolved: bool = False   # the hold reached its terminal owner (captured / verify)
    remaining: float | None = None
    # Which ledger holds the reservation. Capture and release must go back to the
    # same one — a hold taken on credits and captured on the channel ledger would
    # leave the buyer's money reserved forever and record a debit against nobody.
    hold_rail: str = ""
    sandbox_meta: dict[str, Any] = field(default_factory=dict)
    trial_visitor: str = ""
    delivered: bool = False   # the call returned a result to the buyer
    elapsed_ms: int = 0
    receipt: dict[str, Any] | None = None
    verification_env: Any = None
    vs_rejection: Any = None

    @property
    def vs_deferred(self) -> bool:
        """A Pay-on-Verified hold: the verdict, not this call, captures it and accrues revenue."""
        return self.vs_plan is not None and self.vs_plan.active and self.vs_plan.paid


@dataclass
class _Fed:
    """One federated invoke, from the peer lookup to `_fed_unwind`."""

    peer: Any = None
    verify_env: Any = None
    cap: Any = None
    list_price: float = 0.0
    sells: bool = False
    peer_key: str | None = None
    resells: bool = False
    price: float = 0.0
    listed: Any = None
    listed_price: float = 0.0
    expected_fee: float = 0.0
    authorized_total: float = 0.0
    escrow_binding: str = ""
    authorization: Any = None
    nonce: str = ""
    reserved: bool = False
    settled: bool = False
    # Which ledger the federated reservation lives in — same reason as `hold_rail`
    # on the local branch: capture and release must return to the ledger that held.
    hold_rail: str = ""
    # A routing-fee reservation, taken BEFORE the peer is asked to do anything. See
    # `_fed_reserve_routing_fee` for why it is no longer collected after the fact.
    fee_nonce: str = ""
    fee_rail: str = ""
    fee_reserved_usd: float = 0.0
    # A free-tier trial is a reservation too, released on every path that does not
    # deliver — the mirror of reserved/settled for the paid path.
    trial_visitor: str = ""
    trial_delivered: bool = False
    sandbox_meta: dict[str, Any] = field(default_factory=dict)
    x402_accepted: dict[str, Any] | None = None
    started: float = 0.0


# api.py's module-level helpers the phases read. Looked up when register runs, not imported
# at the top, because api.py imports this module.
_API_HELPERS = (
    "_MAX_REPORTED_LATENCY_MS",
    "_MAX_REPORTED_PRICE_USD",
    "_announced_relay",
    "_as_float",
    "_authorization_too_short",
    "_ceil_to_cents",
    "_client_address",
    "_is_safe_path",
    "_observe_answer",
    "_opaque_buyer",
    "_peer_invoke_endpoint",
    "_peer_payment_headers",
    "_peer_sells_direct",
    "_provider_channel_ref",
    "logger",
)


def _a2a_charge_task(request: Request) -> str:
    """The A2A task this invoke runs for, when the A2A bridge itself sent it — proven by the
    process's internal secret, so no outside caller can attach its call to someone's task."""
    import hmac

    from aimarket_hub import a2a
    from aimarket_hub.a2a_tasks import is_task_id

    task_id = (request.headers.get(a2a.TASK_HEADER) or "").strip()
    secret = (request.headers.get(a2a.INTERNAL_HEADER) or "").strip()
    if not task_id or not secret or not is_task_id(task_id):
        return ""
    return task_id if hmac.compare_digest(secret, a2a.INTERNAL_SECRET) else ""


def register(
    *,
    TrustOracleUnavailable: type[Exception],
    _TRUSTED_PROXIES: frozenset[str],
    _bind_hub_fee_payee: Callable[..., Any],
    _bind_listing_payee: Callable[..., Any],
    _check_invoke_rate: Callable[..., Any],
    _credit_hearth_owner: Callable[..., Any],
    _ecosystem_policy: Callable[..., Any],
    _mcp_caller: Callable[..., Any],
    _pay_publisher_share: Callable[..., Any],
    _payment_hint: Callable[..., Any],
    _payment_ways: Callable[..., Any],
    _pays_a_third_party: Callable[..., Any],
    _release_market_payment: Callable[..., Any],
    _resolve_invoke_consumer_hub: Callable[..., Any],
    _settle_market_payment: Callable[..., Any],
    _unbind_payee: Callable[..., Any],
    builtin_safety: SafetyGate,
    config: HubConfig,
    db: HubDatabase,
    hub_credits: CreditsLedger,
    hub_jobs: JobStore,
    hub_mandates: MandateStore,
    late: SimpleNamespace,
    plugins: PluginRegistry,
    router: APIRouter,
    signer: Signer,
    supply_security: SupplySecurity,
    verify_svc: VerifiedSettlementService,
) -> None:
    """Attach POST /invoke to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub import api

    # What the invoke phases below read: everything register was handed, and api.py's helpers.
    d = SimpleNamespace(**locals(), **{name: getattr(api, name) for name in _API_HELPERS})

    @router.post("/invoke")
    async def invoke(
        body: InvokeRequest,
        request: Request,
        x_payment_channel: str | None = Header(default=None, alias="X-Payment-Channel"),
        x_payment_channel_secret: str | None = Header(default=None, alias="X-Payment-Channel-Secret"),
        x_aimarket_route_ok: str | None = Header(default=None, alias="X-AIMarket-Route-Ok"),
        x_sandbox_visitor: str | None = Header(default=None, alias="X-AIMarket-Sandbox-Visitor"),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_payment: str | None = Header(default=None, alias="X-PAYMENT"),
        payment: str | None = Header(default=None, alias="PAYMENT"),
        payment_signature: str | None = Header(default=None, alias="PAYMENT-SIGNATURE"),
        x_payment_nonce: str | None = Header(default=None, alias="X-Payment-Nonce"),
        x_payment_secret: str | None = Header(default=None, alias="X-Payment-Secret"),
        authorization: str = Header(default=""),
    ):
        """The invoke route: mandates and subcontracting around the payment path.

        `invoke_funding.prepare` decides who pays and under whose limits BEFORE any money is
        reserved; `_invoke_core` runs the payment path unchanged except that it takes the
        funding account and ledger it is handed; `invoke_funding.finish` settles what
        prepare opened — on every exit, including an exception — and completes the answer.
        """
        client_nonce, nonce_error = receipt_binding.read_client_nonce(request.headers)
        if nonce_error:
            return JSONResponse(status_code=400, content={
                "success": False, "error": "client_nonce_invalid", "detail": nonce_error})
        if (body.product_id, body.capability_id, body.source_hub or "local") == ("hephaestus", "pipeline.run@v1", "local"):
            # This zero-price built-in owns an immutable wallet-funded graph. No
            # credit/trial credential can be mistaken for authority to pay its children.
            if body.subcontract or body.verify or any(request.headers.get(h) for h in (
                "X-API-Key", "X-AIMarket-Mandate", "X-AIMarket-Job", "X-AIMarket-Job-Grant",
                "X-AIMarket-Sandbox-Visitor", "X-Payment-Channel", "X-Payment", "Payment", "Payment-Signature",
            )):
                return JSONResponse(status_code=400, content={"success": False,
                    "error": "pipeline_funding_invalid", "detail": "pipeline.run uses its prepared buyer-signed payment bundle; send no credits grant or other payment"})
            if not _check_invoke_rate("pipeline:" + _mcp_caller(request)):
                raise HTTPException(429, "slow down")
            from pydantic import ValidationError
            from aimarket_hub.pipeline_provider import PipelineInput
            try:
                plan = PipelineInput.model_validate(body.input)
            except ValidationError:
                raise HTTPException(422, "pipeline.run input requires run_id, access_token and optional signed transactions")
            result = await late.pipeline_provider.invoke(plan, _mcp_caller(request))
            status = 200 if result["status"] in ("completed", "failed") else 202
            return JSONResponse(status_code=status, content=result, headers={"Cache-Control": "no-store"})
        ledger = hub_credits if credits.enabled() else None
        charge_task = _a2a_charge_task(request)
        if charge_task and ledger is not None:
            # An A2A task's own invoke (a2a.py sends it through this app): every reservation
            # and debit is named against the task before the money moves, so a restart
            # mid-call can be recovered from the ledger instead of guessed at.
            from aimarket_hub.a2a_tasks import A2ATaskStore, ChargeJournal

            ledger = ChargeJournal(ledger, A2ATaskStore(db._conn), charge_task)
            request.state.aimarket_charge_journal = ledger

        def _resolve_product(product_id: str, capability_id: str) -> str:
            # The same lookup the handler executes with, so a per-product limit is keyed on
            # the product that really runs, not on the product_id the caller typed.
            cap = db.get_capability(product_id, capability_id) or db.find_by_capability_id(capability_id)
            return str(getattr(cap, "product_id", "") or product_id)

        funding = await invoke_funding.prepare(
            request=request, body=body, credits_ledger=ledger, store=hub_mandates, jobs=hub_jobs,
            resolve_product=_resolve_product, routing_fee_bps=config.routing_fee_bps,
        )
        if isinstance(funding, JSONResponse):
            return funding
        request.state.aimarket_funding = funding
        result = None
        try:
            result = await _invoke_core(
                body, request,
                x_payment_channel=x_payment_channel,
                x_payment_channel_secret=x_payment_channel_secret,
                x_aimarket_route_ok=x_aimarket_route_ok,
                x_sandbox_visitor=x_sandbox_visitor,
                x_api_key=x_api_key,
                x_payment=x_payment,
                payment=payment,
                payment_signature=payment_signature,
                x_payment_nonce=x_payment_nonce,
                x_payment_secret=x_payment_secret,
                authorization=authorization,
            )
        except HTTPException as exc:
            if funding.job is None:
                raise
            # A root whose provider failed AFTER its subcontractors delivered still pays for
            # them (§6.3, cost-plus) — so its answer must carry the bill of materials and
            # the job id, or the buyer sees charges nothing explains. Same body FastAPI's
            # own handler would render, plus what finish() adds. A failed child also
            # keeps its job node identity so external payments can be reconciled.
            result = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                                  headers=getattr(exc, "headers", None))
        finally:
            finished = invoke_funding.finish(
                funding, result, credits_ledger=ledger, store=hub_mandates, jobs=hub_jobs,
            )
        return _bind_receipt(finished, body, client_nonce)

    def _bind_receipt(result: Any, body: InvokeRequest, client_nonce: str | None) -> Any:
        """Sign what was asked and what was answered next to the receipt (receipt_binding.py).

        Last, after finish(), so the digest covers the answer exactly as the buyer gets it.
        Never fails the call: a delivered answer without a binding is what every hub sent
        before this existed."""
        status, content = invoke_funding._body_of(result)
        if status != 200 or not isinstance(content, dict) or not content.get("success"):
            return result
        try:
            content = jsonable_encoder(content)
            binding = receipt_binding.build(
                content, input_payload=jsonable_encoder(body.input), client_nonce=client_nonce,
                hub_url=config.hub_url, signer=signer)
        except Exception as exc:  # noqa: BLE001
            _rb_logging.getLogger(__name__).error("receipt binding failed: %s", exc)
            return result
        if binding is None:
            return result
        content["receipt_binding"] = binding
        headers = {} if isinstance(result, dict) else {
            k: v for k, v in result.headers.items() if k.lower() not in ("content-length", "content-type")}
        if client_nonce:
            headers[receipt_binding.CLIENT_NONCE_ECHO_HEADER] = client_nonce
        return JSONResponse(status_code=status, content=content, headers=headers)

    async def _invoke_core(
        body: InvokeRequest,
        request: Request,
        *,
        x_payment_channel: str | None,
        x_payment_channel_secret: str | None,
        x_aimarket_route_ok: str | None,
        x_sandbox_visitor: str | None,
        x_api_key: str | None,
        x_payment: str | None,
        payment: str | None,
        payment_signature: str | None,
        x_payment_nonce: str | None,
        authorization: str,
        x_payment_secret: str | None = None,
    ):
        call = _read_call(
            d, body, request,
            x_payment_channel=x_payment_channel,
            x_payment_channel_secret=x_payment_channel_secret,
            x_sandbox_visitor=x_sandbox_visitor,
            x_api_key=x_api_key,
            x_payment=x_payment,
            payment=payment,
            payment_signature=payment_signature,
            x_payment_nonce=x_payment_nonce,
            x_payment_secret=x_payment_secret,
            authorization=authorization,
        )
        if isinstance(call, JSONResponse):
            return call
        if body.source_hub == "local":
            return await _invoke_local(d, call)
        return await _invoke_federated(d, call)


# ── The caller, read once ────────────────────────────────────────────────────────────


def _read_call(
    d: SimpleNamespace,
    body: InvokeRequest,
    request: Request,
    *,
    x_payment_channel: str | None,
    x_payment_channel_secret: str | None,
    x_sandbox_visitor: str | None,
    x_api_key: str | None,
    x_payment: str | None,
    payment: str | None,
    payment_signature: str | None,
    x_payment_nonce: str | None,
    x_payment_secret: str | None,
    authorization: str,
) -> _Call | JSONResponse:
    """Who is calling and how they mean to pay, or the answer that ends the call here: an
    unknown API key, a malformed payment header, a caller over the rate limit."""
    config, hub_credits = d.config, d.hub_credits
    _resolve_invoke_consumer_hub, _check_invoke_rate = d._resolve_invoke_consumer_hub, d._check_invoke_rate
    _client_address, _announced_relay, _TRUSTED_PROXIES = d._client_address, d._announced_relay, d._TRUSTED_PROXIES
    sandbox_mode = bool(x_sandbox_visitor and sandbox_enabled())
    # Master crypto switch (default OFF): when off, every invoke is served FREE —
    # no 402, no payment channel, no debit. Capabilities still execute normally.
    crypto_on = config.crypto_enabled
    # Credits: the second rail, and the only one a hub can charge on without a chain.
    # `price_rail_active` is what decides whether a listed price is real money — before
    # this existed it was `crypto_on` alone, which is why a default deployment served
    # every priced capability for free.
    credits_on = credits.enabled()
    credits_ledger = (getattr(request.state, "aimarket_charge_journal", None) or hub_credits) if credits_on else None
    credit_account = ""
    if credits_ledger is not None and x_api_key:
        credit_account = credits_ledger.resolve(x_api_key)
        if not credit_account:
            # Fail closed on an unknown key rather than falling through to the free
            # path: a typo in a key must not silently become an unbilled invoke.
            return JSONResponse(status_code=401, content={
                "success": False,
                "error": "invalid_api_key",
                "detail": "X-API-Key is not a known credit account on this hub",
                "protocol_version": "v2",
            })
    # A mandate or a job allowance names the funding account itself, and replaces the
    # ledger for this request with one that reserves the mandate's limits (or draws on
    # the allowance) alongside the money — see invoke_funding.py. Every hold, capture
    # and release below, on either branch, therefore goes through that ledger.
    funding = getattr(request.state, "aimarket_funding", None)
    if funding is not None and credits_ledger is not None:
        if funding.account_id:
            credit_account = funding.account_id
        credits_ledger = funding.wrap(credits_ledger)
    # Market rail: a payer who answered our 402 by sending USDC to the
    # seller. The header is a tx hash (HESTIA) or an x402 PAYMENT-SIGNATURE
    # that names the same payee and carries the settle transaction.
    x402_payment = None
    x402_raw = (x_payment or payment or payment_signature or "").strip()
    if x402_raw and x402.accept_enabled():
        if settle.is_tx_hash(x402_raw):
            x402_payment = {"txHash": x402_raw}
        else:
            decoded = x402.decode_payment(x402_raw)
            if decoded is None:
                return JSONResponse(status_code=400, content={
                    "success": False,
                    "error": "payment_malformed",
                    "detail": "the payment header is neither a tx hash, base64 JSON nor JSON",
                    "protocol_version": "v2",
                })
            x402_payment = decoded
    price_rail_active = crypto_on or credits_on or bool(x402_payment)
    request.state.aimarket_capability_id = body.capability_id
    from aimarket_hub.mcp_gateway import MCP_CALLER_HEADER

    consumer_hub_label = _resolve_invoke_consumer_hub(
        x_sandbox_visitor=x_sandbox_visitor,
        x_payment_channel=x_payment_channel,
        authorization=authorization,
        credit_account=credit_account,
        # Not from the header: "x402" is set below, only once the payment verifies. A junk
        # X-Payment on a free call used to show on the public feed as x402-paid demand.
        x402_paid=False,
        mcp_caller=request.headers.get(MCP_CALLER_HEADER),
    )

    # Proxy-aware (see _client_address): behind nginx the raw peer is the proxy, so
    # keying the limiter on it would put every caller in one bucket.
    client_ip = _client_address(request, _TRUSTED_PROXIES)

    # SELF vs EXT for the row this call will write (ecosystem.py). A call another hub
    # routes here, or a seller operation another hub bought, arrives from THAT hub's
    # address and often on its credentials: the routing hub saw the real buyer and
    # classifies it there, so here it is never SELF. These markers are unauthenticated,
    # which is fine — they can only push a row towards EXT.
    _peer = str(getattr(getattr(request, "client", None), "host", "") or "")
    forwarded_call = bool(
        (request.headers.get("x-aimarket-routing-hub") or "").strip()
        or (request.headers.get("x-aimarket-buyer") or "").strip()
        or str(x_sandbox_visitor or "").strip().startswith("hub-fed-")
        or getattr(request.state, "seller_operation_id", None)
        or _announced_relay(_peer, request.headers.get("x-forwarded-for") or "", _TRUSTED_PROXIES)
    )

    # Per-consumer rate limit (griefing / provider-hammering protection). Key on
    # the network/session identity (client_ip), NOT the unauthenticated
    # X-Payment-Channel header: a caller could rotate that header per request to
    # get a fresh empty bucket and nullify the limiter. Sandbox flows fall back
    # to the sandbox-visitor id when there is no client address.
    rate_key = client_ip or x_sandbox_visitor or "anonymous"
    if not _check_invoke_rate(rate_key):
        return JSONResponse(status_code=429, content={
            "success": False,
            "error": "rate_limited",
            "detail": "invoke rate limit exceeded — slow down",
            "protocol_version": "v2",
        })
    return _Call(
        body=body,
        request=request,
        x_payment_channel=x_payment_channel,
        x_payment_channel_secret=x_payment_channel_secret,
        x_sandbox_visitor=x_sandbox_visitor,
        payment_signature=payment_signature,
        x_payment_nonce=x_payment_nonce,
        x_payment_secret=x_payment_secret,
        authorization=authorization,
        sandbox_mode=sandbox_mode,
        crypto_on=crypto_on,
        credits_on=credits_on,
        credits_ledger=credits_ledger,
        credit_account=credit_account,
        funding=funding,
        x402_payment=x402_payment,
        x402_raw=x402_raw,
        price_rail_active=price_rail_active,
        consumer_hub_label=consumer_hub_label,
        client_ip=client_ip,
        forwarded_call=forwarded_call,
        rate_key=rate_key,
        routed_by_hub=bool((request.headers.get("x-aimarket-routing-hub") or "").strip()),
    )


def _label_x402_paid(d: SimpleNamespace, call: _Call) -> str:
    from aimarket_hub.mcp_gateway import MCP_CALLER_HEADER

    return d._resolve_invoke_consumer_hub(
        x_sandbox_visitor=call.x_sandbox_visitor, x_payment_channel=call.x_payment_channel,
        authorization=call.authorization, credit_account=call.credit_account, x402_paid=True,
        mcp_caller=call.request.headers.get(MCP_CALLER_HEADER))


def _caller_class_now(d: SimpleNamespace, call: _Call) -> str:
    try:
        return d._ecosystem_policy().caller_class(
            label=call.consumer_hub_label, client_ip=call.client_ip,
            payer_wallet=call.payer_wallet, forwarded=call.forwarded_call,
        )
    except Exception:  # a metrics column must never fail the call
        d.logger.warning("caller_class could not be decided", exc_info=True)
        return ""


def _refuse_incomplete_input(d: SimpleNamespace, call: _Call):
    """A 400 naming the fields the caller left out, or None to carry on.

    Asked at both execution points rather than once at the top, and that placement
    is the whole subtlety. Put before the paywall, it answers 400 to an UNPAID call
    on a priced capability — which breaks x402: the client is waiting for a 402 to
    know what to pay, and telling it the input is short instead strands the payment
    flow. `deploy_hub_rebuild.sh` probes exactly that (every selling peer, empty
    input, expects 402) and rolled the apex hub back for it. Payment first, then
    this, then the provider — so nobody is told what they are missing before being
    told what it costs, and nobody crosses the federation to find out either.

    The capability's own `input_schema` is the only source. `anyOf`/`oneOf` are read
    as ALTERNATIVE required groups, because that is how a capability with two ways
    in declares itself — ATLAS's watchbox takes a stored id plus its owner token OR
    a bare bbox, and a flat `required` list cannot say that.
    """
    db, body = d.db, call.body
    try:
        described = db.get_capability(body.product_id, body.capability_id)
        if described is None:
            described = db.find_by_capability_id(body.capability_id)
        absent = missing_required_inputs(
            body.input, getattr(described, "input_schema", None),
        )
    except Exception:
        # A lookup that fails must not turn a valid call into a 400. The provider
        # still answers, and the classifier still reads its refusal, exactly as
        # before this check existed.
        return None
    if not absent:
        return None
    stat = InvocationStat(
        capability_id=body.capability_id,
        product_id=body.product_id,
        source_hub=body.source_hub or "local",
        price_usd=0.0,
        latency_ms=0,
        success=False,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        consumer_hub=call.consumer_hub_label,
        outcome=OUTCOME_INCOMPLETE,
        caller_class=_caller_class_now(d, call),
        purpose=body.purpose,
    )
    with contextlib.suppress(Exception):
        db.record_invocation(stat)
    wanted = " or ".join(", ".join(group) for group in absent)
    plural = len(absent) > 1 or len(absent[0]) > 1
    return JSONResponse(status_code=400, content={
        "success": False,
        "error": "incomplete_input",
        "detail": (
            f"{body.capability_id} requires {wanted} — the request did not include "
            f"{'them' if plural else 'it'}. This is not a hub or provider failure "
            f"and is not counted as one."
        ),
        "missing": absent[0] if len(absent) == 1 else absent,
        "accepts": absent,
        "capability_id": body.capability_id,
        "protocol_version": "v2",
    })


def _post_check(d: SimpleNamespace, result: Any, context: dict[str, Any]):
    """Plugins first, then the built-in gate, on an output about to be accepted: the 403 that
    withholds it (its refund made true by the branch's unwind), or None."""
    plugins, builtin_safety = d.plugins, d.builtin_safety
    post_block = plugins.run_post_checks(result, context)
    if not post_block:
        verdict = builtin_safety.post_response_check(result)
        if not verdict.passed:
            post_block = {
                "blocked": True,
                "category": verdict.category,
                "reason": verdict.reason,
                "refund": True,
                "plugin": "builtin-safety",
            }
    if post_block:
        return JSONResponse(status_code=403, content={
            "success": False,
            "error": "plugin_blocked_response",
            "category": post_block.get("category"),
            "reason": post_block.get("reason"),
            "blocked_by": post_block.get("plugin"),
            "refund": {"refunded": True},
            "protocol_version": "v2",
        })
    return None


# ── Local: a capability this hub serves itself ───────────────────────────────────────


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
            escrow_binding = channel_escrow_binding(x_payment_channel)

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
        pay_result = hold_channel(
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
        pay_result = debit_channel(
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
            else release_hold(nonce)
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
            payer, rail = channel_payer(call.x_payment_channel), "channel"
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
        # Private Hub→provider token: only for operator-named local
        # gateway hosts (e.g. kova-api). Use the post-rewrite host so
        # localhost→gateway remaps still get the token. Never forward
        # to federated / public URLs.
        capability_token = os.environ.get("AIMARKET_CAPABILITY_TOKEN", "").strip()
        target_host = (urlparse(resolve_invoke_url(invoke_url)).hostname or "").lower()
        if capability_token and target_host in set(invoke_gateway_hosts()):
            provider_headers["X-AIMarket-Internal-Token"] = capability_token
            # Who the buyer is, as one stable pseudonym the operator's own provider can key
            # the buyer's data by (Attested Memory owners). Same gate as the token, so a
            # third-party seller never gets it; left out for anonymous and trial calls.
            buyer_ref = provider_buyer_ref.buyer_ref(d.signer, call, local)
            if buyer_ref:
                provider_headers[provider_buyer_ref.HEADER] = buyer_ref
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
            else capture_hold(nonce)
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
                    _bal = channel_balance(x_payment_channel)
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

    receipt_artifacts = plugins.run_receipt_hooks(result, {
        # The answer carries this value as `result`; the signed subject says so.
        "output_digest_of": "result",
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
    })
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
    headers = _x402_settlement(d, call, local, response_body)
    return JSONResponse(status_code=200, content=response_body, headers=headers or None)


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
                else release_hold(nonce)
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


# ── Federated: a capability another hub serves ───────────────────────────────────────


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
            fed.escrow_binding = channel_escrow_binding(x_payment_channel)

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
        fed_hold = hold_channel(
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
                else release_hold(fed_nonce)
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
            fee_hold = hold_channel(
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

        tool_endpoint = _fed_tool_endpoint(fed)
        if tool_endpoint:
            # An x402 seller that answers at each tool's own URL and has no invoke route
            # (mach402.dev, agent-exec.448c.org). Same bare input as the legacy path, and the
            # same 402 passthrough and result handling below.
            resp = await safe_post(tool_endpoint, json=body.input, headers=headers)
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
            )
        else:
            # product_id / capability_id are interpolated into the upstream path,
            # so they get the same traversal guard the local branch applies.
            if not _is_safe_path(body.product_id) or not _is_safe_path(body.capability_id):
                raise HTTPException(status_code=400, detail="Invalid product or capability ID")
            provider_url = f"{peer.url}/capabilities/{body.product_id}/{body.capability_id}/invoke"
            resp = await safe_post(provider_url, json=body.input, headers=headers)
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
            else capture_hold(fed_nonce)
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
            else capture_hold
        )
        _fee_ledger_release = (
            credits_ledger.release_hold
            if fed_fee_rail == "credits" and credits_ledger is not None
            else release_hold
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
                fee_result = debit_channel(
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
    # for local work, naming the actual provider hub. Charged price is the amount
    # THIS hub settled, never the peer's self-reported list price.
    #
    # outputDigest covers the member of this answer that carries the work, named in
    # the signed subject as `outputDigestOf`; the peer's own receipt is committed to
    # separately (`gatewayReceiptDigest`). It used to digest the whole envelope at this
    # point — which then grew (provenance_receipt, mandate, subcontracting), so no
    # buyer could recompute it from the answer they received.
    if bool(result_data.get("success", False)):
        fed_elapsed_ms = int((time.time() - fed_started) * 1000)
        output_member = "output" if "output" in result_data else "result"
        receipt_artifacts = plugins.run_receipt_hooks(result_data.get(output_member), {
            "output_digest_of": output_member,
            "routed": True,
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
                else release_hold(fed_nonce)
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
                else release_hold(fed_fee_nonce)
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


def _x402_settlement(d: SimpleNamespace, call: _Call, local: _Local, response_body: dict) -> dict[str, str]:
    """For a call paid over x402 to the seller and delivered: the x402 SettlementResponse, with
    the signed receipt of the Offer and Receipt extension, in the body (``x402_settlement``)
    and as the PAYMENT-RESPONSE header x402 clients read. Never raises: a fault leaves the
    settlement out, never the buyer's result. (Ported from main's invoke_parts/local_delivery.py.)"""
    accepted = local.x402_accepted
    if not (isinstance(accepted, dict) and accepted.get("ok") and accepted.get("rail") == "seller_direct"):
        return {}
    try:
        from aimarket_hub import x402, x402_offer_receipt

        if not x402_offer_receipt.enabled():
            return {}
        base = (d.config.hub_url or "").rstrip("/")
        url = call.request.url
        resource_url = f"{base}{url.path}{('?' + url.query) if url.query else ''}" if base else str(url)
        settlement = x402_offer_receipt.settlement_response(
            d.signer, network=x402.caip2(), resource_url=resource_url,
            payer=str(accepted.get("payer") or call.payer_wallet or ""),
            transaction=str(accepted.get("tx_hash") or ""),
        )
        response_body["x402_settlement"] = settlement
        return {"PAYMENT-RESPONSE": x402.encode_header(settlement),
                "Access-Control-Expose-Headers": "PAYMENT-RESPONSE"}
    except Exception:  # noqa: BLE001
        d.logger.exception("x402 settlement response for %s left out", call.body.capability_id)
        return {}
