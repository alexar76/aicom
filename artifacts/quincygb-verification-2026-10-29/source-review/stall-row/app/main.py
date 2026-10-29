"""StallRow — one x402 service hosting a row of paid micro-services.

Owner's portfolio strategy (2026-10-21): many real stalls, expect one
or two to hit. One deployment, one facilitator configuration, every
route independently priced, listed, and settled.

Paid:   POST /v1/* routes (see app/discovery.py ROUTES)
Free:   GET  /, /health, /quote, /.well-known/x402, /skill.md, /llms.txt
        POST /v1/recheck/pack-balance (pack id is the credential)
        POST /v1/nudge (signed fleet-health mail — see services/nudge.py)
        POST /v1/probe (one-link checker — see services/probe.py)
        POST /v1/claim/start, POST /v1/claim/verify (stall claim
             challenges — see services/claims.py)
        GET  /v1/claim/status (an origin's patrol history; only a
             claim session token issued for that origin unlocks it)
        POST /v1/hosted-inbox/<origin-key> (signed fleet-health
             knocks for a CLAIMED origin — see services/hosted_inbox.py)
        GET  /v1/claim/inbox, POST /v1/claim/inbox/config (the
             claimed origin's mailbox read + relay config, session-gated)
        POST /v1/internal/nudges (owner read, fleet-internal secret)
        POST /v1/internal/claims-history (claims history snapshot
             upload, fleet-internal secret)

Recheck packs: POST /v1/recheck presenting a pack id (body field
`pack_id` or X-Recheck-Pack header) spends a prepaid credit instead
of paying per call, so the middleware below lets such requests
through to the handler, which validates the pack against the store
before any check runs — an invalid pack delivers nothing.

Failure honesty: when an upstream cannot supply the data, handlers
raise UpstreamError / return 502 — and the x402 middleware does NOT
settle payment on >= 400 responses, so nobody pays for undelivered data.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any
from urllib.parse import urlsplit

# Scrub bracketed-IPv6 no_proxy entries before any x402 SDK client is
# constructed (see list-smith/app/main.py — the SDK's httpx client dies
# on "[::1]" entries and turns every unpaid call into a 500).
for _var in ("no_proxy", "NO_PROXY"):
    _val = os.environ.get(_var)
    if _val:
        _kept = [e for e in _val.split(",") if "[" not in e and "]" not in e]
        os.environ[_var] = ",".join(_kept)

import httpx
import asyncio
import hashlib
import hmac
import json

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption, RouteConfig
from x402.http.middleware import fastapi_payment_middleware
from x402.mechanisms.evm.exact.server import ExactEvmScheme
from x402.mechanisms.svm.exact.server import ExactSvmScheme as ExactSvmServerScheme
from x402.server import x402ResourceServer

from .blockscout import Blockscout
from .config import PRICE_UNITS, SOLANA_ACCEPT_PATHS, load_settings
from .solana_rail import SvmReplayGuard, make_after_settle_hook, make_before_verify_hook
from .discovery import OWNERSHIP_PROOFS, ROUTES, llms_txt, route_extension, skill_md, x402_manifest
from .rpc import Rpc, UpstreamError, is_address, is_tx_hash
from .services import agentcard as agentcard_svc
from .services import claims as claims_svc
from .services import hosted_inbox as hosted_svc
from .services import counterparty as counterparty_svc
from .services import fetch as fetch_svc
from .services import fleetcheck as fleetcheck_svc
from .services import gradestall as gradestall_svc
from .services import receipts as receipts_svc
from .services import registry as registry_svc
from .services import watchlist as watchlist_svc
from .services import fleetpass as fleetpass_svc
from .services import indexfeed as indexfeed_svc
from .services import indexsub as indexsub_svc
from .services import nudge as nudge_svc
from .services import paymentrail as paymentrail_svc
from .services import orchestrate as orchestrate_svc
from .services import pretrade as pretrade_svc
from .services import probe as probe_svc
from .services import reads as reads_svc
from .services import recheck as recheck_svc
from .services import rotalerts as rotalerts_svc
from .services import watch as watch_svc
from .services import scout as scout_svc
from .services import seller as seller_svc
from .services import verdict as verdict_svc

log = logging.getLogger("stall-row")
logging.basicConfig(level=logging.INFO)

settings = load_settings()  # raises if payout wallet is a placeholder

# --- x402 wiring (same three-way facilitator branch as the siblings) ---------
if settings.use_cdp:
    from .cdp_auth import cdp_facilitator_config

    assert settings.cdp_api_key_id and settings.cdp_api_key_secret
    facilitator = HTTPFacilitatorClient(
        cdp_facilitator_config(settings.cdp_api_key_id, settings.cdp_api_key_secret)
    )
    log.info("facilitator: CDP (Bazaar cataloging path)")
elif settings.use_payai:
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=settings.facilitator_url))
    log.info("facilitator: PayAI (PayAI index cataloging path)")
else:
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=settings.facilitator_url))
    log.info("facilitator: %s (%s)", settings.facilitator_url, settings.network)

resource_server = x402ResourceServer(facilitator)
resource_server.register(settings.network, ExactEvmScheme())

# --- Solana rail (Fleet Check routes only; mirrors Token Verdict) ------------
# Same facilitator: the configured facilitator supports x402 v2 exact on
# solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp alongside eip155:8453, so the one
# facilitator client verifies and settles both networks. The SVM scheme is
# registered on the shared resource server (exactly as Token Verdict does),
# but only the Fleet Check routes in SOLANA_ACCEPT_PATHS carry a Solana
# PaymentOption below — every other route's challenge is unchanged. The
# local pre-verify + replay hooks are network-scoped inside
# app/solana_rail.py: Base payloads pass through untouched, and a Solana
# payment is locally validated (mint / fee payer / destination ATA /
# amount / replay) BEFORE the facilitator verify, and only settles —
# releasing the sweep or the pack — through that same verify → settle
# flow. No Solana payment, no delivery: there is no challenge-only path.
resource_server.register(
    settings.solana_network,
    ExactSvmServerScheme(rpc_url=settings.solana_rpc_url),
)
_svm_replay_guard = SvmReplayGuard()
resource_server.on_before_verify(
    make_before_verify_hook(
        _svm_replay_guard,
        solana_network=settings.solana_network,
        usdc_mint=settings.solana_usdc_mint,
    )
)
resource_server.on_after_settle(
    make_after_settle_hook(_svm_replay_guard, solana_network=settings.solana_network)
)
log.info(
    "solana rail enabled for %s: %s payTo %s",
    sorted(SOLANA_ACCEPT_PATHS),
    settings.solana_network,
    settings.solana_pay_to,
)


def _accepts_for(path: str) -> list[PaymentOption]:
    """Payment rails for one route: Base always (the original accept,
    built exactly as before); Solana too for the Fleet Check routes —
    same USD price, paid in Solana USDC to the Phantom payTo."""
    options = [
        PaymentOption(
            scheme="exact",
            pay_to=settings.pay_to,
            price=settings.prices[path],
            network=settings.network,
        )
    ]
    if path in SOLANA_ACCEPT_PATHS:
        options.append(
            PaymentOption(
                scheme="exact",
                pay_to=settings.solana_pay_to,
                price=settings.prices[path],
                network=settings.solana_network,
            )
        )
    return options


routes = {
    f"POST {path}": RouteConfig(
        accepts=_accepts_for(path),
        description=r["description"],
        mime_type="application/json",
        service_name=settings.service_name,  # ≤32 chars, forwarded to Bazaar
        tags=r["tags"],
        extensions={"bazaar": route_extension(path)},
    )
    for path, r in ROUTES.items()
}

# --- app ---------------------------------------------------------------------
app = FastAPI(title="stall-row", version="1.0.0")


def _openapi_with_ownership_proofs():
    """Default OpenAPI document plus the x402scan ownership-proof root
    keys (x-discovery / x-agentcash-provenance). x402scan reads these to
    verify control of the payTo address — see OWNERSHIP_PROOFS in
    discovery.py; removing them un-verifies the listing."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema["x-discovery"] = {"ownershipProofs": OWNERSHIP_PROOFS}
    schema["x-agentcash-provenance"] = {"ownershipProofs": OWNERSHIP_PROOFS}
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_with_ownership_proofs

# Build the payment middleware ONCE. Constructing it runs the SDK's
# initialize(), which synchronously fetches the facilitator's /supported
# document over the network — building it per request (as this module did
# originally) added a full external round-trip, on the event loop, to
# EVERY request including /health and the unpaid 402 challenges.
_payment_middleware = fastapi_payment_middleware(routes, resource_server)

PACK_HEADER = "x-recheck-pack"


async def _request_pack_id(request: Request) -> str:
    """The pack id a recheck call presents, if any: the X-Recheck-Pack
    header, or the body's pack_id field. Reading the body here is
    safe — Starlette's HTTP middleware replays it to the handler."""
    header = request.headers.get(PACK_HEADER)
    if header and header.strip():
        return header.strip()
    try:
        body = await request.body()
        if body:
            data = json.loads(body)
            if isinstance(data, dict):
                pack_id = data.get("pack_id")
                if isinstance(pack_id, str) and pack_id.strip():
                    return pack_id.strip()
    except Exception:  # noqa: BLE001 — an unreadable body is just "no pack"
        pass
    return ""


PASS_HEADER = fleetpass_svc.PASS_HEADER
_PASS_EXEMPT = {
    "/v1/recheck/pack",
    "/v1/fleet-check/pack",
    "/v1/fleet-pass",
    "/v1/fleet-pass-20",
}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    # A recheck call presenting a pack id is paid from the pack, not
    # per call: skip the paywall and let the handler validate the
    # pack against the store (unknown/wrong/expired/exhausted packs
    # are refused there and deliver nothing).
    if request.method == "POST" and request.url.path == "/v1/recheck":
        if await _request_pack_id(request):
            return await call_next(request)
    # A call presenting a Fleet Pass id is paid from the pass: debit
    # this route's listed price from the ledger BEFORE the handler
    # runs, and refund the debit when the response is a failure —
    # reserve-then-run, never a charge for our failure, and never a
    # silent fallback to a per-call charge.
    pass_id = (request.headers.get(PASS_HEADER) or "").strip()
    if (
        pass_id
        and request.method == "POST"
        and request.url.path in PRICE_UNITS
        and request.url.path not in _PASS_EXEMPT
    ):
        price = fleetpass_svc.price_for("stall-row", request.url.path)
        if price is not None:
            try:
                debit = _recheck_store.debit_pass(
                    pass_id, "stall-row", request.url.path, price
                )
            except recheck_svc.PackError as e:
                return JSONResponse(
                    {"error": e.message, "code": e.code}, status_code=e.http_status
                )
            response = await call_next(request)
            if response.status_code >= 400:
                _recheck_store.refund_debit(debit["debit_id"])
            return response
    return await _payment_middleware(request, call_next)


# Request-body cap (security audit 2026-10-25): every legitimate body in
# this API is a small JSON document; an uncapped body lets a caller
# stream unbounded bytes at the parser. Chunked bodies without a
# Content-Length are the residual gap (terminated at the edge).
_MAX_BODY_BYTES = 1024 * 1024


@app.middleware("http")
async def _body_cap(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > _MAX_BODY_BYTES:
        return JSONResponse({"error": "request body too large"}, status_code=413)
    return await call_next(request)


# CORS for exactly two surfaces, both GitHub Pages: the public
# one-link checker page calls POST /v1/probe cross-origin, and the
# stall claim page calls /v1/claim/* cross-origin. The allowance is
# scoped to those routes + that origin only — the rest of the API
# carries no CORS headers at all. This middleware is registered
# last so it runs outermost for those paths, preflight included.
_PROBE_CORS_ORIGIN = "https://quincygb.github.io"
_CLAIM_CORS_PATHS = (
    "/v1/claim/start",
    "/v1/claim/verify",
    "/v1/claim/status",
    "/v1/claim/inbox",
    "/v1/claim/inbox/config",
)


@app.middleware("http")
async def _probe_cors(request: Request, call_next):
    is_probe = request.url.path == "/v1/probe"
    is_claim = request.url.path in _CLAIM_CORS_PATHS
    if not is_probe and not is_claim:
        return await call_next(request)
    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        if origin == _PROBE_CORS_ORIGIN:
            methods = "POST, OPTIONS" if is_probe else "GET, POST, OPTIONS"
            allow_headers = (
                "Content-Type"
                if is_probe
                else "Content-Type, X-Claim-Session, Authorization"
            )
            return JSONResponse(
                {},
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": _PROBE_CORS_ORIGIN,
                    "Access-Control-Allow-Methods": methods,
                    "Access-Control-Allow-Headers": allow_headers,
                    "Access-Control-Max-Age": "600",
                    "Vary": "Origin",
                },
            )
        return JSONResponse({}, status_code=204)
    response = await call_next(request)
    if origin == _PROBE_CORS_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = _PROBE_CORS_ORIGIN
        response.headers["Vary"] = "Origin"
    return response


def _scrub_upstreams(text: str) -> str:
    """Never echo a configured upstream URL in an error body: an RPC or
    indexer URL can carry an API key in its path, and transport errors
    embed the URL they failed on (security audit 2026-10-25)."""
    for url in (settings.rpc_url, settings.blockscout_base_url):
        if url:
            text = text.replace(url, "[upstream]")
    return text


def _payment_key(request: Request) -> str | None:
    """The replay identity of the verified payment behind this
    request, for idempotent pack minting.

    The middleware stashes the verified payment payload on
    request.state. For the EVM exact scheme that payload carries the
    EIP-3009 transfer authorization, whose nonce is single-use
    on-chain — the strongest identity available to the handler (the
    settlement tx hash only exists AFTER the handler returns, when
    the middleware settles). Fallbacks: a hash of the raw payment
    header (equally unique per signed authorization). None when no
    payment identity is reachable at all."""

    def dig(obj, *names):
        for name in names:
            if obj is None:
                return None
            obj = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        return obj

    payload = getattr(request.state, "payment_payload", None)
    nonce = dig(payload, "payload", "authorization", "nonce")
    if isinstance(nonce, str) and nonce:
        return f"evm3009-nonce:{nonce}"
    payer = dig(payload, "payload", "authorization", "from")
    if isinstance(payer, str) and payer:
        signature = dig(payload, "payload", "signature")
        if isinstance(signature, str) and signature:
            return "evm3009-sig:" + hashlib.sha256(signature.encode()).hexdigest()
    # Solana (SVM) exact payloads carry a partially-signed transaction
    # instead of an EIP-3009 authorization; the client-presented
    # transaction bytes are the payment's identity for a re-presented
    # retry (the replay guard in app/solana_rail.py handles the
    # settled-transaction replay case by message hash).
    transaction = dig(payload, "payload", "transaction")
    if isinstance(transaction, str) and transaction:
        return "svm-tx:" + hashlib.sha256(transaction.encode()).hexdigest()
    for header in ("payment-signature", "x-payment"):
        raw = request.headers.get(header)
        if raw:
            return "payment-header:" + hashlib.sha256(raw.encode()).hexdigest()
    return None


def _clients() -> tuple[httpx.AsyncClient, Rpc, Blockscout]:
    client = httpx.AsyncClient(timeout=settings.fetch_timeout_s, follow_redirects=True)
    return client, Rpc(client, settings.rpc_url), Blockscout(client, settings.blockscout_base_url)


_shared_fetch_client: httpx.AsyncClient | None = None


def _fetch_client() -> httpx.AsyncClient:
    """Process-wide client for the page-to-markdown stall. _clients()
    builds a fresh AsyncClient per request, discarding the connection
    pool, so every page fetch paid a new DNS + TCP + TLS handshake to
    the target host. The shared client reuses connections across
    requests (and across one fetch's redirect/retry hops). Callers
    must NOT close it."""
    global _shared_fetch_client
    if _shared_fetch_client is None or _shared_fetch_client.is_closed:
        _shared_fetch_client = httpx.AsyncClient(
            timeout=settings.fetch_timeout_s, follow_redirects=True
        )
    return _shared_fetch_client


def _public_base(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


async def _run(coro_fn):
    """Run a paid handler body; upstream failures become a 502 JSON
    error (the middleware does not settle on >= 400)."""
    try:
        return await coro_fn()
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except UpstreamError as e:
        return JSONResponse({"error": _scrub_upstreams(str(e))}, status_code=502)
    except Exception:  # noqa: BLE001 — never leak tracebacks
        log.exception("paid handler failed")
        return JSONResponse({"error": "internal failure"}, status_code=502)


# --- request models ------------------------------------------------------------

class AddressRequest(BaseModel):
    address: str = Field(description="Base (EVM) address, 0x…")


class TxRequest(BaseModel):
    tx_hash: str = Field(description="Base transaction hash, 0x… (66 chars)")


class EmptyRequest(BaseModel):
    pass


class TubeSearchRequest(BaseModel):
    query: str = Field(description="YouTube search query")
    max_results: int = Field(default=5, ge=1, le=20)


class PageRequest(BaseModel):
    url: str = Field(description="Public http(s) URL to fetch and convert")


class RepoRequest(BaseModel):
    repo: str = Field(description="'owner/name' or a github.com URL")


class PriceCheckRequest(BaseModel):
    keywords: str = Field(description="Keywords/category describing the listing to price")
    description: str | None = Field(default=None, description="Optional longer description (folded into the keyword match)")


class CardSmithRequest(BaseModel):
    mode: str = Field(description="'generate' or 'grade'")
    name: str | None = None
    description: str | None = None
    url: str | None = None
    version: str | None = None
    provider: str | None = None
    provider_url: str | None = None
    wallet: str | None = None
    skills: Any = None
    endpoints: Any = None
    card: dict | None = None


class JobScoutRequest(BaseModel):
    capabilities: list[str] | None = Field(default=None, description="Capability tags to filter by")
    limit: int | None = Field(default=None, ge=1, le=100)


class RecheckRequest(BaseModel):
    url: str = Field(description="Public http(s) URL to watch: an x402 resource or a web page")
    watch_id: str | None = Field(
        default=None,
        description="Optional watch identifier; defaults to a hash of the URL",
    )
    pack_id: str | None = Field(
        default=None,
        description=(
            "Optional recheck pack id (or send the X-Recheck-Pack header): "
            "spends one pack credit instead of the per-call payment"
        ),
    )


class IndexChangesRequest(BaseModel):
    resource_contains: str | None = Field(
        default=None, description="Only events whose resource URL contains this string"
    )
    pay_to: str | None = Field(
        default=None, description="Only events for resources paid to this address"
    )
    service_name: str | None = Field(
        default=None, description="Only events whose service name contains this string"
    )
    network: str | None = Field(
        default=None,
        description="Restrict the diff to one network (e.g. eip155:8453 or a Solana chain id)",
    )
    limit: int | None = Field(
        default=None, description="Max events to return (default 100, cap 500)"
    )


class PreTradeGuardRequest(BaseModel):
    pay_to: str = Field(description="The payTo address you are about to pay, 0x…")
    amount: int | str | None = Field(
        default=None,
        description="Optional amount you are about to pay, in the asset's smallest units (e.g. 20000 for $0.02 USDC)",
    )
    network: str | None = Field(
        default=None, description="Optional network id (default eip155:8453, Base)"
    )
    resource: str | None = Field(
        default=None,
        description="Optional resource URL of the listing you are about to pay",
    )


class OrchestrateRequest(BaseModel):
    address: str = Field(description="Token contract address for the Token Verdict leg")
    chain: str = Field(default="base", description="Chain for the Token Verdict leg")
    service_url: str = Field(
        description="The service endpoint URL: RouteVerdict checks it, LockSmith audits it"
    )
    listing_url: str = Field(description="The listing/manifest URL ListSmith grades")


class RecheckPackBuyRequest(BaseModel):
    url: str = Field(description="The ONE endpoint URL this pack's credits may check")


class RecheckPackBalanceRequest(BaseModel):
    pack_id: str = Field(description="Pack id returned by POST /v1/recheck/pack")
    url: str | None = Field(
        default=None,
        description="Optional: when given, the pack must be bound to this endpoint",
    )


# --- paid routes ---------------------------------------------------------------

@app.post("/v1/wallet-snapshot")
async def wallet_snapshot(req: AddressRequest):
    if not is_address(req.address):
        return JSONResponse({"error": "address must be a 0x EVM address"}, status_code=422)

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await reads_svc.wallet_snapshot(client, rpc, scout, req.address)

    return await _run(go)


@app.post("/v1/allowance-audit")
async def allowance_audit(req: AddressRequest):
    if not is_address(req.address):
        return JSONResponse({"error": "address must be a 0x EVM address"}, status_code=422)

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await reads_svc.allowance_audit(client, rpc, scout, req.address)

    return await _run(go)


@app.post("/v1/tx-decoder")
async def tx_decoder(req: TxRequest):
    if not is_tx_hash(req.tx_hash):
        return JSONResponse({"error": "tx_hash must be a 0x transaction hash"}, status_code=422)

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await reads_svc.tx_decoder(rpc, scout, req.tx_hash)

    return await _run(go)


@app.post("/v1/gas-oracle")
async def gas_oracle(_req: EmptyRequest | None = None):
    async def go():
        client, rpc, _ = _clients()
        async with client:
            return await reads_svc.gas_oracle(rpc)

    return await _run(go)


@app.post("/v1/wallet-verdict")
async def wallet_verdict(req: AddressRequest):
    if not is_address(req.address):
        return JSONResponse({"error": "address must be a 0x EVM address"}, status_code=422)

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await verdict_svc.wallet_verdict(client, rpc, scout, req.address)

    return await _run(go)


@app.post("/v1/tube-search")
async def tube_search(req: TubeSearchRequest):
    async def go():
        client, _, _ = _clients()
        async with client:
            return await fetch_svc.tube_search(client, req.query.strip(), req.max_results)

    return await _run(go)


@app.post("/v1/page-to-markdown")
async def page_to_markdown(req: PageRequest):
    async def go():
        return await fetch_svc.page_to_markdown(_fetch_client(), req.url.strip())

    return await _run(go)


@app.post("/v1/repo-vitals")
async def repo_vitals(req: RepoRequest):
    async def go():
        client, _, _ = _clients()
        async with client:
            return await fetch_svc.repo_vitals(client, req.repo, settings.github_token)

    return await _run(go)


@app.post("/v1/price-check")
async def price_check(req: PriceCheckRequest):
    keywords = req.keywords + (" " + req.description if req.description else "")

    async def go():
        client, _, _ = _clients()
        async with client:
            return await seller_svc.price_check(client, keywords)

    return await _run(go)


@app.post("/v1/card-smith")
async def card_smith(req: CardSmithRequest):
    payload = req.model_dump(exclude_none=True)

    async def go():
        return seller_svc.card_smith(payload)

    return await _run(go)


@app.post("/v1/job-scout")
async def job_scout(req: JobScoutRequest | None = None):
    req = req or JobScoutRequest()

    async def go():
        return scout_svc.job_scout(req.capabilities, req.limit)

    return await _run(go)


# Recheck watch state + watch-pack balances: one sqlite file whose
# location config.resolve_recheck_db() picked — under a mounted
# volume it survives redeploys; on the service's own disk a redeploy
# wipes it and every watch re-baselines (BASELINE) on its next call.
# Which mode is live is logged here and reported in /health;
# production currently measures persistent, and the route's own
# description states that verified behavior.
_recheck_store = recheck_svc.WatchStore(
    settings.recheck_db_path, persistent=settings.recheck_db_persistent
)
log.info(
    "recheck store durability: %s (path %s)",
    "persistent" if settings.recheck_db_persistent else "EPHEMERAL",
    settings.recheck_db_path,
)


@app.post("/v1/orchestrate")
async def orchestrate(req: OrchestrateRequest):
    """One combined fleet report: Token Verdict on the token,
    RouteVerdict + LockSmith on the service URL, ListSmith on the
    listing URL — via the siblings' internal unpaid paths. Partial
    reports mark failed legs; a total failure 502s unsettled."""

    async def go():
        return await orchestrate_svc.run_orchestrate(
            _fetch_client(),
            address=req.address.strip(),
            chain=(req.chain or "base").strip(),
            service_url=req.service_url.strip(),
            listing_url=req.listing_url.strip(),
        )

    return await _run(go)


# Verdict Index snapshot store: same sqlite file as the recheck
# store (same volume, same durability story), refreshed by a
# background ticker — a full catalog pull is ~80 requests and must
# never run inside a paid call.
_index_store = indexfeed_svc.IndexStore(settings.recheck_db_path)


@app.post("/v1/index/changes")
async def index_changes(req: IndexChangesRequest):
    """Verdict Index: diff of the two newest catalog snapshots.
    Until two snapshots exist there is no honest diff, so the
    service raises UpstreamError and the call 502s unsettled."""

    async def go():
        return indexfeed_svc.changes(
            _index_store,
            resource_contains=req.resource_contains,
            pay_to=req.pay_to,
            service_name=req.service_name,
            network=(req.network or "").strip() or None,
            limit=req.limit or indexfeed_svc.DEFAULT_EVENT_LIMIT,
        )

    return await _run(go)


@app.post("/v1/pre-trade-guard")
async def pre_trade_guard(req: PreTradeGuardRequest):
    """Pre-Trade Guard: screen a payTo BEFORE paying it — Verdict
    Index catalog history (first seen, payTo rotations), the OFAC
    sanctions screen, and the wallet's Base age/activity, combined
    into PROCEED / CAUTION / ABORT. Every leg is a local read or a
    cheap chain read and degrades to "unknown" (capping the verdict
    at CAUTION) rather than failing, so a valid request always
    delivers a verdict — a first-seen payTo included."""
    if not is_address(req.pay_to):
        return JSONResponse({"error": "pay_to must be a 0x EVM address"}, status_code=422)

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await pretrade_svc.pre_trade_guard(
                client,
                rpc,
                scout,
                _index_store,
                pay_to=req.pay_to.strip(),
                amount=req.amount,
                network=(req.network or "").strip() or None,
                resource=(req.resource or "").strip() or None,
            )

    return await _run(go)


class CounterpartyReportRequest(BaseModel):
    pay_to: str = Field(description="The seller's payTo address, 0x…")
    token_address: str | None = Field(
        default=None, description="Optional token contract for the Token Verdict leg"
    )
    chain: str = Field(default="base", description="Chain for the Token Verdict leg")
    service_url: str | None = Field(
        default=None, description="Optional service endpoint URL for the LockSmith audit leg"
    )
    listing_url: str | None = Field(
        default=None, description="Optional listing/manifest URL for the ListSmith leg"
    )
    resource: str | None = Field(
        default=None,
        description="Optional resource URL for the Index history leg (defaults to listing_url)",
    )


@app.post("/v1/counterparty-report")
async def counterparty_report(req: CounterpartyReportRequest):
    """Counterparty Report: everything the fleet can say about one
    seller in one call — wallet snapshot, sanctions screen, and
    Index history locally; Token Verdict / LockSmith / ListSmith
    legs via the fleet-internal paths when the buyer names a token,
    a service URL, or a listing URL. Legs that cannot run are
    marked in the report; only a total failure 502s unsettled."""
    if not is_address(req.pay_to):
        return JSONResponse({"error": "pay_to must be a 0x EVM address"}, status_code=422)
    if req.token_address is not None and not is_address(req.token_address):
        return JSONResponse(
            {"error": "token_address must be a 0x EVM address"}, status_code=422
        )

    async def go():
        client, rpc, scout = _clients()
        async with client:
            return await counterparty_svc.run_counterparty(
                client,
                rpc,
                scout,
                _index_store,
                pay_to=req.pay_to.strip(),
                token_address=(req.token_address or "").strip() or None,
                chain=(req.chain or "base").strip(),
                service_url=(req.service_url or "").strip() or None,
                listing_url=(req.listing_url or "").strip() or None,
                resource=(req.resource or "").strip() or None,
            )

    return await _run(go)


class GradeMyStallRequest(BaseModel):
    resource_url: str = Field(description="The seller's x402 resource URL")
    pay_to: str | None = Field(
        default=None,
        description="Optional: the payTo the seller believes the resource uses",
    )


@app.post("/v1/grade-my-stall")
async def grade_my_stall(req: GradeMyStallRequest):
    """Grade My Stall: a seller-side report card for one resource —
    live 402 probe, description length vs the catalogue limit, CDP
    listing presence in the newest Index snapshot, Settled's record,
    x402scan ownership declaration on the origin, and payTo
    consistency across every source that names one. Checks that
    cannot be performed report "unverified", never a guess."""
    url = (req.resource_url or "").strip()
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
        return JSONResponse(
            {"error": "resource_url must be an http(s) URL"}, status_code=422
        )
    if req.pay_to is not None and not is_address(req.pay_to):
        return JSONResponse(
            {"error": "pay_to must be a 0x EVM address"}, status_code=422
        )

    async def go():
        client, _rpc, _scout = _clients()
        async with client:
            return await gradestall_svc.grade_stall(
                client,
                _index_store,
                resource_url=url,
                pay_to=(req.pay_to or "").strip() or None,
            )

    return await _run(go)


class ReceiptVerifyRequest(BaseModel):
    tx_hash: str = Field(description="Base transaction hash, 0x + 64 hex")


@app.post("/v1/receipt-verify")
async def receipt_verify(req: ReceiptVerifyRequest):
    """Receipt Verifier: a Base tx hash in, a normalized verified
    receipt out — payer, payTo and amount from the transaction's
    USDC Transfer log, settlement status and confirmations from the
    receipt and the chain head, and the fleet routes priced at
    exactly the paid amount listed as candidates (an amount alone
    never identifies a route). Unknown or unconfirmed transactions
    502 unsettled. Base only."""
    if not receipts_svc._TX_HASH_RE.match((req.tx_hash or "").strip()):
        return JSONResponse(
            {"error": "tx_hash must be a 0x-prefixed 64-hex transaction hash"},
            status_code=422,
        )

    async def go():
        client, rpc, _scout = _clients()
        async with client:
            return await receipts_svc.verify_receipt(
                client, rpc, tx_hash=req.tx_hash, fleet_pay_to=settings.pay_to
            )

    return await _run(go)


@app.post("/v1/flagged-paytos")
async def flagged_paytos(_req: EmptyRequest | None = None):
    """Bad-payTo Registry Feed: the currently flagged payTos with
    their evidence — the bundled OFAC SDN snapshot's addresses, plus
    payTos the newest Index snapshot pair shows rotated away from
    live listings or tied to vanished listings. Built from the same
    two sources Pre-Trade Guard screens against. No entry without
    evidence; caps and truncations are stated in the response."""
    async def go():
        return registry_svc.build_feed(_index_store)

    return await _run(go)


class AgentCardVerifyRequest(BaseModel):
    agent_id: int | None = Field(
        default=None, description="ERC-8004 agent id on Base (registry-resolved)"
    )
    agent_url: str | None = Field(
        default=None, description="Direct URL of the agent card JSON"
    )


@app.post("/v1/agent-card-verify")
async def agent_card_verify(req: AgentCardVerifyRequest):
    """Agent-Card Verifier: an ERC-8004 agent id (resolved through
    the Base registry's agentURI/tokenURI) or a direct card URL in;
    the card is fetched and checked against live reality — declared
    endpoints probed unpaid, challenge payTos compared with the
    card's declared wallets, declared prices compared with live
    challenge amounts. Undeclared fields report not_checked; an
    unreachable card 502s unsettled."""
    if req.agent_id is None and not (req.agent_url or "").strip():
        return JSONResponse(
            {"error": "name an agent_id or an agent_url"}, status_code=422
        )
    if req.agent_id is not None and req.agent_id < 0:
        return JSONResponse(
            {"error": "agent_id must be a non-negative integer"}, status_code=422
        )
    url = (req.agent_url or "").strip()
    if url and (
        urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc
    ):
        return JSONResponse(
            {"error": "agent_url must be an http(s) URL"}, status_code=422
        )

    async def go():
        client, rpc, _scout = _clients()
        async with client:
            return await agentcard_svc.verify_agent_card(
                client,
                rpc,
                agent_id=req.agent_id,
                agent_url=url or None,
            )

    return await _run(go)


async def _index_ticker() -> None:
    """Catalog snapshot refresh: once at startup (if none is fresh),
    then whenever the newest snapshot ages past the refresh window.
    A failed pull stores nothing and never stops the ticker."""
    refresh_min_s = float(os.environ.get("STALLROW_INDEX_REFRESH_MIN_S", "21600"))
    bootstrap_min_s = float(
        os.environ.get(
            "STALLROW_INDEX_BOOTSTRAP_MIN_S",
            str(indexfeed_svc.DEFAULT_BOOTSTRAP_INTERVAL_S),
        )
    )
    tick = float(os.environ.get("STALLROW_INDEX_TICK_S", "900"))
    while True:
        try:
            stored = await indexfeed_svc.refresh_if_stale(
                _index_store, _fetch_client(), refresh_min_s, bootstrap_min_s
            )
            if stored:
                log.info(
                    "verdict index: catalog snapshot stored (%d held)",
                    len(_index_store.snapshots()),
                )
        except Exception:  # noqa: BLE001 — a failed pull stores nothing
            log.exception("verdict index refresh failed")
        await asyncio.sleep(tick)


@app.on_event("startup")
async def _start_index_ticker() -> None:
    asyncio.get_event_loop().create_task(_index_ticker())


@app.post("/v1/recheck")
async def recheck(req: RecheckRequest, request: Request):
    pack_id = (req.pack_id or request.headers.get(PACK_HEADER) or "").strip()
    if pack_id:
        try:
            return await recheck_svc.recheck_with_pack(
                _fetch_client(), _recheck_store, req.url, req.watch_id, pack_id
            )
        except recheck_svc.PackError as e:
            return JSONResponse(
                {"error": e.message, "code": e.code, "pack_id": pack_id},
                status_code=e.http_status,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=422)
        except UpstreamError as e:
            return JSONResponse({"error": _scrub_upstreams(str(e))}, status_code=502)
        except Exception:  # noqa: BLE001 — mirror _run's honesty contract
            log.exception("pack recheck failed")
            return JSONResponse({"error": "internal failure"}, status_code=502)

    async def go():
        return await recheck_svc.recheck(
            _fetch_client(), _recheck_store, req.url, req.watch_id
        )

    return await _run(go)


@app.post("/v1/recheck/pack")
async def recheck_pack_buy(req: RecheckPackBuyRequest, request: Request):
    """Mint a watch pack. Runs only after the x402 middleware has
    verified the $1.00 payment; minting is idempotent on the payment's
    identity (see _payment_key), so a re-presented payment returns
    the pack it already bought instead of minting a second one. If
    settlement later fails, the middleware replaces this response
    with its own failure — the buyer never sees an unpaid pack."""
    url = req.url.strip()
    try:
        await asyncio.to_thread(fetch_svc.ssrf_check, url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    payment_key = _payment_key(request)
    if payment_key is None:
        return JSONResponse(
            {"error": "payment identity unavailable; pack cannot be minted safely"},
            status_code=502,
        )
    pack, created = _recheck_store.mint_pack(payment_key, url)
    return {
        **pack,
        "expiry_days": recheck_svc.PACK_TTL_DAYS,
        "price_units": recheck_svc.PACK_PRICE_UNITS,
        "note": (
            "Spend credits with POST /v1/recheck: send this pack_id in "
            "the body or the X-Recheck-Pack header. Read the balance "
            "free at POST /v1/recheck/pack-balance."
            + ("" if created else " This payment already minted this pack; returning it.")
        ),
    }


@app.post("/v1/recheck/pack-balance")
async def recheck_pack_balance(req: RecheckPackBalanceRequest):
    """Free balance read: credits remaining + expiry for a pack.
    Spends nothing. An unknown pack — or a pack bound to a different
    endpoint than the one named — is a plain 404."""
    pack = _recheck_store.get_pack(req.pack_id.strip())
    if pack is None or (req.url is not None and pack["url"] != req.url.strip()):
        return JSONResponse({"error": "unknown pack_id"}, status_code=404)
    return pack


# --- Fleet Pass ---------------------------------------------------------------
# The pass ledger lives in the recheck store. Buy is a paid route
# (minting idempotent on the payment identity, like packs); balance,
# debit and refund are free routes where the pass/debit id is the
# credential — debit is how the SIBLING services spend a buyer's pass
# (the price always comes from fleetpass.FLEET_ROUTES, never from the
# request body beyond naming service + route).

class FleetPassBalanceRequest(BaseModel):
    pass_id: str = Field(description="Pass id returned by POST /v1/fleet-pass")


class FleetPassDebitRequest(BaseModel):
    pass_id: str = Field(description="Pass id presented by the buyer (X-Fleet-Pass)")
    service: str = Field(description="Fleet service name, e.g. token-verdict")
    route: str = Field(description="Fleet route path, e.g. /v1/verdict")


class FleetPassRefundRequest(BaseModel):
    debit_id: str = Field(description="Debit id returned by POST /v1/fleet-pass/debit")


@app.post("/v1/fleet-pass")
async def fleet_pass_buy(request: Request):
    """Mint a Fleet Pass. Runs only after the x402 middleware has
    verified the $5.00 payment; idempotent on the payment identity."""
    payment_key = _payment_key(request)
    if payment_key is None:
        return JSONResponse(
            {"error": "payment identity unavailable; pass cannot be minted safely"},
            status_code=502,
        )
    fleet_pass, created = _recheck_store.mint_pass(
        payment_key, fleetpass_svc.PASS_PRICE_UNITS, fleetpass_svc.PASS_TTL_DAYS
    )
    return {
        **fleet_pass,
        "expiry_days": fleetpass_svc.PASS_TTL_DAYS,
        "price_units": fleetpass_svc.PASS_PRICE_UNITS,
        "note": (
            "Spend with the X-Fleet-Pass header on any fleet route; each "
            "call debits that route's listed price. Read the balance "
            "free at POST /v1/fleet-pass/balance."
            + ("" if created else " This payment already minted this pass; returning it.")
        ),
    }


@app.post("/v1/fleet-pass/balance")
async def fleet_pass_balance(req: FleetPassBalanceRequest):
    """Free balance read: USD balance + expiry + debit count."""
    fleet_pass = _recheck_store.get_pass(req.pass_id.strip())
    if fleet_pass is None:
        return JSONResponse({"error": "unknown pass_id"}, status_code=404)
    fleet_pass["debits"] = _recheck_store.pass_debit_count(req.pass_id.strip())
    return fleet_pass


@app.post("/v1/fleet-pass/debit")
async def fleet_pass_debit(req: FleetPassDebitRequest):
    """Debit one fleet call from a pass. The price is looked up in
    the fleet price table — the request names service + route only."""
    price = fleetpass_svc.price_for(req.service.strip(), req.route.strip())
    if price is None:
        return JSONResponse(
            {"error": "unknown fleet service/route"}, status_code=422
        )
    try:
        return _recheck_store.debit_pass(
            req.pass_id.strip(), req.service.strip(), req.route.strip(), price
        )
    except recheck_svc.PackError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )


@app.post("/v1/fleet-pass/refund")
async def fleet_pass_refund(req: FleetPassRefundRequest):
    """Re-credit a debit after the calling service failed to deliver.
    Idempotent per debit_id."""
    refunded = _recheck_store.refund_debit(req.debit_id.strip())
    return {"debit_id": req.debit_id.strip(), "refunded": refunded}


# --- Webhook Watch --------------------------------------------------------------

class WatchRegisterRequest(BaseModel):
    url: str = Field(description="Public http(s) URL to watch: an x402 resource or a web page")
    webhook_url: str | None = Field(default=None, description="Public http(s) URL that receives change pushes")
    email: str | None = Field(default=None, description="Optional contact email (stored; webhook is the live channel)")
    interval_s: int | None = Field(default=None, ge=300, le=86400, description="Seconds between automatic checks (300–86400)")
    pack_id: str | None = Field(default=None, description="Fund runs with this recheck pack (bound to the watched URL)")
    fleet_pass_id: str | None = Field(default=None, description="Fund runs with this Fleet Pass ($0.005 per run)")


class WatchIdRequest(BaseModel):
    watch_reg_id: str = Field(description="Watch registration id returned by POST /v1/watch/register")


@app.post("/v1/watch/register")
async def watch_register(req: WatchRegisterRequest):
    """Register a webhook watch. Free to register; every run spends
    from the named funding credential. Both URLs are SSRF-checked and
    the credential must actually cover this watch."""
    try:
        return await watch_svc.register(
            _recheck_store,
            req.url,
            req.webhook_url,
            req.email,
            req.interval_s,
            req.pack_id,
            req.fleet_pass_id,
        )
    except watch_svc.WatchError as e:
        return JSONResponse({"error": e.message}, status_code=e.http_status)


@app.post("/v1/watch/status")
async def watch_status(req: WatchIdRequest):
    reg = _recheck_store.get_watch_reg(req.watch_reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown watch_reg_id"}, status_code=404)
    reg["deliveries"] = _recheck_store.deliveries_for(req.watch_reg_id.strip())
    return reg


@app.post("/v1/watch/run")
async def watch_run(req: WatchIdRequest):
    """Run one funded check for a registration right now (the periodic
    ticker runs the same code when a registration comes due)."""
    reg = _recheck_store.get_watch_reg(req.watch_reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown watch_reg_id"}, status_code=404)
    return await watch_svc.run_watch(_fetch_client(), _recheck_store, reg)


async def _run_rotation_alerts() -> None:
    """Evaluate every rotation-alert registration whose watermark is
    behind the newest Index snapshot. Runs from the watch ticker
    (snapshots land ~4x/day, so the due-check is nearly free) and
    costs each evaluated registration one $0.005 Fleet Pass debit —
    the registration's own funding, never a silent free run."""
    snaps = _index_store.snapshots()
    if len(snaps) < 2:
        return
    newest = snaps[-1]["id"]
    for reg in _recheck_store.rotation_regs_to_eval(newest):
        try:
            await rotalerts_svc.evaluate(
                _fetch_client(), _recheck_store, _index_store, reg
            )
        except Exception:  # noqa: BLE001 — one alert must not kill the loop
            log.exception("rotation evaluation failed for %s", reg["reg_id"])
    for reg in _recheck_store.watchlist_regs_to_eval(newest):
        try:
            await watchlist_svc.evaluate(
                _fetch_client(), _recheck_store, _index_store, reg
            )
        except Exception:  # noqa: BLE001 — one watchlist must not kill the loop
            log.exception("watchlist evaluation failed for %s", reg["reg_id"])
    for reg in _recheck_store.index_subs_to_eval(newest):
        try:
            await indexsub_svc.evaluate(
                _fetch_client(), _recheck_store, _index_store, reg
            )
        except Exception:  # noqa: BLE001 — one subscription must not kill the loop
            log.exception("index subscription evaluation failed for %s", reg["reg_id"])


async def _run_fleet_check_packs() -> None:
    """Run every Fleet Check pack whose interval has come due (the
    same reserve-then-run sweep POST /v1/fleet-check/run performs).
    An unfundable pack is never due, so a sweep here always has its
    credit; a PackError can only be a race with expiry — logged and
    skipped, never retried in a loop."""
    for pack in _recheck_store.due_fleet_check_packs():
        try:
            await fleetcheck_svc.run_pack_sweep(
                _fetch_client(), _recheck_store, pack
            )
        except recheck_svc.PackError as e:
            log.info(
                "fleet check sweep refused for %s: %s", pack["pack_id"], e.code
            )
        except Exception:  # noqa: BLE001 — one pack must not kill the loop
            log.exception("fleet check sweep failed for %s", pack["pack_id"])


async def _watch_ticker() -> None:
    """Periodic funded checks for due registrations. Sequential by
    design; a failing watch never stops the ticker."""
    tick = float(os.environ.get("STALLROW_WATCH_TICK_S", "300"))
    while True:
        await asyncio.sleep(tick)
        try:
            for reg in _recheck_store.due_watch_regs():
                try:
                    await watch_svc.run_watch(
                        _fetch_client(), _recheck_store, reg
                    )
                except Exception:  # noqa: BLE001 — one watch must not kill the loop
                    log.exception("watch run failed for %s", reg["watch_reg_id"])
        except Exception:  # noqa: BLE001
            log.exception("watch ticker pass failed")
        try:
            await _run_fleet_check_packs()
        except Exception:  # noqa: BLE001
            log.exception("fleet check pack pass failed")
        try:
            await _run_rotation_alerts()
        except Exception:  # noqa: BLE001
            log.exception("rotation alert pass failed")


@app.on_event("startup")
async def _start_watch_ticker() -> None:
    asyncio.get_event_loop().create_task(_watch_ticker())


# --- Rotation Alerts ------------------------------------------------------------
# The push form of the Verdict Index: free to register, funded per
# evaluation from a Fleet Pass ($0.005 per comparison run — the
# Webhook Watch run price), evaluated once per new catalog snapshot
# by the watch ticker above (and on demand via /run).

class RotationRegisterRequest(BaseModel):
    pay_to: str | None = Field(default=None, description="Watch every listing paying this 0x address")
    resource: str | None = Field(default=None, description="Watch exactly this one resource URL")
    webhook_url: str | None = Field(default=None, description="Public http(s) URL that receives alert pushes")
    email: str | None = Field(default=None, description="Optional contact email (stored; webhook is the live channel)")
    fleet_pass_id: str = Field(description="Fleet Pass funding each evaluation ($0.005 per run)")


class RotationIdRequest(BaseModel):
    reg_id: str = Field(description="Registration id returned by POST /v1/rotation-alerts/register")


@app.post("/v1/rotation-alerts/register")
async def rotation_register(req: RotationRegisterRequest):
    """Register a rotation alert. Free to register; each evaluation
    spends $0.005 from the named Fleet Pass. The target (payTo and/or
    resource) and the webhook are validated before anything is
    stored."""
    try:
        return await rotalerts_svc.register(
            _recheck_store,
            req.pay_to,
            req.resource,
            req.webhook_url,
            req.email,
            req.fleet_pass_id,
        )
    except rotalerts_svc.RotationError as e:
        return JSONResponse({"error": e.message}, status_code=e.http_status)


@app.post("/v1/rotation-alerts/status")
async def rotation_status(req: RotationIdRequest):
    reg = _recheck_store.get_rotation_reg(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    reg["deliveries"] = _recheck_store.deliveries_for(req.reg_id.strip())
    return reg


@app.post("/v1/rotation-alerts/run")
async def rotation_run(req: RotationIdRequest):
    """Evaluate one registration against the newest snapshot pair
    right now (the watch ticker runs the same code when a new
    snapshot lands). A registration already at the newest snapshot
    answers no_new_snapshot and charges nothing."""
    reg = _recheck_store.get_rotation_reg(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    return await rotalerts_svc.evaluate(
        _fetch_client(), _recheck_store, _index_store, reg
    )


# --- Router Watchlist -------------------------------------------------------------
# The top-N catalog (default 100) by 30d calls, diffed per snapshot
# and pushed like a recheck pack's drift — but built on the watch
# store, because the pack machinery binds one pack to ONE endpoint
# and a watchlist is the whole catalog's head. Free to register;
# $0.005 per evaluation from a Fleet Pass, first evaluation a free
# silent baseline.

class WatchlistRegisterRequest(BaseModel):
    top_n: int | None = Field(default=None, description="Watchlist size by 30d calls (default 100, max 500)")
    webhook_url: str | None = Field(default=None, description="Public http(s) URL that receives diff pushes")
    email: str | None = Field(default=None, description="Optional contact email (stored; webhook is the live channel)")
    fleet_pass_id: str = Field(description="Fleet Pass funding each evaluation ($0.005 per run)")


class WatchlistIdRequest(BaseModel):
    reg_id: str = Field(description="Registration id returned by POST /v1/watchlist/register")


@app.post("/v1/watchlist/register")
async def watchlist_register(req: WatchlistRegisterRequest):
    """Register a router watchlist. Free to register; each
    evaluation spends $0.005 from the named Fleet Pass."""
    try:
        return await watchlist_svc.register(
            _recheck_store,
            req.top_n,
            req.webhook_url,
            req.email,
            req.fleet_pass_id,
        )
    except watchlist_svc.WatchlistError as e:
        return JSONResponse({"error": e.message}, status_code=e.http_status)


@app.post("/v1/watchlist/status")
async def watchlist_status(req: WatchlistIdRequest):
    reg = _recheck_store.get_watchlist_reg(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    reg["deliveries"] = _recheck_store.deliveries_for(req.reg_id.strip())
    return reg


@app.post("/v1/watchlist/run")
async def watchlist_run(req: WatchlistIdRequest):
    """Evaluate one watchlist registration against the newest
    snapshot pair right now. A registration already at the newest
    snapshot answers no_new_snapshot and charges nothing."""
    reg = _recheck_store.get_watchlist_reg(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    return await watchlist_svc.evaluate(
        _fetch_client(), _recheck_store, _index_store, reg
    )


# --- Index subscriptions ---------------------------------------------------------
# The standing form of POST /v1/index/changes: free to register,
# funded per delivered evaluation from a Fleet Pass at the paid
# route's own $0.10 price, evaluated once per new catalog snapshot
# by the watch ticker above (and on demand via /run).

class IndexSubRegisterRequest(BaseModel):
    resource_contains: str | None = Field(default=None, description="Only resources whose URL contains this string")
    pay_to: str | None = Field(default=None, description="Only resources paying this 0x address")
    service_name: str | None = Field(default=None, description="Only resources whose service name contains this string")
    network: str | None = Field(default=None, description="Only this network (e.g. eip155:8453)")
    webhook_url: str | None = Field(default=None, description="Public http(s) URL that receives diff pushes")
    email: str | None = Field(default=None, description="Optional contact email (stored; webhook is the live channel)")
    fleet_pass_id: str = Field(description="Fleet Pass funding each evaluation ($0.10 per delivered diff)")


class IndexSubIdRequest(BaseModel):
    reg_id: str = Field(description="Registration id returned by POST /v1/index/subscribe")


@app.post("/v1/index/subscribe")
async def index_subscribe(req: IndexSubRegisterRequest):
    """Register an Index subscription. Free to register; each
    delivered evaluation spends $0.10 from the named Fleet Pass —
    the listed price of one POST /v1/index/changes call."""
    try:
        return await indexsub_svc.register(
            _recheck_store,
            req.resource_contains,
            req.pay_to,
            req.service_name,
            req.network,
            req.webhook_url,
            req.email,
            req.fleet_pass_id,
        )
    except indexsub_svc.IndexSubError as e:
        return JSONResponse({"error": e.message}, status_code=e.http_status)


@app.post("/v1/index/subscription/status")
async def index_subscription_status(req: IndexSubIdRequest):
    reg = _recheck_store.get_index_sub(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    reg["deliveries"] = _recheck_store.deliveries_for(req.reg_id.strip())
    return reg


@app.post("/v1/index/subscription/run")
async def index_subscription_run(req: IndexSubIdRequest):
    """Evaluate one subscription against the newest snapshot pair
    right now. A registration already at the newest snapshot answers
    no_new_snapshot and charges nothing."""
    reg = _recheck_store.get_index_sub(req.reg_id.strip())
    if reg is None:
        return JSONResponse({"error": "unknown reg_id"}, status_code=404)
    return await indexsub_svc.evaluate(
        _fetch_client(), _recheck_store, _index_store, reg
    )


# --- Fleet Pass v2 -----------------------------------------------------------------
# The $20 working pass for agent frameworks: same ledger, same
# 90-day TTL, same debit-at-listed-prices rule as the $5 pass — a
# bigger prepaid denomination, nothing else changes. Minting is
# idempotent on the payment identity, like the $5 pass.

@app.post("/v1/fleet-pass-20")
async def fleet_pass_20_buy(request: Request):
    """Mint a $20 Fleet Pass. Runs only after the x402 middleware
    has verified the $20.00 payment; idempotent on payment identity."""
    payment_key = _payment_key(request)
    if payment_key is None:
        return JSONResponse(
            {"error": "payment identity unavailable; pass cannot be minted safely"},
            status_code=502,
        )
    fleet_pass, created = _recheck_store.mint_pass(
        payment_key,
        fleetpass_svc.PASS_V2_PRICE_UNITS,
        fleetpass_svc.PASS_TTL_DAYS,
    )
    return {
        **fleet_pass,
        "expiry_days": fleetpass_svc.PASS_TTL_DAYS,
        "price_units": fleetpass_svc.PASS_V2_PRICE_UNITS,
        "note": (
            "The $20 Fleet Pass: a prepaid balance for agent "
            "frameworks, spent with the X-Fleet-Pass header on any "
            "fleet route; each call debits that route's listed "
            "price. There are no holder discounts — passes debit at "
            "listed prices, exactly like the $5 pass. Read the "
            "balance free at POST /v1/fleet-pass/balance."
            + ("" if created else " This payment already minted this pass; returning it.")
        ),
    }


# --- Fleet Check ------------------------------------------------------------------
# Whole-fleet health sweeps for stall owners: the one-shot is a paid
# route; the pack is the standing form (paid mint, free run/status,
# pack id as the credential) mirroring the recheck pack. Sweeps probe
# the buyer's routes UNPAID — the checker never pays a route it
# checks. Automatic sweeps ride the watch ticker below.

class FleetCheckRequest(BaseModel):
    resources: list[str] | None = Field(
        default=None,
        description="Resource URLs to probe (max 40 across the whole sweep)",
    )
    origins: list[str] | None = Field(
        default=None,
        description="Origins whose /.well-known/x402 priced resources join the sweep (max 10)",
    )


class FleetCheckPackBuyRequest(BaseModel):
    resources: list[str] | None = Field(
        default=None,
        description="Resource URLs in this pack's FIXED fleet definition (max 40)",
    )
    origins: list[str] | None = Field(
        default=None,
        description="Origins in this pack's FIXED fleet definition (max 10)",
    )
    webhook_url: str | None = Field(
        default=None,
        description="Public http(s) URL that receives new-failure / recovery pushes",
    )
    email: str | None = Field(
        default=None,
        description="Optional contact email (stored; webhook is the live channel)",
    )
    heartbeat: bool = Field(
        default=False,
        description="Also POST a heartbeat to the webhook on sweeps with no changes",
    )
    interval_s: int | None = Field(
        default=None, ge=300, le=86400,
        description="Seconds between automatic sweeps (300–86400, default 3600)",
    )


class FleetCheckPackIdRequest(BaseModel):
    pack_id: str = Field(description="Pack id returned by POST /v1/fleet-check/pack")


@app.post("/v1/fleet-check")
async def fleet_check(req: FleetCheckRequest):
    """One paid sweep of the buyer's fleet. Invalid definitions
    (empty, oversized, non-public targets) are refused 422 before
    anything is probed — and a refusal never settles. A sweep whose
    table is full of DOWN rows still delivered: the table is the
    product."""

    async def go():
        definition = await fleetcheck_svc.validate_definition(
            req.resources, req.origins
        )
        return await fleetcheck_svc.sweep(_fetch_client(), definition)

    return await _run(go)


@app.post("/v1/fleet-check/pack")
async def fleet_check_pack_buy(
    req: FleetCheckPackBuyRequest, request: Request
):
    """Mint a Fleet Check pack. Runs only after the x402 middleware
    has verified the $5.00 payment; minting is idempotent on the
    payment's identity, like every prepaid product on the row. The
    fleet definition is validated (SSRF included) BEFORE minting —
    a refused definition mints nothing."""
    try:
        definition = await fleetcheck_svc.validate_definition(
            req.resources, req.origins, req.webhook_url
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    payment_key = _payment_key(request)
    if payment_key is None:
        return JSONResponse(
            {"error": "payment identity unavailable; pack cannot be minted safely"},
            status_code=502,
        )
    pack, created = _recheck_store.mint_fleet_check_pack(
        payment_key,
        definition,
        req.webhook_url.strip() if req.webhook_url else None,
        req.email.strip() if req.email else None,
        bool(req.heartbeat),
        req.interval_s or fleetcheck_svc.DEFAULT_INTERVAL_S,
    )
    return {
        **pack,
        "expiry_days": fleetcheck_svc.PACK_TTL_DAYS,
        "price_units": fleetcheck_svc.PACK_PRICE_UNITS,
        "note": (
            "Sweeps of this fixed fleet definition run automatically "
            "on the pack interval and on demand via POST "
            "/v1/fleet-check/run — one credit per sweep, never per "
            "route. Read the latest table free at POST "
            "/v1/fleet-check/status."
            + ("" if created else " This payment already minted this pack; returning it.")
        ),
    }


@app.post("/v1/fleet-check/run")
async def fleet_check_run(req: FleetCheckPackIdRequest):
    """Run one sweep for a pack right now, spending one sweep
    credit (the watch ticker runs the same code when a pack comes
    due). Funding refusals are the pack refusal matrix: unknown
    404, expired 410, exhausted 402."""
    pack = _recheck_store.get_fleet_check_pack(req.pack_id.strip())
    if pack is None:
        return JSONResponse({"error": "unknown pack_id"}, status_code=404)
    try:
        return await fleetcheck_svc.run_pack_sweep(
            _fetch_client(), _recheck_store, pack
        )
    except recheck_svc.PackError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code, "pack_id": pack["pack_id"]},
            status_code=e.http_status,
        )


@app.post("/v1/fleet-check/status")
async def fleet_check_status(req: FleetCheckPackIdRequest):
    """Free read: the pack (definition, credits, expiry) plus its
    latest sweep table, that sweep's diff, and any webhook delivery
    record. Spends nothing."""
    pack = _recheck_store.get_fleet_check_pack(req.pack_id.strip())
    if pack is None:
        return JSONResponse({"error": "unknown pack_id"}, status_code=404)
    pack["latest_run"] = _recheck_store.latest_fleet_check_run(
        req.pack_id.strip()
    )
    pack["deliveries"] = _recheck_store.deliveries_for(req.pack_id.strip())
    return pack


# --- One-link probe (free) -------------------------------------------------------
# The public checker page's backend (services/probe.py): ONE route
# URL or origin in, Fleet Check's own classification out. Free and
# absent from PRICE_UNITS / discovery — the priced count does not
# move. Abuse brakes: the per-IP rate limiter in probe.py, the SSRF
# guard inside definition validation, and the probe timeout.

class ProbeRequest(BaseModel):
    url: str = Field(description="One x402 route URL, or one stall origin to expand from its /.well-known/x402")


@app.post("/v1/probe")
async def probe(req: ProbeRequest, request: Request):
    """Probe one route (or origin) unpaid and classify it with
    Fleet Check's machinery. Refused targets (non-http(s),
    private/loopback) are a 422 before anything is probed; a probe
    that cannot run at all on our side is a 502, never dressed up
    as a verdict on the target."""
    client_ip = request.client.host if request.client else "unknown"
    if not probe_svc.RATE_LIMITER.allow(
        client_ip, probe_svc.rate_limit_per_min()
    ):
        return JSONResponse(
            {"error": "rate limit: at most 10 probes per minute from one address"},
            status_code=429,
        )
    url = (req.url or "").strip()
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=422)
    try:
        return await probe_svc.probe_one(_fetch_client(), url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception:  # noqa: BLE001 — our failure, stated as ours
        log.exception("probe failed to run for %s", url)
        return JSONResponse(
            {"error": "probe failed to run — this says nothing about the target"},
            status_code=502,
        )


# --- Stall claim flow (free) ------------------------------------------------------
# An operator proves control of a stall origin — EIP-191 signature
# by the payTo its own discovery doc publishes, or a token file
# under its /.well-known/ — and only then reads that origin's
# patrol defect history (services/claims.py). Free and absent from
# PRICE_UNITS / discovery — the priced route count does not move.
# Abuse brakes: the per-IP rate limiter in claims.py, and the SSRF
# discipline on every fetch verify makes of the claimed origin.

class ClaimStartRequest(BaseModel):
    origin: str = Field(description="The stall origin to claim, e.g. https://stall.example.com")


class ClaimVerifyRequest(BaseModel):
    origin: str = Field(description="The stall origin named at claim start")
    method: str = Field(description="'sign-message' or 'file'")
    signature: str | None = Field(
        default=None,
        description="EIP-191 signature over the challenge message (sign-message method only)",
    )


def _claim_rate_limited(request: Request) -> JSONResponse | None:
    client_ip = request.client.host if request.client else "unknown"
    if not claims_svc.RATE_LIMITER.allow(
        f"{request.url.path}:{client_ip}", claims_svc.rate_limit_per_min()
    ):
        return JSONResponse(
            {"error": "rate limit: too many claim attempts from one address"},
            status_code=429,
        )
    return None


@app.post("/v1/claim/start")
async def claim_start(req: ClaimStartRequest, request: Request):
    """Issue a claim challenge for one origin: a single-use token
    (≤1h) with both proof options — the exact EIP-191 message to
    sign with the origin's published payTo wallet, and the
    /.well-known/claim-<token> file to serve."""
    limited = _claim_rate_limited(request)
    if limited is not None:
        return limited
    try:
        return claims_svc.start_claim(_recheck_store, req.origin)
    except claims_svc.ClaimError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )


def _session_token_from(request: Request) -> str:
    """The claim session token, from the X-Claim-Session header, an
    Authorization: Bearer header, or the session_token query
    parameter — the three carriers the claim page uses."""
    token = (request.headers.get("x-claim-session") or "").strip()
    if not token:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        token = (request.query_params.get("session_token") or "").strip()
    return token


@app.post("/v1/claim/verify")
async def claim_verify(req: ClaimVerifyRequest, request: Request):
    """Verify one proof against the origin's active challenge. On
    success the challenge is consumed, the origin is marked claimed
    in the WatchStore, and a session token bound to that origin is
    returned. Every failure is a clean 4xx and consumes nothing.
    A successful claim also mints the origin's hosted inbox (see
    /v1/hosted-inbox below) and returns its kit block."""
    limited = _claim_rate_limited(request)
    if limited is not None:
        return limited
    try:
        result = await claims_svc.verify_claim(
            _fetch_client(),
            _recheck_store,
            req.origin,
            req.method,
            req.signature,
        )
    except claims_svc.ClaimError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )
    result["hosted_inbox"] = hosted_svc.inbox_block(
        _recheck_store, result["origin"], _public_base(request)
    )
    return result


@app.get("/v1/claim/status")
async def claim_status(request: Request, origin: str = ""):
    """One origin's patrol defect history + Managed Loop enrollment
    offer. Answers ONLY to a claim session token issued for the
    origin named in the query (X-Claim-Session header, an
    Authorization: Bearer header, or the session_token query
    parameter): no session 401, unknown/expired session 401, a
    session for a different origin 403 — and nothing about the
    origin is disclosed on any refusal path."""
    try:
        status = claims_svc.claim_status(
            _recheck_store, origin, _session_token_from(request)
        )
    except claims_svc.ClaimError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )
    status["hosted_inbox"] = hosted_svc.inbox_block(
        _recheck_store, status["origin"], _public_base(request)
    )
    return status


# --- Hosted inboxes (free) ----------------------------------------------------------
# The mailbox relay for claimed origins (services/hosted_inbox.py,
# spec §8): POST /v1/hosted-inbox/<origin-key> accepts spec-valid
# signed knocks for a CLAIMED origin with exactly the fleet inbox's
# discipline (malformed 400, forged 403, unclaimed 404); the owner
# reads the mail and configures webhook/email relays through the
# claim session. Free and absent from PRICE_UNITS / discovery.

class HostedInboxConfigRequest(BaseModel):
    origin: str = Field(description="The claimed origin whose mailbox to configure")
    webhook_url: str | None = Field(default=None, description="Webhook target (public https) or null to clear")
    webhook_enabled: bool | None = Field(default=None, description="Enable/disable webhook relay")
    email: str | None = Field(default=None, description="Relay email address or null to clear")
    email_enabled: bool | None = Field(default=None, description="Enable/disable email relay (relay itself is deployment-gated)")


async def _run_hosted_deliveries(origin: str) -> None:
    """Background relay pass after a knock is stored. Delivery
    outcomes land on the delivery rows; a relay fault is recorded
    there and never fails the knock that triggered it."""
    try:
        await hosted_svc.process_deliveries(
            _fetch_client(), _recheck_store, origin
        )
    except Exception as exc:  # noqa: BLE001 - background relay, rows carry the evidence
        print(
            f"hosted-inbox delivery pass for {origin} raised: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


@app.post("/v1/hosted-inbox/{origin_key}")
async def hosted_inbox_receive(
    origin_key: str, request: Request, background: BackgroundTasks
):
    """Receive one knock at a claimed origin's hosted address. The
    knock's stall must be the origin the address was minted for;
    opt-outs signed by the origin's published payTo bind here
    exactly as they do at a self-hosted inbox."""
    try:
        raw = await request.body()
        message = json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(
            {"ok": False, "error": "body_not_json",
             "detail": "the knock must be a JSON object"},
            status_code=400,
        )
    try:
        result = await hosted_svc.receive_knock(
            _fetch_client(), _recheck_store, origin_key, message
        )
    except hosted_svc.HostedError as e:
        return JSONResponse(e.body(), status_code=e.http_status)
    if result.get("stored"):
        background.add_task(_run_hosted_deliveries, result["stall"])
    return result


@app.get("/v1/claim/inbox")
async def claim_inbox(request: Request, origin: str = ""):
    """The owner's mailbox read: hosted-inbox kit block, stored
    knocks, and the relay delivery log — behind the same claim
    session gate as /v1/claim/status."""
    try:
        return hosted_svc.owner_inbox(
            _recheck_store,
            origin,
            _session_token_from(request),
            _public_base(request),
        )
    except claims_svc.ClaimError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )
    except hosted_svc.HostedError as e:
        return JSONResponse(e.body(), status_code=e.http_status)


@app.post("/v1/claim/inbox/config")
async def claim_inbox_config(req: HostedInboxConfigRequest, request: Request):
    """Configure a claimed origin's mailbox relays (webhook URL /
    email address) under its claim session. Only fields the caller
    actually sent are applied; an explicit null clears that field."""
    body = {
        name: getattr(req, name)
        for name in req.model_fields_set
        if name != "origin"
    }
    try:
        result = await hosted_svc.update_config(
            _recheck_store,
            req.origin,
            _session_token_from(request),
            body,
        )
    except claims_svc.ClaimError as e:
        return JSONResponse(
            {"error": e.message, "code": e.code}, status_code=e.http_status
        )
    except hosted_svc.HostedError as e:
        return JSONResponse(e.body(), status_code=e.http_status)
    result["hosted_inbox"] = hosted_svc.inbox_block(
        _recheck_store, result["origin"], _public_base(request)
    )
    return result


@app.post("/v1/internal/claims-history")
async def internal_claims_history(request: Request):
    """Fleet-internal upload of the claims history snapshot (the
    patrol census document the claim status read serves when no
    CLAIM_HISTORY_PATH file is configured on this deployment).
    Secret-gated exactly like /v1/internal/nudges: no secret
    configured on the service, no endpoint (404); wrong secret,
    403. The document is stored verbatim and replaces the last."""
    secret = os.environ.get("FLEET_INTERNAL_SECRET", "")
    if not secret:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    provided = request.headers.get("x-fleet-internal-secret", "")
    if not hmac.compare_digest(provided, secret):
        return JSONResponse(
            {"detail": "fleet internal secret required"}, status_code=403
        )
    try:
        raw = await request.body()
        doc = json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(
            {"detail": "body must be JSON"}, status_code=400
        )
    if not isinstance(doc, dict) or not any(
        key in doc for key in ("origins", "open_defects", "entries")
    ):
        return JSONResponse(
            {
                "detail": "document must carry origins, open_defects "
                "or entries"
            },
            status_code=400,
        )
    meta = _recheck_store.save_claims_history_snapshot(doc)
    origins: set[str] = set()
    rows = 0
    if isinstance(doc.get("origins"), dict):
        for origin, entry in doc["origins"].items():
            origins.add(str(origin))
            if isinstance(entry, dict):
                rows += len(entry.get("defects") or [])
    if isinstance(doc.get("open_defects"), dict):
        for key, defect in doc["open_defects"].items():
            origins.add(str(key).split("|", 1)[0])
            if isinstance(defect, dict):
                rows += 1
    if isinstance(doc.get("entries"), list):
        for entry in doc["entries"]:
            if isinstance(entry, dict):
                for origin in entry.get("origins") or []:
                    origins.add(str(origin))
                rows += len(entry.get("defects") or [])
    return {
        "ok": True,
        **meta,
        "origins": len(origins),
        "defect_rows": rows,
    }


# --- Human payment rail (internal mint) -------------------------------------------
# A buyer who cannot pay via x402 sends exactly $5.00 USDC on Base
# directly to the payTo wallet; the payment-rail watcher
# (fleet-checker/payment_rail.py) detects the transfer and calls
# this endpoint. Fleet-internal secret gate, mirroring
# /v1/internal/nudges exactly: secret unset = 404, wrong = 403.
# The endpoint verifies the payment ON-CHAIN (receipt + USDC
# Transfer log: to payTo, from buyer_wallet, exactly $5.00) before
# minting, and a tx hash may mint exactly once, ever — consumed
# hashes persist in the WatchStore beside the packs.

class HumanRailMintRequest(BaseModel):
    buyer_wallet: str = Field(description="Wallet that sent the $5.00 USDC payment, 0x…")
    tx_hash: str = Field(description="Base transaction hash of the payment, 0x… (66 chars)")
    definition: dict | None = Field(
        default=None,
        description=(
            "Optional fleet definition {resources, origins} for the pack; "
            "defaults to an empty definition the buyer configures later"
        ),
    )


@app.post("/v1/internal/fleet-check/pack/mint")
async def internal_fleet_check_pack_mint(
    req: HumanRailMintRequest, request: Request
):
    secret = os.environ.get("FLEET_INTERNAL_SECRET", "")
    if not secret:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    presented = request.headers.get("x-fleet-internal-secret", "")
    if not hmac.compare_digest(presented, secret):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    buyer = (req.buyer_wallet or "").strip()
    tx_hash = (req.tx_hash or "").strip()
    if not is_address(buyer):
        return JSONResponse(
            {"error": "buyer_wallet must be a 0x EVM address"}, status_code=422
        )
    if not is_tx_hash(tx_hash):
        return JSONResponse(
            {"error": "tx_hash must be a 0x transaction hash"}, status_code=422
        )
    if _recheck_store.is_tx_consumed(tx_hash):
        return JSONResponse(
            {"error": "this transaction already minted a pack", "code": "tx_consumed"},
            status_code=409,
        )
    # Definition: default empty (buyer configures origins later);
    # when one is supplied it must be a {resources, origins} object
    # of string lists — stored verbatim, capped like a normal pack.
    definition: dict = {"resources": [], "origins": []}
    if req.definition is not None:
        if not isinstance(req.definition, dict):
            return JSONResponse(
                {"error": "definition must be an object"}, status_code=422
            )
        resources = req.definition.get("resources") or []
        origins = req.definition.get("origins") or []
        if not all(
            isinstance(v, list) and all(isinstance(x, str) for x in v)
            for v in (resources, origins)
        ):
            return JSONResponse(
                {"error": "definition resources/origins must be string lists"},
                status_code=422,
            )
        if len(resources) > fleetcheck_svc.MAX_RESOURCES or len(origins) > fleetcheck_svc.MAX_ORIGINS:
            return JSONResponse(
                {"error": "definition exceeds Fleet Check pack limits"},
                status_code=422,
            )
        definition = {"resources": list(resources), "origins": list(origins)}
    client, rpc, _scout = _clients()
    try:
        async with client:
            await paymentrail_svc.verify_usdc_payment(
                rpc,
                tx_hash=tx_hash,
                buyer_wallet=buyer,
                pay_to=settings.pay_to,
            )
    except paymentrail_svc.PaymentRailError as e:
        return JSONResponse(
            {"error": str(e), "code": e.code}, status_code=e.http_status
        )
    except UpstreamError as e:
        return JSONResponse(
            {"error": _scrub_upstreams(str(e))}, status_code=502
        )
    pack, created = _recheck_store.mint_fleet_check_pack(
        f"human-rail:{tx_hash.lower()}",
        definition,
        None,
        None,
        False,
        fleetcheck_svc.DEFAULT_INTERVAL_S,
    )
    recorded = _recheck_store.record_consumed_tx(tx_hash, pack["pack_id"], buyer)
    if not recorded:
        # Lost a race with a concurrent mint of the same tx: the
        # pack above is the idempotent replay of that same payment
        # key, so returning it is correct — never a second pack.
        return {"pack_id": pack["pack_id"], "created": False}
    return {
        "pack_id": pack["pack_id"],
        "created": created,
        "credits_total": pack["credits_total"],
        "credits_remaining": pack["credits_remaining"],
        "expires_at": pack["expires_at"],
        "definition": pack["definition"],
    }


# --- Nudge inbox ------------------------------------------------------------------
# The two-way leg of Fleet Check (app/services/nudge.py; spec:
# x402-loop-kits/nudge-inbox.md). POST /v1/nudge is FREE — inbound
# mail is not a product, and it is absent from PRICE_UNITS and every
# paid surface, so the priced route count does not move. Every
# message is EIP-191-signed; unsigned or wrongly-signed mail is a
# clean 4xx, never a 5xx. The owner reads the inbox through the
# fleet-internal gate, same discipline as the siblings' internal
# routes: secret unset = 404, wrong secret = 403.

class NudgeInboxReadRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


async def _stall_pay_to(stall: str) -> str | None:
    """The payTo a stall's own discovery doc publishes — the
    opt-out verifier's ground truth for who controls that stall.
    Fetched under the recheck prober's SSRF discipline."""
    try:
        status, _headers, body = await recheck_svc._get_once(
            _fetch_client(), f"{stall.rstrip('/')}/.well-known/x402", "GET"
        )
    except Exception:  # noqa: BLE001 — an unreadable doc proves nothing
        return None
    if status != 200 or not body:
        return None
    try:
        doc = json.loads(body)
    except ValueError:
        return None
    pay_to = doc.get("payTo") if isinstance(doc, dict) else None
    return pay_to if isinstance(pay_to, str) else None


@app.post("/v1/nudge")
async def nudge_inbox(request: Request):
    """Receive one fleet-health nudge (or opt-out). The message is
    validated structurally, then its signature must recover to the
    claimed sender wallet, then — for nudges — the per-sender rate
    limit applies. Verified nudges are stored deduped; opt-outs
    must be signed by the payTo the named stall's own discovery
    doc publishes, and are recorded for the sender engine."""
    try:
        raw = await request.body()
        message = json.loads(raw) if raw else None
    except ValueError:
        return JSONResponse(
            {"error": "body must be a JSON object"}, status_code=400
        )
    try:
        nudge_svc.validate_message(message)
        nudge_svc.verify_sender(message)
    except nudge_svc.NudgeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.http_status)
    if message["kind"] == nudge_svc.KIND_OPT_OUT:
        pay_to = await _stall_pay_to(message["stall"])
        if pay_to is None:
            return JSONResponse(
                {
                    "error": "could not read the stall's discovery "
                    "doc to verify payTo control"
                },
                status_code=422,
            )
        if pay_to.lower() != message["sender"].lower():
            return JSONResponse(
                {
                    "error": "opt-out must be signed by the stall's "
                    "published payTo wallet"
                },
                status_code=403,
            )
        _recheck_store.record_optout(message["stall"], message["sender"])
        return {
            "ok": True,
            "kind": message["kind"],
            "opted_out": message["stall"].rstrip("/"),
        }
    if not nudge_svc.RATE_LIMITER.allow(
        message["sender"], nudge_svc.rate_limit_per_hour()
    ):
        return JSONResponse(
            {"error": "rate limit: too many nudges from this sender"},
            status_code=429,
        )
    stored = _recheck_store.store_nudge(message, nudge_svc.dedupe_key(message))
    return {
        "ok": True,
        "kind": message["kind"],
        "stored": stored,
        "duplicate": not stored,
    }


@app.post("/v1/internal/nudges")
async def nudge_inbox_read(
    req: NudgeInboxReadRequest | None = None, request: Request = None
):
    """Owner read of the nudge inbox: stored nudges (newest first)
    plus the opt-out registry. Fleet-internal secret gate, mirroring
    the siblings' /v1/internal/* routes exactly."""
    secret = os.environ.get("FLEET_INTERNAL_SECRET", "")
    if not secret:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    presented = request.headers.get("x-fleet-internal-secret", "")
    if not hmac.compare_digest(presented, secret):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    limit = req.limit if req is not None else 50
    return {
        "count": _recheck_store.nudge_count(),
        "nudges": _recheck_store.list_nudges(limit),
        "optouts": _recheck_store.list_optouts(),
    }


# --- free routes -----------------------------------------------------------------

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StallRow — a row of x402 micro-services</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 820px; margin: 40px auto;
         padding: 0 20px 60px; line-height: 1.55; color: #16202a; }
  code { font-family: ui-monospace, Menlo, monospace; }
  table { border-collapse: collapse; width: 100%; }
  td, th { border-bottom: 1px solid #dde5ec; padding: 6px 8px; text-align: left; vertical-align: top; }
</style>
</head>
<body>
<h1>StallRow</h1>
<p>Thirteen small x402 stalls under one roof: Base chain reads, a wallet
trust verdict, fetch tools, seller tools, a digest of open agent
jobs, and scheduled change detection for x402 resources and web pages. Every stall names its data sources and marks what it cannot
supply as <em>unknown</em> — nothing is fabricated, and if an upstream
fails the call returns 502 and the payment does not settle.
No accounts, no API keys: payment is the authentication.</p>
<p>See <a href="/quote">/quote</a> for prices, <a href="/skill.md">/skill.md</a>
for agent docs, and <a href="/.well-known/x402">/.well-known/x402</a>
for the machine-readable manifest.</p>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return LANDING_HTML


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": settings.service_name,
        "routes": len(PRICE_UNITS),
        # Durability of the recheck baseline/pack store, measured at
        # startup (config.resolve_recheck_db) — "persistent" only
        # when the store file lives on a mounted volume.
        "storage": {
            "recheck_store": (
                "persistent" if settings.recheck_db_persistent else "ephemeral"
            ),
            "recheck_db_path": settings.recheck_db_path,
        },
    }


@app.get("/quote")
async def quote():
    return {
        "service": settings.service_name,
        "endpoints": {
            path: {"price": settings.prices[path], "price_units": PRICE_UNITS[path]}
            for path in PRICE_UNITS
        },
        "asset": "USDC",
        "network": settings.network,
        "payTo": settings.pay_to,
        "protocol": "x402 v2 (exact scheme)",
    }


@app.get("/.well-known/x402")
async def well_known(request: Request):
    return JSONResponse(x402_manifest(settings, _public_base(request)))


@app.get("/skill.md", response_class=PlainTextResponse)
async def skill(request: Request):
    return skill_md(settings, _public_base(request))


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms(request: Request):
    return llms_txt(settings, _public_base(request))


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)


if __name__ == "__main__":
    main()
