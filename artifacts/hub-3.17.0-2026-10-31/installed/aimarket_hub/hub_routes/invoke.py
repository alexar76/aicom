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

This module holds the route, the request reading and the per-call state. The phases live in
`invoke_parts/`, one module per branch and stage: `local_admission` and `local_delivery`,
`federated_admission` and `federated_delivery` (before and from the provider or peer call).

Every phase takes `d`, the collaborators `register` was handed plus api.py's helpers. The
channel-ledger functions (`hold_channel`, `capture_hold`, `channel_escrow_binding`, …) are
read as `invoke.<name>` from this module's globals, which is where tests patch them.
"""


from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub import credits, invoke_funding, settle, x402
from aimarket_hub.api_models import InvokeRequest
# Not called here: the phases in invoke_parts/ read these as invoke.<name> at call time, so
# this module is the one place to patch the channel ledger for the whole invoke path.
from aimarket_hub.channels import (  # noqa: F401
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
from aimarket_hub.invoke_outcome import (
    missing_required_inputs,
    OUTCOME_INCOMPLETE,
)
from aimarket_hub.mandates import MandateStore
from aimarket_hub.models import InvocationStat
from aimarket_hub.plugin import PluginRegistry
from aimarket_hub.safety_gate import SafetyGate
from aimarket_hub.sandbox_trials import sandbox_enabled
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
    # The x402 SettlementResponse of a call paid to the seller over x402 and delivered: the
    # answer's PAYMENT-RESPONSE and, as AWR-X402/1, the work receipt's `settlement`.
    x402_settlement: dict[str, Any] | None = None
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
                raise HTTPException(422, "pipeline.run input requires run_id, access_token and optional signed transactions") from None
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
        return finished

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


# The two branches live in invoke_parts/, imported after this module's own code: they read
# its state classes and helpers, and either side may load first.
from aimarket_hub.hub_routes.invoke_parts.federated_admission import _invoke_federated  # noqa: E402
from aimarket_hub.hub_routes.invoke_parts.local_admission import _invoke_local  # noqa: E402
