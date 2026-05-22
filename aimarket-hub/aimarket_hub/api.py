"""Hub API — FastAPI application exposing federation endpoints.

Core routes: .well-known, manifest (v2), federated search, routing proxy,
federation announce, peers list, stats, plugin catalog.

Plugins extend the hub via entry points — they register their own routes
and hook into the invoke pipeline (pre/post checks). See plugin.py.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aimarket_hub.channels import close_channel, open_channel
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.demo_seeder import seed_demo_capabilities
from aimarket_hub.models import InvocationStat, Peer
from aimarket_hub.plugin import PluginRegistry
from aimarket_hub.safety_gate import SafetyGate, default_safety_gate
from aimarket_hub.signing import Signer
from aimarket_hub.trust import TrustScorer


# ── Pydantic models ────────────────────────────────────────────


class SearchRequest(BaseModel):
    intent: str = Field("", max_length=4000)
    budget: Optional[float] = Field(None, ge=0, le=100_000)
    max_latency_ms: Optional[int] = Field(None, ge=0)
    min_trust: Optional[float] = Field(None, ge=0, le=1)
    hub: str = Field("any", max_length=256)
    limit: int = Field(20, ge=1, le=100)


class InvokeRequest(BaseModel):
    product_id: str = Field(..., min_length=2, max_length=80)
    capability_id: str = Field(..., min_length=2, max_length=80)
    source_hub: str = Field("local", max_length=256)
    input: dict[str, Any] = Field(default_factory=dict)


class AnnounceRequest(BaseModel):
    hub_url: str = Field(..., max_length=256)
    well_known_url: str = Field(..., max_length=256)
    capabilities_count: int = Field(0, ge=0)
    hub_name: str = Field("", max_length=128)
    signer_public_key: str = Field("", max_length=128)
    signature: Optional[dict[str, str]] = None


class ReputationEventsRequest(BaseModel):
    events: list[dict[str, Any]] = Field(..., min_length=1, max_length=100)


class ChannelOpenRequest(BaseModel):
    deposit_usd: float = Field(..., gt=0, le=10_000)
    token: Optional[str] = Field(None, max_length=16)
    chain: Optional[str] = Field(None, max_length=32)
    wallet: str = Field("", max_length=128)
    tx_hash: str = Field("", max_length=128)


class ChannelCloseRequest(BaseModel):
    channel_id: str = Field(..., min_length=8, max_length=64)
    settle_tx_hash: str = Field("", max_length=128)


# ── Router factory ─────────────────────────────────────────────


def create_app(
    config: HubConfig | None = None,
    db: HubDatabase | None = None,
    signer: Signer | None = None,
    trust_scorer: TrustScorer | None = None,
    plugins: PluginRegistry | None = None,
) -> FastAPI:
    """Create the hub FastAPI app.

    Args:
        config: Hub configuration
        db: Hub database
        signer: Ed25519 signer
        trust_scorer: Trust score computer
        plugins: Plugin registry (auto-discovers from entry_points if None)
    """
    config = config or HubConfig()
    db = db or HubDatabase(config.db_path)
    signer = signer or Signer(config.signing_key_path)
    trust_scorer = trust_scorer or TrustScorer(db)
    builtin_safety = default_safety_gate()  # Built-in fallback

    # Seed demo capabilities on first startup
    seeded = seed_demo_capabilities(db)
    if seeded:
        import logging
        logging.getLogger(__name__).info("Seeded %d demo capabilities", seeded)

    # Import real products from AI-Factory if bridge is available
    try:
        from aimarket_hub.factory_bridge import import_factory_products
        real = import_factory_products(db)
        if real:
            import logging
            logging.getLogger(__name__).info("Imported %d real factory products", real)
    except Exception:
        pass

    # Plugin discovery
    if plugins is None:
        plugins = PluginRegistry()
        plugins.discover(db)
        plugins.startup_all(db)

    app = FastAPI(
        title=f"{config.hub_name} — AIMarket Hub v3",
        version="3.0.0",
        description="Lean federation hub for AI capability discovery and routing. Plugins extend functionality.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach plugin registry to app state
    app.state.plugins = plugins

    router = APIRouter(prefix="/ai-market/v2", tags=["hub-v2"])
    wellknown_router = APIRouter(tags=["wellknown"])

    # ── .well-known ────────────────────────────────────────────

    @wellknown_router.get("/.well-known/ai-market.json")
    async def well_known():
        peers = []
        for p in db.list_peers():
            peers.append({
                "url": p.url,
                "name": p.name,
                "capabilities_count": p.capabilities_count,
                "last_crawl": p.last_crawl,
                "trust_score": p.trust_score,
            })

        wk = {
            "name": config.hub_name,
            "protocol_versions": ["v1", "v2"],
            "hub_version": "3.0.0",
            "mcp_endpoint": f"{config.hub_url}/ai-market/mcp",
            "manifest_url": f"{config.hub_url}/ai-market/v2/manifest",
            "products_count": db.count_capabilities("local"),
            "capabilities_count": db.count_capabilities("local"),
            "federated_capabilities_count": db.count_capabilities(),
            "supported_chains": [config.payment_chain],
            "supported_tokens": [config.payment_token],
            "payment_recipient": config.payment_recipient if not config.payment_verify_stub else "demo-mode (stub verification)",
            "payment_testnet": config.payment_testnet,
            "signer_public_key": signer.public_key_b64,
            "federation": {
                "crawl_interval_s": config.crawl_interval_s,
                "routing_fee_bps": config.routing_fee_bps,
                "min_trust_score": config.min_trust_score,
                "seed_list": config.seed_list,
            },
            "peers": peers,
            "plugins_loaded": plugins.count(),
            "demo_mode": db.count_capabilities("local") > 0 and all(
                "[DEMO]" in (c.description or "") for c in db.list_capabilities("local", limit=100)
            ),
        }

        # Merge plugin manifest extensions
        plugin_ext = plugins.get_manifest_extensions()
        if plugin_ext:
            wk["plugin_extensions"] = plugin_ext

        return wk

    # ── Manifest ────────────────────────────────────────────────

    @router.get("/manifest")
    async def v2_manifest():
        caps = db.list_capabilities(limit=1000)
        tools = []
        for c in caps:
            tools.append({
                "name": c.tool_name(),
                "description": c.description,
                "input_schema": c.input_schema,
                "output_schema": c.output_schema,
                "price_per_call_usd": c.price_per_call_usd,
                "p50_latency_ms": c.p50_latency_ms,
                "success_rate_30d": c.success_rate_30d,
                "product_id": c.product_id,
                "capability_id": c.capability_id,
                "source_hub": c.source_hub,
                "source_hub_name": c.source_hub_name,
                "routed_price_usd": c.routed_price_usd,
                "routing_fee_bps": c.routing_fee_bps,
                "trust_score": c.trust_score,
            })

        by_hub: dict[str, dict[str, Any]] = {}
        for p in db.list_peers():
            by_hub[p.url] = {
                "capabilities_count": p.capabilities_count,
                "trust_score": p.trust_score,
                "last_crawl": p.last_crawl,
            }
        by_hub["local"] = {
            "capabilities_count": db.count_capabilities("local"),
            "trust_score": 1.0,
            "last_crawl": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        manifest_body = {
            "protocol_version": "v2",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "base_url": config.hub_url,
            "total_capabilities": len(caps),
            "local_capabilities": db.count_capabilities("local"),
            "federated_capabilities": db.count_federated(),
            "hubs_indexed": db.peer_count(),
            "tools": tools,
            "by_hub": by_hub,
        }
        manifest_body["signature"] = signer.sign_manifest(manifest_body)
        return manifest_body

    # ── Search ──────────────────────────────────────────────────

    @router.get("/search")
    async def search(
        intent: str = "",
        budget: Optional[float] = None,
        max_latency_ms: Optional[int] = None,
        min_trust: Optional[float] = None,
        hub: str = "any",
        limit: int = 20,
    ):
        limit = min(limit, 100)
        results = db.search_capabilities(intent, limit=limit * 2)

        filtered: list[dict[str, Any]] = []
        for cap in results:
            if hub != "any" and cap.source_hub != hub:
                continue
            if min_trust is not None and cap.trust_score < min_trust:
                continue
            if max_latency_ms is not None and cap.p50_latency_ms > max_latency_ms:
                continue
            routed = cap.routed_price_usd or cap.price_per_call_usd
            if budget is not None and routed > budget:
                continue
            filtered.append({
                "product_id": cap.product_id,
                "capability_id": cap.capability_id,
                "source_hub": cap.source_hub,
                "source_hub_name": cap.source_hub_name,
                "name": cap.name,
                "description": cap.description,
                "score": 0.8,
                "price_per_call_usd": cap.price_per_call_usd,
                "routed_price_usd": routed,
                "routing_fee_bps": cap.routing_fee_bps,
                "trust_score": cap.trust_score,
                "p50_latency_ms": cap.p50_latency_ms,
            })
            if len(filtered) >= limit:
                break

        return {
            "query": intent,
            "matches": filtered,
            "total_hubs_searched": db.peer_count() + 1,
            "protocol_version": "v2",
        }

    # ── Invoke (plugin-gated) ───────────────────────────────────

    @router.post("/invoke")
    async def invoke(
        body: InvokeRequest,
        request: Request,
        x_payment_channel: Optional[str] = Header(default=None, alias="X-Payment-Channel"),
        x_aimarket_route_ok: Optional[str] = Header(default=None, alias="X-AIMarket-Route-Ok"),
    ):
        if body.source_hub == "local":
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
                try:
                    rejection_receipt["signature"] = signer.sign_receipt(rejection_receipt)
                except Exception:
                    pass
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

            # ── Execute ─────────────────────────────────────────
            t0 = time.time()
            # Try real factory backend first, fall back to demo stub
            factory_url = os.environ.get("AIFACTORY_PUBLIC_URL", "")
            cap = db.get_capability(body.product_id, body.capability_id)
            is_demo = cap and "[DEMO]" in (cap.description or "")

            if factory_url and not is_demo:
                try:
                    async with httpx.AsyncClient(timeout=30) as fc:
                        fr = await fc.post(
                            f"{factory_url}/capabilities/{body.product_id}/{body.capability_id}/invoke",
                            json={"input": body.input},
                            headers={"X-Payment-Channel": x_payment_channel or ""},
                        )
                        if fr.status_code == 200:
                            result = fr.json()
                        else:
                            result = {"output": f"Factory returned {fr.status_code}: {fr.text[:200]}"}
                except Exception:
                    result = {"output": f"[DEMO] Executed {body.capability_id} (factory unreachable)"}
            else:
                demo_note = " [DEMO]" if is_demo else ""
                result = {"output": f"[DEMO] Executed {body.capability_id} locally{demo_note}"}
            elapsed_ms = int((time.time() - t0) * 1000)

            # ── Post-check: plugins first, then built-in ────────
            post_block = plugins.run_post_checks(result, {
                "product_id": body.product_id,
                "capability_id": body.capability_id,
            })
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

            receipt = signer.sign_receipt({
                "nonce": f"rcpt_{int(time.time())}",
                "product_id": body.product_id,
                "capability_id": body.capability_id,
                "price_usd": 0.40,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })

            stat = InvocationStat(
                capability_id=body.capability_id,
                product_id=body.product_id,
                source_hub="local",
                price_usd=0.40,
                latency_ms=elapsed_ms,
                success=True,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                consumer_hub=config.hub_url,
            )
            db.record_invocation(stat)

            return JSONResponse(status_code=200, content={
                "success": True,
                "result": result,
                "receipt": receipt,
                "price_usd": 0.40,
                "latency_ms": elapsed_ms,
                "safety_checked": True,
                "plugins_checked": plugins.count(),
                "protocol_version": "v2",
            })

        # Federated invoke — route to provider hub
        peer = db.get_peer(body.source_hub)
        if not peer:
            raise HTTPException(status_code=404, detail="Peer hub not found")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                provider_url = f"{peer.url}/capabilities/{body.product_id}/{body.capability_id}/invoke"
                headers: dict[str, str] = {
                    "X-AIMarket-Routing-Hub": config.hub_url,
                    "X-AIMarket-Routing-Fee": str(config.routing_fee_bps),
                }
                if x_payment_channel:
                    headers["X-Payment-Channel"] = x_payment_channel
                resp = await client.post(provider_url, json=body.input, headers=headers)
                if resp.status_code == 402:
                    return JSONResponse(status_code=402, content=resp.json())
                if resp.status_code >= 400:
                    raise HTTPException(status_code=502, detail=f"Provider returned {resp.status_code}")

                result_data = resp.json()
                stat = InvocationStat(
                    capability_id=body.capability_id,
                    product_id=body.product_id,
                    source_hub=body.source_hub,
                    price_usd=result_data.get("price_usd", 0),
                    latency_ms=result_data.get("latency_ms", 0),
                    success=result_data.get("success", False),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    consumer_hub=config.hub_url,
                )
                db.record_invocation(stat)
                result_data["routed_via"] = config.hub_url
                result_data["routing_fee_bps"] = config.routing_fee_bps
                return result_data

        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Provider unreachable: {exc}")

    # ── Federation ──────────────────────────────────────────────

    @router.post("/federation/announce")
    async def federation_announce(body: AnnounceRequest):
        peer = Peer(
            url=body.hub_url,
            name=body.hub_name or body.hub_url,
            capabilities_count=body.capabilities_count,
            last_crawl=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            well_known_url=body.well_known_url,
            public_key=body.signer_public_key,
            depth=1,
            discoverer="announce",
        )
        db.upsert_peer(peer)
        return {"acknowledged": True, "peer_added": True}

    @router.get("/federation/peers")
    async def list_peers():
        peers = db.list_peers()
        return {
            "peers": [
                {"url": p.url, "name": p.name, "capabilities_count": p.capabilities_count,
                 "last_crawl": p.last_crawl, "trust_score": p.trust_score, "depth": p.depth}
                for p in peers
            ],
            "count": len(peers),
        }

    @router.post("/federation/crawl")
    async def trigger_crawl():
        from aimarket_hub.crawler import Crawler
        crawler = Crawler(config=config, db=db, signer=signer, trust_scorer=trust_scorer)
        try:
            stats = await crawler.crawl(clear_first=True)
        finally:
            await crawler.close()
        return {"status": "complete", "stats": stats}

    # ── Reputation ──────────────────────────────────────────────

    @router.get("/reputation/{hub_url:path}")
    async def get_reputation(hub_url: str):
        score = trust_scorer.compute_score(hub_url)
        details = trust_scorer.score_details(hub_url)
        events = db.reputation_events_for(hub_url, limit=20)
        return {
            "hub_url": hub_url,
            "trust_score": score,
            "details": details,
            "recent_events": [
                {"type": e.event_type, "timestamp": e.timestamp,
                 "price_usd": e.price_usd, "latency_ms": e.latency_ms}
                for e in events
            ],
        }

    @router.post("/reputation/events")
    async def submit_reputation_events(body: ReputationEventsRequest):
        from aimarket_hub.models import ReputationEvent
        for ev in body.events:
            db.record_reputation_event(ReputationEvent(
                event_type=ev.get("type", "unknown"),
                provider_hub=ev.get("provider_hub", ""),
                capability_id=ev.get("capability_id"),
                timestamp=ev.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                price_usd=ev.get("price_usd", 0),
                latency_ms=ev.get("latency_ms", 0),
                consumer_hub=ev.get("consumer_hub", config.hub_url),
                signature=json.dumps(ev.get("signature") or {}),
            ))
        return {"received": len(body.events)}

    @router.get("/stats/live")
    async def live_stats(limit: int = 50):
        stats = db.recent_stats(limit=min(limit, 200))
        summary = db.stats_summary()
        return {"events": stats, "summary": summary, "protocol_version": "v2"}

    # ── Payment Channels ────────────────────────────────────────

    @router.post("/channel/open")
    async def channel_open(body: ChannelOpenRequest):
        result = open_channel(
            deposit_usd=body.deposit_usd,
            token=body.token,
            chain=body.chain,
            wallet=body.wallet,
            tx_hash=body.tx_hash,
        )
        if result.get("error"):
            return JSONResponse(status_code=400, content=result)
        return result

    @router.post("/channel/close")
    async def channel_close(body: ChannelCloseRequest):
        result = close_channel(
            channel_id=body.channel_id,
            settle_tx_hash=body.settle_tx_hash,
        )
        if result.get("error"):
            return JSONResponse(status_code=400, content=result)
        return result

    # ── Plugin Catalog (the marketplace) ───────────────────────

    @router.get("/plugins")
    async def list_plugins():
        """List all loaded plugins."""
        return {
            "plugins": plugins.list_plugins(),
            "count": plugins.count(),
            "discovery": "Plugins are auto-discovered via setuptools entry_points (group: aimarket.plugins)",
            "registry_url": f"{config.hub_url}/ai-market/v2/plugins/registry",
        }

    @router.get("/plugins/registry")
    async def plugin_registry():
        """Serve the static curated plugin registry."""
        import os as _os
        registry_path = _os.path.join(_os.path.dirname(__file__), "..", "plugins.json")
        if _os.path.isfile(registry_path):
            with open(registry_path) as f:
                return json.load(f)
        return {"registry_version": "1.0", "plugins": [], "note": "No plugins.json found. Add plugins via PR to the curated registry."}

    @router.get("/plugins/{plugin_name}")
    async def plugin_detail(plugin_name: str):
        """Get details about a specific loaded plugin."""
        plugin = plugins.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not loaded")
        return plugin.plugin_info()

    # ── Register routes ─────────────────────────────────────────

    # Register plugin routes under /ai-market/v2/p/{name}/...
    for p in plugins.plugins:
        if p._list_hooks() and "register_routes" in [h for h in p._list_hooks()]:
            plugin_router = APIRouter(prefix=f"/p/{p.name}", tags=[f"plugin-{p.name}"])
            p.register_routes(plugin_router)
            app.include_router(plugin_router)

    app.include_router(wellknown_router)
    app.include_router(router)

    # ── Landing page & Integration Examples ──────────────────

    from aimarket_hub.landing import INTEGRATION_EXAMPLES_HTML, LANDING_HTML

    @app.get("/", response_class=HTMLResponse)
    async def landing_page():
        return HTMLResponse(LANDING_HTML)

    @app.get("/examples", response_class=HTMLResponse)
    async def integration_examples():
        return HTMLResponse(INTEGRATION_EXAMPLES_HTML)

    # ── Widget & Live Stream static serving ─────────────────────

    # Resolve widget dir — handles both repo layout (../../aimarket-widget)
    # and Docker layout (../aimarket-widget).
    widget_dir = None
    for candidate in (
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aimarket-widget")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "aimarket-widget")),
        "/app/aimarket-widget",
    ):
        if os.path.isdir(candidate):
            widget_dir = candidate
            break

    @app.get("/widget/demo", response_class=HTMLResponse)
    async def widget_demo():
        demo_html = os.path.join(widget_dir, "demo.html") if widget_dir else None
        if demo_html and os.path.isfile(demo_html):
            return HTMLResponse(open(demo_html).read())
        return HTMLResponse("<h1>Widget demo not found</h1>", status_code=404)

    @app.get("/live", response_class=HTMLResponse)
    async def live_economy_stream():
        live_html = os.path.join(widget_dir, "live-stream.html") if widget_dir else None
        if live_html and os.path.isfile(live_html):
            return HTMLResponse(open(live_html).read())
        return HTMLResponse("<h1>Live stream not found</h1>", status_code=404)

    if widget_dir:
        app.mount("/widget", StaticFiles(directory=widget_dir, html=True), name="widget")

    return app
