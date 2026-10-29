"""RouteVerdict — x402 pay-per-call trust & liveness checks for x402 APIs.

Paid:   POST /v1/check   (USDC via x402 v2 "exact" scheme on Base)
Free:   GET  /, /health, /quote, /.well-known/x402, /skill.md, /llms.txt
        POST /v1/nudge (signed fleet-health mail — see nudge.py)
        POST /v1/internal/nudges (owner read, fleet-internal secret)

The check itself is observation-only: it probes a target endpoint WITHOUT
paying it and reports liveness, terms, discovery-schema quality, catalog
presence, and a diff against the previous check.
"""

from __future__ import annotations

import hmac
import json
import logging
import os

# Some shells/hosts export a no_proxy list containing bracketed IPv6
# entries ("[::1]"). The x402 SDK's httpx-based facilitator client parses
# that list as URLs and dies with "Invalid port: ':1]'", which turns every
# unpaid call into a 500 instead of a 402 — fatal optics for a trust
# service. Scrub just the bracketed entries before any SDK client is
# constructed. (Token Verdict only scrubbed this in its test conftest;
# RouteVerdict scrubs in-process so any host shell is safe.)
for _var in ("no_proxy", "NO_PROXY"):
    _val = os.environ.get(_var)
    if _val:
        _kept = [e for e in _val.split(",") if "[" not in e and "]" not in e]
        os.environ[_var] = ",".join(_kept)

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption, RouteConfig
from x402.http.middleware import fastapi_payment_middleware
from x402.mechanisms.evm.exact.server import ExactEvmScheme
from x402.server import x402ResourceServer

from . import checker as checker_svc
from . import nudge as nudge_svc
from .checker import run_check
from .config import load_settings
from .discovery import OWNERSHIP_PROOFS, bazaar_extension, llms_txt, skill_md, x402_manifest
from .store import CheckStore

log = logging.getLogger("route-verdict")
logging.basicConfig(level=logging.INFO)

settings = load_settings()  # raises if payout wallet is a placeholder

# --- x402 wiring -------------------------------------------------------------
# The facilitator is chosen by X402_FACILITATOR_URL alone (plus CDP keys for
# the CDP branch). Cataloging is settlement-driven per facilitator — each
# index lists only settlements through its OWN facilitator — so the env
# choice decides which catalog a settled payment feeds:
#   * CDP (api.cdp.coinbase.com, needs CDP_API_KEY_ID/SECRET): CDP Bazaar.
#   * PayAI (facilitator.payai.network, no key for exact): PayAI index.
#   * default keyless ultravioletadao: settles Base, feeds no major index.
# One deployment settles through one facilitator at a time; to appear in
# both indexes, settle at least one call under each configuration.
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

CHECK_DESCRIPTION = (
    "Send any x402 resource URL, get a trust verdict on the endpoint "
    "itself. Returns TRUSTED / CAUTION / AVOID with a 0-100 score from an "
    "observation-only live probe (never pays the target): payment terms, "
    "Bazaar discovery-schema quality, CDP Bazaar and PayAI catalog "
    "presence, plus a diff against the previous check. Use this when an "
    "agent is about to pay an unfamiliar x402 endpoint and needs to know "
    "it is alive, honestly described, and unchanged first."
)

routes = {
    "POST /v1/check": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=settings.pay_to,
                price=settings.price_usdc,
                network=settings.network,
            )
        ],
        description=CHECK_DESCRIPTION,
        mime_type="application/json",
        service_name=settings.service_name,  # ≤32 chars, forwarded to Bazaar
        tags=["x402", "trust", "liveness", "monitoring", "verification", "agents"],
        extensions={"bazaar": bazaar_extension()},
    ),
}

# --- app ---------------------------------------------------------------------
app = FastAPI(title="route-verdict", version="1.0.0")


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
# EVERY request including /health and the unpaid 402 challenge. That was
# the fleet's latency-variance problem (2026-10-24): Settled's latency
# component whipsawed on services that hadn't changed. (Same fix as
# token-verdict ff05d1c and stall-row 59e14b3.)
_payment_middleware = fastapi_payment_middleware(routes, resource_server)


_PASS_PATHS = {"/v1/check"}


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    # A call presenting a Fleet Pass id is paid from the pass ledger
    # in StallRow: debit before the handler, refund on failure.
    from . import fleet_pass as _fleet_pass

    debit = await _fleet_pass.debit_for(request, settings.service_name, _PASS_PATHS)
    if isinstance(debit, JSONResponse):
        return debit
    if debit:
        response = await call_next(request)
        if response.status_code >= 400:
            await _fleet_pass.refund(debit)
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


class CheckRequest(BaseModel):
    resource_url: str = Field(description="Full URL of the x402 resource to audit")


# The diff memory. Created lazily so importing the app (tests, tooling)
# never touches the filesystem until a real check runs.
_store: CheckStore | None = None


def get_store() -> CheckStore:
    global _store
    if _store is None:
        _store = CheckStore(settings.db_path)
    return _store


def _public_base(request: Request) -> str:
    """Public base URL of this service. Railway terminates TLS at the edge,
    so the request scheme arrives as http — indexers and agents need https."""
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RouteVerdict — trust &amp; liveness checks for x402 endpoints</title>
<meta name="description" content="Before an agent pays an unfamiliar x402 endpoint, it pays $0.05 to ask RouteVerdict: is it alive, what does it charge, is its discovery schema real, is it cataloged — and has anything changed since last time?">
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 760px; margin: 40px auto; padding: 0 20px 60px;
         line-height: 1.55; color: #16202a; background: #fbfcfd; }
  h1 { font-size: 2rem; margin-bottom: .2em; }
  .tag { font-size: 1.1rem; color: #33475b; margin-top: 0; }
  code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  pre { background: #0f1b26; color: #dcebf5; padding: 14px 16px;
        border-radius: 8px; overflow-x: auto; font-size: .85rem; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  td, th { border-bottom: 1px solid #dde5ec; padding: 6px 8px;
           text-align: left; vertical-align: top; }
  .pill { display: inline-block; background: #e7f0e9; color: #1d5c33;
          border-radius: 999px; padding: 2px 10px; font-size: .85rem; }
  a { color: #0b5cad; }
  .limits { background: #fdf6e5; border: 1px solid #ecd9a0;
            border-radius: 8px; padding: 10px 14px; }
</style>
</head>
<body>
<h1>RouteVerdict</h1>
<p class="tag">The trust layer for x402 itself. Before an agent pays an
unfamiliar x402 endpoint, it pays <strong>$0.05</strong> to ask RouteVerdict
first: is it alive, what does it charge, is its discovery schema real, is it
cataloged — and has anything changed since last time? No accounts, no API
keys: <em>payment is the authentication.</em></p>

<p><span class="pill">Live on Base mainnet</span>
<span class="pill">x402 v2 · exact scheme</span>
<span class="pill">$0.05 USDC / check</span>
<span class="pill">Observation only — never pays the target</span></p>

<h2>What a check returns</h2>
<p>One <code>POST /v1/check</code> with a resource URL returns:</p>
<ul>
  <li>a verdict — <strong>TRUSTED</strong>, <strong>CAUTION</strong>, or
      <strong>AVOID</strong> — with a 0-100 trust score and every deduction
      itemized</li>
  <li><strong>liveness</strong> — the endpoint probed live, unpaid: HTTP
      status, latency, whether its 402 parses as valid x402</li>
  <li><strong>terms</strong> — price, network, asset and payTo from the
      live challenge</li>
  <li><strong>schema quality</strong> — whether the Bazaar discovery output
      schema types real fields or is hollow (<code>{"type", "example"}</code>
      only — the shape 87.8% of listings ship)</li>
  <li><strong>catalog presence</strong> — listed in the CDP Bazaar? In the
      PayAI index? (a failed lookup reports <code>unknown</code>, never a
      fabricated "not listed")</li>
  <li><strong>diff</strong> — what changed since the previous check of the
      same URL: price, payTo, schema score, listing presence, liveness</li>
</ul>

<h2>How to call it</h2>
<pre>curl -X POST https://route-verdict-production.up.railway.app/v1/check \\
  -H 'content-type: application/json' \\
  -d '{"resource_url":"https://some-service.example.com/v1/endpoint"}'</pre>
<p>Unpaid calls return an HTTP 402 x402 challenge. Pay $0.05 USDC on Base
with any x402 v2 client, retry with the payment header, and the report
comes back. There is no signup and no key to manage — the settlement is
the credential.</p>

<h2>Endpoints</h2>
<table>
  <tr><th>Route</th><th>Price</th><th>Purpose</th></tr>
  <tr><td><code>POST /v1/check</code></td><td>$0.05</td>
      <td>Trust &amp; liveness check for one x402 resource URL (paid, x402)</td></tr>
  <tr><td><code>GET /quote</code></td><td>free</td>
      <td>Price, asset, network, pay-to wallet</td></tr>
  <tr><td><code>GET /.well-known/x402</code></td><td>free</td>
      <td>Machine-readable service manifest</td></tr>
  <tr><td><code>GET /skill.md</code></td><td>free</td>
      <td>Documentation written for agents</td></tr>
  <tr><td><code>GET /llms.txt</code></td><td>free</td>
      <td>Compact agent index</td></tr>
  <tr><td><code>GET /health</code></td><td>free</td><td>Liveness</td></tr>
</table>
<p>Source code:
<a href="https://github.com/QuincyGB/route-verdict">github.com/QuincyGB/route-verdict</a>
(public source — the scoring is deterministic and fully inspectable, and
the test suite ships with it). Sibling service:
<a href="https://github.com/QuincyGB/token-verdict">Token Verdict</a>,
risk verdicts for token contracts.</p>

<div class="limits">
<strong>Honest limits:</strong> RouteVerdict reads what an endpoint
publishes and what the public catalogs hold. It never settles a test
payment to the target, does not grade the paid payload's quality, and
cannot see inside the target's wallet — the diff flags payTo changes,
it does not explain them.
</div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return LANDING_HTML


@app.get("/health")
async def health():
    return {"ok": True, "service": settings.service_name}


@app.get("/quote")
async def quote():
    """Free: what the paid endpoint costs and where it settles."""
    return {
        "service": settings.service_name,
        "endpoint": "/v1/check",
        "price": settings.price_usdc,
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


@app.post("/v1/internal/check")
async def check_internal(req: CheckRequest, request: Request):
    """Fleet-internal unpaid path for StallRow's /v1/orchestrate.
    Secret discipline mirrors Token Verdict's RapidAPI route:
    FLEET_INTERNAL_SECRET unset = 404, wrong secret = 403. Absent
    from the x402 routes dict and every discovery surface."""
    secret = settings.fleet_internal_secret
    if not secret:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    presented = request.headers.get("x-fleet-internal-secret", "")
    if not hmac.compare_digest(presented, secret):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await check(req)


# --- Nudge inbox ------------------------------------------------------------------
# The two-way leg of Fleet Check (app/nudge.py; spec:
# x402-loop-kits/nudge-inbox.md). POST /v1/nudge is FREE — inbound
# mail is not a product, and it is absent from the x402 routes dict
# and every paid surface, so the priced route count does not move.
# Every message is EIP-191-signed; unsigned or wrongly-signed mail
# is a clean 4xx, never a 5xx. The owner reads the inbox through
# the fleet-internal gate, same discipline as /v1/internal/check:
# secret unset = 404, wrong secret = 403.

class NudgeInboxReadRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


async def _stall_pay_to(stall: str) -> str | None:
    """The payTo a stall's own discovery doc publishes — the
    opt-out verifier's ground truth for who controls that stall.
    Fetched under this service's SSRF-guarded fetch discipline
    (app/checker.py: resolve + reject non-public, per-hop redirect
    checks)."""
    try:
        status, _headers, body = await checker_svc._fetch_once(
            checker_svc._shared_client(),
            "GET",
            f"{stall.rstrip('/')}/.well-known/x402",
            {"user-agent": checker_svc.USER_AGENT},
            settings.fetch_timeout_s,
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
        get_store().record_optout(message["stall"], message["sender"])
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
    stored = get_store().store_nudge(message, nudge_svc.dedupe_key(message))
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
    /v1/internal/check exactly."""
    secret = settings.fleet_internal_secret
    if not secret:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    presented = request.headers.get("x-fleet-internal-secret", "")
    if not hmac.compare_digest(presented, secret):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    limit = req.limit if req is not None else 50
    return {
        "count": get_store().nudge_count(),
        "nudges": get_store().list_nudges(limit),
        "optouts": get_store().list_optouts(),
    }


@app.post("/v1/check")
async def check(req: CheckRequest):
    """Paid endpoint — unreachable until the x402 middleware verifies payment."""
    resource_url = req.resource_url.strip()
    try:
        return await run_check(
            resource_url,
            get_store(),
            check_timeout=settings.fetch_timeout_s,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception:  # noqa: BLE001 — never leak tracebacks to callers
        log.exception("check failed for %s", resource_url)
        return JSONResponse({"error": "check failed"}, status_code=502)


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)


if __name__ == "__main__":
    main()
