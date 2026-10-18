"""Local teaching bridge: Hub envelope -> authenticated n8n -> signed result.

The adapter and n8n are loopback-only in this workshop. A public deployment needs
operator access controls and a reviewed data source; do not expose these lab ports.
"""
import hmac
import json
import os
from pathlib import Path

import httpx
import jsonschema
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import _bound_response_canonical

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "input-schema.json").read_text())
CAPABILITY = "store.order_check@v1"
PRODUCT = "workshop-store"


def create_app(*, state_dir=None, webhook_url=None, hub_token=None, webhook_token=None):
    state = Path(state_dir or ROOT / ".runtime")
    hub_token = hub_token or os.environ["AIMARKET_CAPABILITY_TOKEN"]
    webhook_token = webhook_token or os.environ["WORKSHOP_WEBHOOK_TOKEN"]
    webhook_url = webhook_url or "http://127.0.0.1:15678/webhook/aimarket-order-check"
    signer = Signer(state / "provider_key", pqc=False)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def health():
        return {"ok": True, "provider_pubkey": signer.public_key_b64}

    @app.post("/invoke")
    async def invoke(request: Request):
        if not hmac.compare_digest(request.headers.get("X-AIMarket-Internal-Token", ""), hub_token):
            raise HTTPException(401, "Hub authentication required")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16384:
                raise HTTPException(413, "Request too large")
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError
            if body.get("product_id") != PRODUCT or body.get("capability_id") != CAPABILITY:
                raise ValueError
            inp = body["input"]
            jsonschema.validate(inp, SCHEMA)
        except (ValueError, KeyError, jsonschema.ValidationError):
            raise HTTPException(422, "Invalid product, capability or cart") from None
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
                response = await client.post(webhook_url, json=inp,
                    headers={"X-Workshop-Key": webhook_token})
            if response.status_code == 422:
                raise HTTPException(422, "n8n rejected the cart")
            if response.status_code != 200 or len(response.content) > 65536:
                raise HTTPException(502, "n8n unavailable or response too large")
            result = response.json()
            if (not isinstance(result, dict) or result.get("kind") != "order_check"
                    or result.get("schema_version") != 1 or result.get("demo") is not True
                    or result.get("reservation_created") is not False
                    or result.get("order_created") is not False):
                raise HTTPException(502, "Unexpected n8n response; check workflow publication")
        except httpx.TimeoutException:
            raise HTTPException(504, "n8n timed out") from None
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "n8n unavailable or invalid JSON") from None
        signature = signer.sign_canonical(_bound_response_canonical(CAPABILITY, PRODUCT, inp, result))
        return JSONResponse({"success": True, "result": result},
                            headers={"X-Provider-Signature": signature})

    return app
