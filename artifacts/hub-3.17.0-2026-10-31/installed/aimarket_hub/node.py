"""`aimarket node`: make a service you already run a node of the federation.

A seller with an API — an x402 route, a REST endpoint — should not have to run a whole hub to
be found by one. The only outside member of the federation as of 2026-10-12 (Industrial
Sentinel) had hand-written the three documents this serves; nobody else had, and there was no
kit to do it with. This is that kit: a small process beside the API, configured by one TOML
file, that

* publishes a signed `/.well-known/ai-market.json` and a signed manifest of the capabilities
  you name (signed fresh on every read, so it never goes stale);
* answers `POST /ai-market/v2/invoke` by calling YOUR route — GET with the input as query
  parameters, or POST with it as JSON — passing x402 payment headers through in both
  directions, so a 402 from your route reaches the buyer (and the admission sandbox) as-is
  and a paid retry reaches your route with its payment;
* signs a receipt for every answer your route gives with 2xx.

Payment stays yours: the node never holds, verifies or moves money. Your route keeps doing
that exactly as it does today; the node only says, under its own key, what came back.

The crypto is the hub's own (`signing.Signer`), so what this serves is checked by the same
code that admits peers. `aimarket doctor --url <node url>` runs that check before you knock.
"""

from __future__ import annotations

import time
import tomllib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aimarket_hub import __version__

#: Request headers carrying a buyer's payment to your route (x402 V1 and V2, and the hub's own).
PAYMENT_REQUEST_PREFIXES = ("payment-", "x-payment")
#: Response headers carrying your route's offer or settlement back to the buyer.
PAYMENT_RESPONSE_HEADERS = ("payment-required", "payment-response", "x-payment-response")
#: An upstream answer is buffered to sign it; bound it.
MAX_UPSTREAM_BYTES = 1_048_576

TEMPLATE = '''# aimarket node — one file describes the node. Docs: docs/run-a-node.md
name = "Your service"                    # public name; not "AIMarket"
url = "https://api.example.com"          # where other hubs reach this node (https, public)
upstream = "http://127.0.0.1:8000"       # where your existing API listens
# description = "What you sell, in one sentence"
# key_path = "data/node_signing_key"     # the node's identity — back it up

[[capability]]
id = "weather.now@v1"                    # name.verb@v1
product = "example-weather"
name = "Weather now"
description = "Current weather for a city"
price_usd = 0.002                        # 0 = free; must equal what your route's 402 asks
method = "GET"                           # GET: input -> query string; POST: input -> JSON body
path = "/weather"                        # your route on upstream
input_schema = { type = "object", required = ["city"], properties = { city = { type = "string" } } }
# provider_pubkey = "…"                  # optional: the Ed25519 key your service signs answers and
                                         # receipts with (base64, 32 bytes); hubs tie buyers' signed
                                         # delivery receipts to this listing by it
'''


@dataclass
class Capability:
    id: str
    product: str
    name: str
    description: str
    price_usd: float
    method: str
    path: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    #: The key the service behind this node signs its answers and delivery receipts with.
    provider_pubkey: str = ""


def _pubkey(raw: Any, cid: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    import base64
    try:
        ok = len(base64.b64decode(text, validate=True)) == 32
    except Exception:
        ok = False
    if not ok:
        raise ValueError(f"capability {cid}: provider_pubkey must be a base64 Ed25519 public key (32 bytes)")
    return text


@dataclass
class NodeConfig:
    name: str
    url: str
    upstream: str
    capabilities: list[Capability]
    description: str = ""
    key_path: str = "data/node_signing_key"


def load(path: str | Path) -> NodeConfig:
    """Read and check node.toml. Raises ValueError naming what is wrong."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    name = str(raw.get("name") or "").strip()
    url = str(raw.get("url") or "").strip().rstrip("/")
    upstream = str(raw.get("upstream") or "").strip().rstrip("/")
    if not name:
        raise ValueError("name is required")
    for label, value in (("url", url), ("upstream", upstream)):
        if not value.startswith(("http://", "https://")):
            raise ValueError(f"{label} must be an http(s) URL")
    caps: list[Capability] = []
    seen: set[tuple[str, str]] = set()
    for i, item in enumerate(raw.get("capability") or [], 1):
        cid = str(item.get("id") or "").strip()
        if "@v" not in cid:
            raise ValueError(f"capability {i}: id must look like name.verb@v1")
        method = str(item.get("method") or "POST").upper()
        if method not in ("GET", "POST"):
            raise ValueError(f"capability {cid}: method must be GET or POST")
        route = str(item.get("path") or "").strip()
        if not route.startswith("/"):
            raise ValueError(f"capability {cid}: path must start with /")
        price = float(item.get("price_usd") or 0.0)
        if price < 0 or price != price:
            raise ValueError(f"capability {cid}: price_usd must be >= 0")
        product = str(item.get("product") or cid.split("@", 1)[0].split(".", 1)[0]).strip()
        if (product, cid) in seen:
            raise ValueError(f"capability {cid} is listed twice")
        seen.add((product, cid))
        caps.append(Capability(
            id=cid, product=product, name=str(item.get("name") or cid.split("@", 1)[0]),
            description=str(item.get("description") or ""), price_usd=price, method=method,
            path=route, input_schema=dict(item.get("input_schema") or {"type": "object"}),
            output_schema=dict(item.get("output_schema") or {}),
            provider_pubkey=_pubkey(item.get("provider_pubkey"), cid),
        ))
    if not caps:
        raise ValueError("at least one [[capability]] is required")
    return NodeConfig(
        name=name, url=url, upstream=upstream, capabilities=caps,
        description=str(raw.get("description") or ""),
        key_path=str(raw.get("key_path") or "data/node_signing_key"),
    )


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def well_known(cfg: NodeConfig, signer: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": cfg.name,
        "description": cfg.description,
        "protocol_versions": ["v2"],
        "node_version": f"aimarket-node {__version__}",
        "manifest_url": f"{cfg.url}/ai-market/v2/manifest",
        # Where a hub routes a buyer's call. A hub reads `mcp_endpoint` for a peer that is not
        # itself a hub, and without it falls back to /capabilities/{product}/{cap}/invoke —
        # which this node also answers, but the envelope route is the one to name.
        "mcp_endpoint": f"{cfg.url}/ai-market/v2/invoke",
        # Buyers pay the seller's own route directly; a hub that relays such a sale takes no
        # routing fee on it (hub api.py, `fed_direct_x402`).
        "payment_rails": {"seller_direct": {
            "enabled": True,
            "note": "x402 on the seller's own route, passed through unchanged; this node never holds money",
        }},
        "capabilities_count": len(cfg.capabilities),
        "signer_public_key": signer.public_key_b64,
        "generated_at": _now(),
    }
    doc["signature"] = signer.sign_object(doc)
    return doc


def manifest(cfg: NodeConfig, signer: Any) -> dict[str, Any]:
    tools = []
    for cap in cfg.capabilities:
        tool = {
            "capability_id": cap.id,
            "product_id": cap.product,
            "name": cap.name,
            "description": cap.description,
            "input_schema": cap.input_schema,
            "price_per_call_usd": cap.price_usd,
            "access_mode": "paid" if cap.price_usd > 0 else "public_free",
        }
        if cap.output_schema:
            tool["output_schema"] = cap.output_schema
        if cap.provider_pubkey:
            tool["provider_pubkey"] = cap.provider_pubkey
        tools.append(tool)
    doc: dict[str, Any] = {
        "protocol_version": "v2",
        "generated_at": _now(),
        "capabilities_count": len(tools),
        "tools": tools,
    }
    doc["signature"] = signer.sign_manifest(doc)
    return doc


def _forward_request(cap: Capability, cfg: NodeConfig, data: Any,
                     incoming: dict[str, str]) -> dict[str, Any]:
    headers = {k: v for k, v in incoming.items() if k.lower().startswith(PAYMENT_REQUEST_PREFIXES)}
    url = f"{cfg.upstream}{cap.path}"
    if cap.method == "GET":
        if not isinstance(data, dict) or any(isinstance(v, (dict, list)) for v in data.values()):
            raise ValueError("a GET capability takes a flat object of query parameters")
        return {"method": "GET", "url": url, "params": data, "headers": headers}
    return {"method": "POST", "url": url, "json": data, "headers": headers}


def create_app(cfg: NodeConfig, signer: Any | None = None, transport: Any | None = None):
    """The node's ASGI app. `transport` is for tests (an httpx transport to the upstream)."""
    # FastAPI resolves `request: Request` from module globals (this file uses postponed
    # annotations), which is why those imports sit at the top and not here.
    from aimarket_hub.signing import Signer

    signer = signer or Signer(cfg.key_path)
    by_id = {(c.product, c.id): c for c in cfg.capabilities}
    by_cap = {c.id: c for c in cfg.capabilities}
    app = FastAPI(title=f"{cfg.name} — AIMarket node", docs_url=None, redoc_url=None)

    @app.get("/.well-known/ai-market.json")
    async def _well_known():
        return well_known(cfg, signer)

    @app.get("/ai-market/v2/manifest")
    async def _manifest():
        return manifest(cfg, signer)

    @app.get("/ai-market/v2/health")
    async def _health():
        return {"status": "ok", "node": cfg.name, "capabilities": len(cfg.capabilities)}

    @app.post("/capabilities/{product_id}/{capability_id}/invoke")
    async def _legacy_invoke(product_id: str, capability_id: str, request: Request):
        """The path a hub uses for a peer that names no endpoint: the bare input as the body."""
        try:
            data = await request.json()
        except ValueError:
            return JSONResponse({"success": False, "error": "invalid_json"}, status_code=400)
        return await _serve(product_id, capability_id, data if isinstance(data, dict) else {},
                            request)

    @app.post("/ai-market/v2/invoke")
    async def _invoke(request: Request):
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"success": False, "error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"success": False, "error": "invalid_body"}, status_code=400)
        return await _serve(str(body.get("product_id") or ""), str(body.get("capability_id") or ""),
                            body.get("input") or {}, request)

    async def _serve(product_id: str, cid: str, data: Any, request: Request):
        cap = by_id.get((product_id, cid)) or by_cap.get(cid)
        if cap is None:
            return JSONResponse({"success": False, "error": "unknown_capability",
                                 "detail": f"{cid} is not served by this node"}, status_code=404)
        try:
            req = _forward_request(cap, cfg, data, dict(request.headers))
        except ValueError as exc:
            return JSONResponse({"success": False, "error": "invalid_input", "detail": str(exc)},
                                status_code=400)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False,
                                         transport=transport) as client:
                upstream = await client.request(**req)
        except httpx.HTTPError as exc:
            return JSONResponse({"success": False, "error": "upstream_unreachable",
                                 "detail": type(exc).__name__}, status_code=502)
        latency_ms = int((time.monotonic() - started) * 1000)
        passed = {k: v for k, v in upstream.headers.items() if k.lower() in PAYMENT_RESPONSE_HEADERS}
        if len(upstream.content) > MAX_UPSTREAM_BYTES:
            return JSONResponse({"success": False, "error": "upstream_too_large"}, status_code=502)
        try:
            payload = upstream.json() if upstream.content else {}
        except ValueError:
            payload = {"text": upstream.text}
        if upstream.status_code == 402:
            # Your route's door, as it is: the offer travels in the body (x402 V1) or in
            # PAYMENT-REQUIRED (V2), and both reach the buyer unchanged.
            return JSONResponse(payload if isinstance(payload, dict) else {},
                                status_code=402, headers=passed)
        if not 200 <= upstream.status_code < 300:
            return JSONResponse({"success": False, "error": "upstream_error",
                                 "status": upstream.status_code}, status_code=502)
        paid = any(k.lower().startswith(PAYMENT_REQUEST_PREFIXES) for k in req["headers"])
        receipt: dict[str, Any] = {
            "nonce": f"rcpt_{uuid.uuid4().hex}",
            "product_id": cap.product,
            "capability_id": cap.id,
            "price_usd": cap.price_usd if paid else 0.0,
            "timestamp": _now(),
            "success": True,
            "latency_ms": latency_ms,
        }
        receipt["signature"] = signer.sign_receipt(receipt)
        return JSONResponse({"success": True, "result": payload, "receipt": receipt},
                            headers=passed)

    return app


def knock(cfg: NodeConfig, hub: str = "https://modelmarket.dev", timeout: float = 30) -> dict:
    """Announce this node to a hub; the answer carries `assay_url`, where the verdict appears."""
    resp = httpx.post(
        f"{hub.rstrip('/')}/ai-market/v2/federation/announce",
        json={"hub_url": cfg.url, "hub_name": cfg.name},
        timeout=timeout,
    )
    try:
        return resp.json()
    except ValueError:
        return {"status_code": resp.status_code, "text": resp.text[:300]}
