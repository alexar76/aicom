"""FastAPI app factory — every oracle gets a compliant AIMarket v2 surface for free."""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
import time
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from oracle_core import calls as calls_mod
from oracle_core.calls import CallLog
from oracle_core.price_gate import PriceGate
from oracle_core.protocol import OracleSpec, Protocol
from oracle_core.ratelimit import RateLimiter
from oracle_core.tiers import FreeTierExceeded, PaidTierPolicy, enforce_free_tier

logger = logging.getLogger(__name__)


class InvokeRequest(BaseModel):
    capability_id: str
    input: dict[str, Any] = Field(default_factory=dict)


def peer_is_local_proxy(peer: str) -> bool:
    """Could the TCP peer be our own reverse proxy (this host or its docker network)?"""
    try:
        addr = ipaddress.ip_address((peer or "").split("%")[0])
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def client_key(request: Request) -> str:
    """The caller's address: the rate-limit key, and what the paid tier's proxy list is
    checked against (``tiers.is_paid``).

    Behind nginx the socket peer is 127.0.0.1, so the proxy-set ``X-Real-IP`` is the
    caller, and failing that the RIGHT-most ``X-Forwarded-For`` hop (nginx APPENDS the
    real peer; the left-most entry is whatever the caller typed). Those headers count
    only when the peer is such a proxy: a caller that reached the port another way (a
    neighbour on the docker network, a published port) sent them itself, and with
    ORACLE_TRUSTED_PAYMENT_PROXIES set, ``X-Real-IP: <the hub>`` bought the paid tier
    for free.
    """
    peer = request.client.host if request.client else ""
    if peer_is_local_proxy(peer):
        xri = (request.headers.get("x-real-ip") or "").strip()
        if xri:
            return xri
        hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer or "*"


def create_app(
    spec: OracleSpec,
    cors_origins: Optional[str] = None,
    invoke_rate_limit: int = 120,
    extra: Optional[Callable[[FastAPI, Protocol], None]] = None,
    paid_tier: Optional[PaidTierPolicy] = None,
    price_gate: Optional[PriceGate] = None,
    call_log: Optional[CallLog] | bool = None,
) -> FastAPI:
    proto = Protocol(spec)
    limiter = RateLimiter(invoke_rate_limit)
    # Read from the environment by default, and empty by default there too, so an
    # oracle that says nothing about payment grants nothing — see oracle_core.tiers.
    policy = PaidTierPolicy.from_env() if paid_tier is None else paid_tier
    # Which hubs may admit a priced call, also from the environment. Off unless a hub is
    # trusted or the mode is set, which is what this core did before — see
    # oracle_core.price_gate.
    gate = PriceGate.from_env(spec.public_url) if price_gate is None else price_gate
    app_priced = [c.capability_id for c in spec.capabilities if c.price_per_call_usd > 0]
    if gate.mode == "off" and app_priced and os.environ.get("AIFACTORY_PROD", "").strip() == "1":
        logger.warning(
            "%s: price gate is off, so %d priced capabilities answer any caller that reaches "
            "this port, unpaid. Set ORACLE_TRUSTED_HUBS to the hubs that sell them.",
            spec.product_id, len(app_priced),
        )
    # Budgets in CPU-milliseconds per minute, for the capabilities that sell
    # computation. The global limiter above still applies on top and counts requests,
    # so a caller must be under BOTH: these can only ever tighten what the app was
    # configured with, never widen it.
    per_cap: dict[str, RateLimiter] = {
        c.capability_id: RateLimiter(c.cpu_budget_ms_per_min)
        for c in spec.capabilities
        if c.cpu_budget_ms_per_min is not None
    }
    # Aggregate budgets, keyed on nothing — one shared bucket per capability, i.e. the
    # share of the machine it may consume. Held in a separate map from per_cap so the
    # two stay independently expressible: a capability may want an aggregate ceiling
    # with no per-client one, or vice versa.
    per_cap_global: dict[str, RateLimiter] = {
        c.capability_id: RateLimiter(c.global_cpu_budget_ms_per_min)
        for c in spec.capabilities
        if c.global_cpu_budget_ms_per_min is not None
    }

    app = FastAPI(title=spec.name, description=spec.description, version=spec.version)
    app.state.protocol = proto  # exposed for tests / extra routes
    app.state.price_gate = gate
    # Every invoke, written down (oracle_core.calls): from the environment by default
    # (ORACLE_CALLS=1 turns it on), True to keep one regardless, False for none, or a CallLog
    # a caller built.
    if call_log is None or call_log is True:
        log_of_calls = calls_mod.from_env(spec.product_id, force=call_log is True)
    else:
        log_of_calls = call_log or None
    app.state.call_log = log_of_calls

    # Three states, not two. `None` means the oracle said nothing about CORS and keeps
    # the historical wide-open default; a non-empty string is an allowlist; an EXPLICIT
    # empty string is an operator saying "no browser origin may read this" and must fail
    # CLOSED. Before this split, `or ["*"]` collapsed empty onto `*`, so every caller that
    # defaulted its env read to "" — and every deployment that set `X_CORS_ORIGINS=` to
    # lock the service down — silently got the opposite of what it asked for.
    if cors_origins is None:
        origins = ["*"]
    else:
        origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,  # "*" + credentials is invalid per the CORS spec
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "oracle": spec.product_id, "capabilities": len(spec.capabilities)}

    @app.get("/.well-known/ai-market.json")
    async def well_known() -> dict[str, Any]:
        doc = proto.well_known()
        # Only when the gate is on, so an oracle that never configured it keeps a
        # byte-identical document.
        if gate.mode != "off":
            doc["price_gate"] = gate.describe()
        return doc

    @app.get("/ai-market/v2/manifest")
    async def manifest() -> dict[str, Any]:
        return proto.manifest()

    @app.post("/ai-market/v2/invoke")
    async def invoke(req: InvokeRequest, request: Request) -> Any:
        # One call-log row per invoke, whichever way it ends: served, refused, over a limit,
        # failed or crashed. What the caller sees is unchanged.
        started = time.perf_counter()
        note: dict[str, Any] = {}
        status, body, reason = 500, None, ""
        try:
            response = await _invoke(req, request, note)
        except HTTPException as exc:
            status, reason = exc.status_code, str(exc.detail)
            raise
        else:
            if isinstance(response, JSONResponse):
                status = response.status_code
                try:
                    body = json.loads(bytes(response.body))
                except ValueError:
                    body = None
            else:
                status, body = 200, response
            if isinstance(body, dict) and not body.get("ok", True):
                reason = str(body.get("error") or body.get("detail") or "")
            elif isinstance(body, dict) and status != 200:
                reason = str(body.get("error") or body.get("detail") or "")
            return response
        finally:
            if log_of_calls is not None:
                _note_call(req, request, note, status, body, reason, started)

    def _note_call(req: InvokeRequest, request: Request, note: dict[str, Any], status: int,
                   body: Any, reason: str, started: float) -> None:
        try:
            outcome = calls_mod.outcome_for(status, body)
            if note.get("paid"):
                kind, hub = "paid_tier", ""
            elif note.get("status") == "valid":
                kind, hub = "hub", str(note.get("hub") or "")
            else:
                kind, hub = "anonymous", ""
            try:
                price = float(spec.capability(req.capability_id).price_per_call_usd or 0.0)
            except ValueError:
                price = 0.0
            inp = req.input if isinstance(req.input, dict) else {}
            log_of_calls.record(
                capability_id=req.capability_id, http_status=status, outcome=outcome,
                latency_ms=(time.perf_counter() - started) * 1000.0, caller_kind=kind,
                caller_hub=hub, client=client_key(request),
                # Revenue is a served priced call a hub signed: the hub billed it (or gave it
                # as its trial; its ledger says which). An operator-nominated caller (the
                # operator's own ATLAS, a payment proxy) and an anonymous call never count.
                price_usd=price if outcome == "ok" and kind == "hub" else 0.0,
                reason=calls_mod.scrub_reason(reason, req.input),
                input_digest=calls_mod.input_sha256(req.input),
                subject=str(inp.get("actuator_id") or inp.get("device_id") or ""))
        except Exception:  # noqa: BLE001 — the log must never break an answer
            logger.exception("call log: could not record %s", req.capability_id)

    async def _invoke(req: InvokeRequest, request: Request, note: dict[str, Any]) -> Any:
        caller = client_key(request)
        if not limiter.allow(caller):
            raise HTTPException(status_code=429, detail="rate limited")
        paid = policy.is_paid(request.headers, caller)
        note["paid"] = paid

        # The price gate comes before everything that does work or spends a budget. A
        # priced capability is served to a call a trusted hub admitted (it signed it), to
        # an operator-nominated paid caller, or to nobody: the hub's 402 used to be the
        # only payment door, and this port is public. An unknown capability falls
        # through, so the handler below names it.
        try:
            listed = spec.capability(req.capability_id)
        except ValueError:
            listed = None
        if listed is not None:
            refused = gate.check(
                req.capability_id, float(listed.price_per_call_usd or 0.0), req.input,
                request.headers, paid=paid, caller=caller, note=note,
            )
            if refused is not None:
                return JSONResponse(status_code=refused[0], content=refused[1])

        # The free-tier ceiling is checked BEFORE the CPU budget, and the order is load
        # bearing. A request over the ceiling is over it permanently, so answering 429
        # ("retry shortly") would send the caller into a retry loop that can never
        # succeed, while 402 tells them the actual ceiling and that payment lifts it.
        # Budget exhaustion, by contrast, really does clear on its own — so it is the
        # refusal that deserves 429, and it belongs second.
        #
        # Protocol.invoke enforces the same ceiling again. That is deliberate: this
        # layer produces the better error, and that layer keeps the invariant true for
        # every caller, including ones that never come through HTTP.
        cap = per_cap.get(req.capability_id) or per_cap_global.get(req.capability_id)
        if not paid:
            try:
                enforce_free_tier(
                    req.capability_id,
                    spec.capability(req.capability_id).free_tier_max,
                    req.input,
                )
            except ValueError:
                # Unknown capability_id — fall through so the normal handler produces
                # the "Unknown capability: …" message rather than a confusing 402.
                pass
            except FreeTierExceeded as exc:
                return JSONResponse(status_code=402, content=exc.as_body())

        cap_limiter = per_cap.get(req.capability_id)
        cap_global = per_cap_global.get(req.capability_id)
        if cap_limiter is not None or cap_global is not None:
            # Estimated before the work, because that is the only time rationing it is
            # possible. A cheap input costs almost nothing and stays freely repeatable;
            # an expensive one spends the minute in a single call.
            # Present by construction: both maps are built from spec.capabilities, so a
            # hit in either means this id exists.
            cost_ms = spec.capability(req.capability_id).estimate_cost_ms(req.input)
            # Both budgets are TESTED before either is charged. Charging the per-client
            # bucket and then refusing on capacity would debit a caller for work that
            # was never performed, and they would have no way to tell.
            if cap_limiter is not None and not cap_limiter.would_allow(caller, cost_ms):
                # Distinct message from the app-wide one: a caller well under 120/min
                # who is refused anyway would otherwise have no way to tell that this
                # capability is budgeted separately, so the error names the budget, what
                # this call would have cost, and what is left.
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"rate limited: {req.capability_id} budgets "
                        f"{cap_limiter.limit:.0f} ms of CPU per minute per client "
                        f"because its cost scales with the input; this call is "
                        f"~{cost_ms:.0f} ms and {cap_limiter.limit - cap_limiter.spent(caller):.0f} ms "
                        f"remain. Retry later, or ask for less work."
                    ),
                )
            if cap_global is not None and not cap_global.would_allow("*", cost_ms):
                # Reported AFTER the per-client budget so the message a normal caller
                # sees is about their own allowance rather than about the server's load.
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"rate limited: {req.capability_id} is at its capacity ceiling "
                        f"of {cap_global.limit:.0f} ms of CPU per minute across all "
                        f"clients — retry shortly"
                    ),
                )
            # Both budgets said yes; charge them.
            if cap_limiter is not None:
                cap_limiter.allow(caller, cost_ms)
            if cap_global is not None:
                cap_global.allow("*", cost_ms)
        try:
            result = await proto.invoke(req.capability_id, req.input, paid=paid)
            return {"ok": True, **result}
        except FreeTierExceeded as exc:
            # Normally unreachable — the check above already answered. Kept because
            # Protocol.invoke owns the invariant, and if the two ever disagree the
            # answer should still be the correct 402 rather than an uncaught 500.
            # 402, not 400: nothing about the request is malformed — the caller asked
            # for work this tier does not include. 402 is the status the rest of the
            # ecosystem already uses for that (the hub answers it for a priced invoke
            # with no channel), so a client that handles one handles this.
            return JSONResponse(status_code=402, content=exc.as_body())
        except ValueError as exc:
            # A handler rejecting its input, e.g. "points must be a list of [x, y] pairs".
            return {"ok": False, "error": str(exc)}
        except KeyError as exc:
            # A required field was simply absent. Only ValueError used to be translated, so
            # `lumen.score` without `target_node` answered a bare 500 Internal Server Error
            # — a caller that read the schema and mistyped one field learned nothing and had
            # nothing to correct. KeyError stringifies to a quoted name, hence the strip.
            return {"ok": False, "error": f"missing required input field: {str(exc).strip(chr(39))}"}
        except RuntimeError as exc:
            # A federated upstream refused. The oracle-family proxy raises this carrying the
            # upstream's own message ("Unknown capability: …"), which is exactly what the
            # caller needs and exactly what the 500 was swallowing.
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — deliberate catch-all, see below
            # Anything else is a real fault, not a refusal, so it stays a 5xx. But it says
            # what broke: an empty "Internal Server Error" is indistinguishable from a dead
            # process, and callers retry it forever. Full traceback goes to the log.
            logger.exception("invoke %s failed unexpectedly", req.capability_id)
            raise HTTPException(
                status_code=500, detail=f"{type(exc).__name__}: {exc}"
            ) from exc

    # ── the operator's view of the call log ──────────────────────────────────
    # Behind ORACLE_OPS_TOKEN (a Bearer token); without one the routes answer 503 and never
    # open unauthenticated. Times are ISO 8601 UTC or unix seconds; the default is 24 h.
    def _ops(request: Request) -> CallLog:
        token = os.environ.get("ORACLE_OPS_TOKEN", "")
        if not token:
            raise HTTPException(status_code=503, detail="ops API off: set ORACLE_OPS_TOKEN")
        given = request.headers.get("authorization", "")
        if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
            raise HTTPException(status_code=401, detail="ops API needs the operator's bearer token")
        if log_of_calls is None:
            raise HTTPException(status_code=503, detail="the call log is off (set ORACLE_CALLS=1)")
        return log_of_calls

    def _window(since: str | None, until: str | None) -> tuple[float, float]:
        end = _when(until, time.time())
        return _when(since, end - 86_400), end

    @app.get("/ops/v1/stats")
    async def ops_stats(request: Request, since: str | None = None, until: str | None = None):
        lg = _ops(request)
        start, end = _window(since, until)
        return lg.stats(since=start, until=end)

    @app.get("/ops/v1/calls")
    async def ops_calls(request: Request, since: str | None = None, until: str | None = None,
                        capability: str = "", outcome: str = "", limit: int = 100):
        lg = _ops(request)
        start, end = _window(since, until)
        return {"calls": lg.calls(since=start, until=end, capability=capability,
                                  outcome=outcome, limit=limit)}

    @app.get("/ops/v1/metrics")
    async def ops_metrics(request: Request):
        return PlainTextResponse(_ops(request).prometheus(),
                                 media_type="text/plain; version=0.0.4")

    if extra is not None:
        extra(app, proto)

    return app


def _when(value: str | None, default: float) -> float:
    if value in (None, ""):
        return float(default)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{text[:40]!r} is not a time") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
