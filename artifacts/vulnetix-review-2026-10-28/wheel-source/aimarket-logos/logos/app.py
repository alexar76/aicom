"""LOGOS FastAPI application.

Routes:
  GET  /health                          — service health
  GET  /api/v1/snapshot                 — current federation state
  POST /api/v1/ask                      — NL query → insights
  GET  /api/v1/insights                 — recent insights
  GET  /api/v1/report/daily             — today's briefing
  GET  /api/v1/anomalies                — anomalies (status=open|acknowledged|all)
  POST /api/v1/anomalies/{id}/acknowledge
  GET  /api/v1/trend                    — metric time-series from snapshots
  GET  /api/v1/consumption              — measured settlement + catalog-pricing digest
  GET  /api/v1/federation/peers         — hub peer list
  GET  /api/v1/federation/capabilities  — federated capability catalog
  POST /api/v1/federation/invoke        — NEXUS read-only invoke proxy
  GET  /.well-known/agent-card.json     — A2A agent card
  POST /api/v1/a2a/tasks                — A2A analytics.ask delegation
  POST /api/v1/chat                     — AI assistant (non-streaming)
  POST /api/v1/chat/stream              — AI assistant (SSE streaming)
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import ipaddress
import logging
import math
import os
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from logos import __version__
from logos.agent.assistant import LogosAssistant
from logos.agent.config import AgentConfig
from logos.agent.guard import InputGuard
from logos.analyst.engine import AnalystEngine
from logos.anomalies.detector import AnomalyDetector
from logos.config import LogosConfig
from logos.models import AskRequest
from logos.store import LogosStore


# Request/response models at module scope — FastAPI generates the schema from
# them, so they must not be nested inside create_app().
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    reply: str
    guard_verdict: str = "allow"


logger = logging.getLogger("logos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


def _from_local_proxy(peer: str) -> bool:
    """Could the TCP peer be our own reverse proxy (this host or its docker network)? Only
    then are X-Real-IP / X-Forwarded-For the caller's: anyone reaching the port another way
    writes them itself and gets a fresh rate-limit bucket per request."""
    try:
        addr = ipaddress.ip_address((peer or "").split("%")[0])
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def _client_key(request: Request) -> str:
    """Who to rate-limit.

    `request.client.host` is the nginx address for every public caller, because the
    app binds loopback and the edge is the only way in — so one bucket was shared by
    the entire internet and a single eager poller 429'd everyone else. (The Alien
    Monitor did exactly that: four endpoints on a 1.5 s tick.) The edge sets
    X-Real-IP / X-Forwarded-For, so behind it the header is the identity; a caller
    that reaches the port directly is keyed on its own address instead.
    """
    peer = request.client.host if request.client else ""
    if not _from_local_proxy(peer):
        return peer or "unknown"  # not through the edge: the headers are the caller's own
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real
    hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    if hops:
        # RIGHT-most, not left-most: nginx appends the peer it saw ($proxy_add_x_forwarded_for),
        # so the left entry is the caller's own claim and a fresh one per request would mean a
        # fresh, empty bucket per request.
        return hops[-1]
    return peer or "unknown"


def create_app(config: LogosConfig | None = None) -> FastAPI:
    cfg = config or LogosConfig.from_env()
    store = LogosStore(cfg.data_dir)
    engine = AnalystEngine(cfg)
    detector = AnomalyDetector(
        z_threshold=cfg.anomaly_zscore_threshold,
        min_samples=cfg.anomaly_min_samples,
        window_days=cfg.anomaly_window_days,
        poll_interval_s=cfg.poll_interval_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.open()
        app.state.store = store
        app.state.engine = engine
        app.state.detector = detector
        app.state.cfg = cfg

        # Rebuild the statistical baseline from real persisted telemetry so a
        # process restart does not erase anomaly context. Generated alerts are
        # discarded during warm-up; only the rolling observations are restored.
        warm_limit = max(cfg.anomaly_min_samples, min(
            cfg.anomaly_window_days * 24 * 3600 // max(1, cfg.poll_interval_s),
            50_000,
        ))
        for saved in reversed(store.recent_snapshots(warm_limit)):
            detector.ingest_snapshot(
                saved,
                saved.get("findings", {}),
                saved.get("treasury", {}),
            )

        # Background poll task
        poll_task = asyncio.create_task(_poll_loop(store, engine, detector, cfg))

        yield

        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
        store.close()

    app = FastAPI(
        title="LOGOS — Federation Analytics Engine",
        description="Cross-hub analytics, anomaly detection, and NL insights.",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS — reject * with credentials
    origins = [o.strip() for o in cfg.cors_origins.split(",") if o.strip()]
    if "*" in origins and len(origins) > 1:
        logger.warning("CORS: '*' mixed with specific origins — removing '*'")
        origins = [o for o in origins if o != "*"]
    if "*" in origins:
        allow_credentials = False
    else:
        allow_credentials = True
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── auth middleware ──────────────────────────────────────────────────
    # Shared token from LOGOS_API_TOKEN env. When set, every /api/ route
    # requires X-Logos-Token header.  When unset (the default), API is open
    # — appropriate for the localhost-only federation tier behind nginx.
    _API_TOKEN = os.environ.get("LOGOS_API_TOKEN", "").strip()

    # Routes that change what an OPERATOR sees are not covered by the "unset token →
    # open API" default. Everything else under /api/ is read-only intelligence — the
    # POSTs to ask/chat/federation-invoke/a2a carry a query, not a mutation. Anomaly
    # acknowledgement is the exception: with no token configured, anyone on the internet
    # could silently suppress every anomaly LOGOS had raised.
    _OPERATOR_STATE = re.compile(r"^/api/v1/anomalies/[^/]+/acknowledge$")

    # Routes that spend the operator's LLM budget per request. The "unset token → open
    # API" default was justified as "appropriate for the localhost-only federation tier
    # behind nginx" — but deploy/nginx/logos.modelmarket.dev.conf proxies /api/ to the
    # public internet, so on the live deployment these are anonymous, billable calls. The
    # per-IP limiter below (30/min) is not a budget: an attacker with a residential-proxy
    # fleet has as many buckets as addresses, which is exactly the traffic SKOPOS already
    # observed against this ecosystem. So there is also a GLOBAL hourly ceiling.
    _LLM_SPEND = re.compile(
        r"^/api/v1/(ask|chat|chat/stream|a2a/tasks|federation/invoke)$"
    )
    _LLM_SPEND_MAX_PER_HOUR = int(os.environ.get("LOGOS_LLM_MAX_PER_HOUR", "120"))
    _llm_spend_calls: list[float] = []

    def _llm_budget_available() -> bool:
        now = time.monotonic()
        cutoff = now - 3600.0
        _llm_spend_calls[:] = [t for t in _llm_spend_calls if t > cutoff]
        if len(_llm_spend_calls) >= _LLM_SPEND_MAX_PER_HOUR:
            return False
        _llm_spend_calls.append(now)
        return True

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            if _API_TOKEN:
                supplied = (request.headers.get("X-Logos-Token") or "").strip()
                if not hmac.compare_digest(supplied, _API_TOKEN):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "X-Logos-Token header required"},
                    )
            else:
                if _OPERATOR_STATE.match(path):
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": "LOGOS_API_TOKEN is not configured — operator actions "
                                      "are disabled. Set it to enable acknowledgement."
                        },
                    )
                if _LLM_SPEND.match(path) and not _llm_budget_available():
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "LOGOS is answering anonymously and has spent its hourly "
                                f"model budget ({_LLM_SPEND_MAX_PER_HOUR} calls). Set "
                                "LOGOS_API_TOKEN to authenticate callers, or raise "
                                "LOGOS_LLM_MAX_PER_HOUR."
                            )
                        },
                    )
        return await call_next(request)

    # ── simple in-memory rate limiter ─────────────────────────────────────
    # Per-IP token bucket, resets every window_s.  Lightweight — no Redis
    # needed for the federation tier (single-digit concurrent users).
    _RATE_WINDOW_S = int(os.environ.get("LOGOS_RATE_WINDOW_S", "60"))
    _RATE_MAX = int(os.environ.get("LOGOS_RATE_MAX", "30"))
    _rate_buckets: dict[str, list[float]] = defaultdict(list)

    @app.middleware("http")
    async def _rate_limit_middleware(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        ip = _client_key(request)
        now = time.monotonic()
        # Sweep stale IPs once the table grows past 1000 entries
        if len(_rate_buckets) > 1000:
            stale = [k for k, v in _rate_buckets.items() if not v or v[-1] < now - _RATE_WINDOW_S * 2]
            for k in stale:
                del _rate_buckets[k]
        bucket = _rate_buckets[ip]
        cutoff = now - _RATE_WINDOW_S
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= _RATE_MAX:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after_s": _RATE_WINDOW_S},
            )
        bucket.append(now)
        return await call_next(request)

    # ── routes ────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "logos", "version": __version__}

    @app.get("/api/v1/snapshot")
    async def snapshot():
        engine: AnalystEngine = app.state.engine
        results = await engine.snapshot()
        hub = results.get("hub", {})
        momus = results.get("momus", {})
        treasury = results.get("treasury", {})
        return {
            **hub,
            "findings": momus,
            "treasury": treasury,
        }

    @app.post("/api/v1/ask")
    async def ask(req: AskRequest):
        engine: AnalystEngine = app.state.engine
        store: LogosStore = app.state.store
        # Guard /ask queries too: an attacker can POST an injection payload
        # here, it lands in insight_log.query_text, and the assistant later
        # embeds it in its system prompt.
        guard = InputGuard()
        gv = guard.check(req.query)
        if gv.action.value == "block":
            raise HTTPException(status_code=400, detail=f"Query blocked: {gv.reason}")
        # Sanitize before storing: strip injection markers, cap length
        safe_query = req.query[:200].replace("\n", " ").replace("\r", "")
        resp = await engine.ask(req)
        for insight in resp.insights:
            store.save_insight(insight, safe_query)
        return resp

    @app.get("/api/v1/insights")
    async def insights(since: str = Query(default=""), limit: int = Query(default=20, le=100)):
        store: LogosStore = app.state.store
        items = store.recent_insights(limit)
        if since:
            items = [i for i in items if i.generated_at >= since]
        return {"insights": [i.model_dump() for i in items]}

    @app.get("/api/v1/report/daily")
    async def daily_report():
        engine: AnalystEngine = app.state.engine
        store: LogosStore = app.state.store
        # Fetch latest data
        results = await engine.snapshot()
        hub = results.get("hub", {})
        momus = results.get("momus", {})
        skopos = results.get("skopos", {})
        treasury = results.get("treasury", {})
        anomalies_list = store.get_anomalies(acknowledged=False)
        recent = store.recent_insights(10)

        report = await engine.daily_report(
            snapshot=hub, findings=momus, remediation=skopos,
            treasury=treasury, anomalies=anomalies_list, recent_insights=recent,
        )
        store.save_report(report)
        return report

    @app.get("/api/v1/anomalies")
    async def anomalies(status: str = Query(default="open", pattern="^(open|acknowledged|all)$")):
        """List anomalies.

        ``status=open`` (default) returns unacknowledged alerts — the operator's
        working set. ``acknowledged`` returns the handled ones, ``all`` returns
        both, which is what the history heatmap needs.
        """
        store: LogosStore = app.state.store
        wanted = {"open": False, "acknowledged": True, "all": None}[status]
        items = store.get_anomalies(acknowledged=wanted)
        return {"anomalies": [a.model_dump() for a in items]}

    @app.post("/api/v1/anomalies/{anomaly_id}/acknowledge")
    async def acknowledge_anomaly(anomaly_id: str):
        store: LogosStore = app.state.store
        ok = store.acknowledge_anomaly(anomaly_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Anomaly not found or already acknowledged")
        return {"status": "ok", "anomaly_id": anomaly_id}

    @app.get("/api/v1/federation/peers")
    async def federation_peers():
        results = await engine.snapshot()
        hub = results.get("hub", {})
        return {"peers": hub.get("peers", []), "total": hub.get("total_hubs")}

    @app.get("/api/v1/trend")
    async def trend(metric: str = Query(default="total_capabilities"), limit: int = Query(default=24, le=100)):
        """Return time-series of a metric from stored snapshots."""
        store: LogosStore = app.state.store
        snapshots = store.recent_snapshots(limit)
        points = []
        for s in reversed(snapshots):
            try:
                # ``recent_snapshots`` returns the stored payload flattened next
                # to ``captured_at``.  Missing/None metrics are unavailable, not
                # zero-valued observations, and must not enter a trend line.
                if metric not in s or s[metric] is None:
                    continue
                points.append({"ts": s.get("captured_at", ""), "v": float(s[metric])})
            except (TypeError, ValueError):
                continue
        return {"metric": metric, "points": points}

    @app.get("/api/v1/consumption")
    async def consumption():
        """Federation-wide LLM consumption — spend, invocations, per-hub breakdown."""
        from logos.sources.consumption import ConsumptionSource
        src = ConsumptionSource(cfg.hub_url, cfg.hub_timeout_s)
        return await src.fetch()

    @app.get("/api/v1/federation/capabilities")
    async def federation_capabilities():
        """Return the federated capability catalog from the hub manifest."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=cfg.hub_timeout_s) as c:
                r = await c.get(f"{cfg.hub_url.rstrip('/')}/ai-market/v2/manifest")
                r.raise_for_status()
                manifest = r.json()
                tools = manifest.get("tools", [])
                return {
                    "capabilities": [
                        {
                            "product_id": t.get("product_id", ""),
                            "capability_id": t.get("capability_id", ""),
                            "source_hub": t.get("source_hub") or "local",
                            "description": t.get("description", ""),
                            "price_per_call_usd": t.get("routed_price_usd") if t.get("routed_price_usd") is not None else t.get("price_per_call_usd"),
                            "provider_hub": t.get("source_hub") or t.get("provider_hub", ""),
                        }
                        for t in tools
                    ],
                    "total": len(tools),
                    "hubs_indexed": manifest.get("hubs_indexed"),
                }
        except Exception:
            return {"capabilities": [], "total": 0, "hubs_indexed": 0, "error": "hub unreachable"}

    @app.post("/api/v1/federation/invoke")
    async def federation_invoke(request: Request):
        """Proxy a hub.invoke call — the NEXUS playground's one-button invoke."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        capability_id = body.get("capability_id", "")
        inp = body.get("input", {})
        if not isinstance(capability_id, str) or not capability_id:
            raise HTTPException(status_code=400, detail="capability_id required")
        if not isinstance(inp, dict):
            raise HTTPException(status_code=400, detail="input must be a JSON object")
        for name in ("product_id", "source_hub"):
            if name in body and not isinstance(body[name], str):
                raise HTTPException(status_code=400, detail=f"{name} must be a string")
        ceiling = body.get("max_price_usd")
        if ceiling is not None and (
            isinstance(ceiling, bool) or not isinstance(ceiling, (int, float))
            or not math.isfinite(ceiling) or ceiling < 0
        ):
            raise HTTPException(status_code=400, detail="max_price_usd must be a nonnegative finite number")
        if not _is_read_only_capability(capability_id):
            raise HTTPException(
                status_code=403,
                detail="LOGOS NEXUS is read-only; mutating capability refused",
            )
        try:
            import httpx
            async with httpx.AsyncClient(timeout=cfg.hub_timeout_s) as c:
                # The manifest owns route identity. A capability name alone is not
                # a product ID and can be shared by several federated providers.
                catalog = await c.get(f"{cfg.hub_url.rstrip('/')}/ai-market/v2/manifest")
                catalog.raise_for_status()
                matches = [tool for tool in catalog.json().get("tools", [])
                           if tool.get("capability_id") == capability_id]
                for name in ("product_id", "source_hub"):
                    if body.get(name):
                        matches = [tool for tool in matches
                                   if (tool.get(name) or ("local" if name == "source_hub" else "")) == body[name]]
                if not matches:
                    raise HTTPException(status_code=404, detail="Capability route is no longer in the catalog; refresh and choose again")
                if len(matches) != 1:
                    raise HTTPException(status_code=409, detail="Multiple providers offer this capability; choose a product and source hub")
                tool = matches[0]
                if not tool.get("product_id"):
                    raise HTTPException(status_code=502, detail="Hub catalog omitted the product ID")
                payload = {
                    "product_id": tool["product_id"],
                    "capability_id": capability_id,
                    "source_hub": tool.get("source_hub") or "local",
                    "input": inp,
                }
                if ceiling is not None:
                    payload["max_price_usd"] = ceiling
                r = await c.post(
                    f"{cfg.hub_url.rstrip('/')}/ai-market/v2/invoke", json=payload,
                )
                if not r.is_success:
                    # Keep the Hub's actionable error (payment, input, route, etc.)
                    # instead of replacing it with httpx's generic status message.
                    try:
                        refusal = r.json()
                    except ValueError:
                        refusal = {}
                    detail = (refusal.get("detail") or refusal.get("error")) if isinstance(refusal, dict) else None
                    if not isinstance(detail, str):
                        detail = f"Hub returned HTTP {r.status_code}"
                    return JSONResponse(status_code=r.status_code, content={
                        "status": "error", "error": detail[:1000], "routed_via": cfg.hub_url,
                    })
                r.raise_for_status()
                data = r.json()
                return {
                    "status": "ok",
                    "result": data.get("result", data.get("output", data)),
                    "price_usd": data.get("price_usd"),
                    "routing_fee_usd": data.get("routing_fee_usd"),
                    "source": data.get("source", "hub"),
                    "verifiable": data.get("verifiable"),
                    "routed_via": cfg.hub_url,
                }
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("NEXUS hub request failed: %s", exc)
            return JSONResponse(status_code=502, content={
                "status": "error", "error": "Hub is unreachable; try again shortly",
            })

    # ── AIMarket federation surface ───────────────────────────────────
    # LOGOS reads the hub with the crawler header, which the hub records as a knock. A
    # peer that knocks and publishes nothing is a `fail` forever; these three routes are
    # what make the knock honest. See logos/aimarket.py.

    def _protocol():
        proto = getattr(app.state, "aimarket", None)
        if proto is None:
            from logos.aimarket import build_protocol

            proto = build_protocol(app.state, cfg)
            app.state.aimarket = proto
        return proto

    @app.get("/.well-known/ai-market.json")
    async def ai_market_well_known():
        return _protocol().well_known()

    @app.get("/ai-market/v2/manifest")
    async def ai_market_manifest():
        return _protocol().manifest()

    @app.post("/ai-market/v2/invoke")
    async def ai_market_invoke(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        capability_id = str(body.get("capability_id") or "").strip()
        payload = body.get("input")
        try:
            return await _protocol().invoke(
                capability_id, payload if isinstance(payload, dict) else {},
            )
        except ValueError as exc:
            # Unknown capability — the caller's mistake, not ours, and the message names
            # only what they asked for.
            raise HTTPException(status_code=404, detail=str(exc)[:200])

    # ── A2A agent card ────────────────────────────────────────────────

    @app.get("/.well-known/agent-card.json")
    async def agent_card_endpoint():
        from logos.a2a import agent_card
        return agent_card(cfg.public_url)

    @app.post("/api/v1/a2a/tasks")
    async def a2a_tasks(request: Request):
        """A2A tasks endpoint — accepts analytics.ask skill delegations."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        skill = body.get("skill", "")
        if skill != "analytics.ask":
            raise HTTPException(status_code=400, detail=f"Unknown skill: {skill}")
        q = body.get("input", {}).get("query", "")
        if not q:
            raise HTTPException(status_code=400, detail="Missing query in task input")
        verdict = InputGuard().check(q)
        if verdict.action.value == "block":
            raise HTTPException(status_code=400, detail=f"Query blocked: {verdict.reason}")
        engine: AnalystEngine = app.state.engine
        resp = await engine.ask(AskRequest(query=q[:8000], max_insights=5))
        return {
            "status": "completed",
            "output": {
                "insights": [i.model_dump() for i in resp.insights],
                "interpreted_intent": resp.interpreted_intent.value,
            },
        }

    # ── AI assistant routes ─────────────────────────────────────────

    @app.post("/api/v1/chat")
    async def chat(req: ChatRequest):
        """Non-streaming chat with the LOGOS AI assistant."""
        assistant = LogosAssistant(
            store=app.state.store,
            config=AgentConfig.from_env(),
        )
        reply = await assistant.chat(req.message)
        return ChatResponse(reply=reply)

    @app.post("/api/v1/chat/stream")
    async def chat_stream(req: ChatRequest):
        """SSE-streaming chat with the LOGOS AI assistant."""
        assistant = LogosAssistant(
            store=app.state.store,
            config=AgentConfig.from_env(),
        )

        async def _stream():
            async for token in assistant.chat_stream(req.message):
                safe = token.replace("\n", " ").replace("\r", "")
                yield f"data: {safe}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


_MUTATING_CAPABILITY_TOKENS = frozenset({
    "delete", "remove", "drop", "write", "create", "update", "patch",
    "deploy", "remediate", "pay", "payout", "transfer", "withdraw",
    "deposit", "mint", "burn", "sign", "execute", "submit", "publish",
    "acknowledge", "trigger", "start", "stop", "restart", "rotate",
})


def _is_read_only_capability(capability_id: str) -> bool:
    """Conservative boundary for the public NEXUS proxy.

    Capability identifiers are dot/slash/dash separated in the federation.
    Unknown verbs are allowed for discovery compatibility, while explicit
    mutation verbs are refused before any network request is made.
    """
    import re
    tokens = {p for p in re.split(r"[^a-z0-9]+", capability_id.lower()) if p}
    return not bool(tokens & _MUTATING_CAPABILITY_TOKENS)


# ── background poll loop ──────────────────────────────────────────────────────

async def _poll_loop(
    store: LogosStore,
    engine: AnalystEngine,
    detector: AnomalyDetector,
    cfg: LogosConfig,
) -> None:
    """Periodically refresh federation data, detect anomalies, and generate
    the daily report at the configured hour."""
    last_report_date: str = ""

    while True:
        try:
            results = await engine.snapshot()
            hub = results.get("hub", {})
            momus = results.get("momus", {})
            treasury = results.get("treasury", {})

            merged = {**hub, "findings": momus, "treasury": treasury}
            store.save_snapshot(merged)

            # Detect anomalies — pass treasury for balance tracking
            new_anomalies = detector.ingest_snapshot(hub, momus, treasury)
            for a in new_anomalies:
                store.save_anomaly(a)

            # Telegram alerts for new anomalies (same bot as SKOPOS)
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
            for a in new_anomalies:
                if tg_token and tg_chat and a.severity.value in ("critical", "high"):
                    from logos.telegram import send_anomaly_alert
                    await send_anomaly_alert(
                        tg_token, tg_chat, a.metric, a.severity.value,
                        a.z_score, a.description, a.detected_at,
                    )
            if new_anomalies:
                logger.info("Detected %d new anomalies", len(new_anomalies))

            # Daily report at the configured hour
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            if now.hour == cfg.daily_report_hour and today != last_report_date:
                report = await engine.daily_report(
                    snapshot=hub, findings=momus,
                    remediation={}, treasury=treasury,
                    anomalies=store.get_anomalies(acknowledged=False),
                    recent_insights=store.recent_insights(10),
                )
                store.save_report(report)
                last_report_date = today
                logger.info("Generated daily report: %s", report.report_id)

                # Telegram daily report (same bot as SKOPOS)
                if tg_token and tg_chat:
                    from logos.telegram import send_daily_report
                    await send_daily_report(
                        tg_token, tg_chat,
                        report.summary,
                        [k.model_dump() for k in report.kpis],
                        len(report.anomalies),
                        report.overall_status,
                    )

            # Prune old snapshots beyond retention window (uses dual-dialect store method)
            try:
                store.prune_snapshots(cfg.snapshot_retention_days)
            except Exception:
                pass

        except Exception as exc:
            logger.warning("Poll cycle failed: %s", exc)

        await asyncio.sleep(cfg.poll_interval_s)
