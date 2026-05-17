"""
AI Market Protocol API (production pilot)
=========================================
Discovery + on-chain settlement confirmation + entitlement activation.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException

from core.paths import (
    ai_market_integrations_log_path,
    pipeline_json_path,
    store_licenses_path,
)
from web.backend.api import payment as payment_api
from web.backend.schemas.api_requests import (
    AiMarketCapabilityInvokeRequest,
    AiMarketSearchRequest,
    AiMarketSettlementConfirmRequest,
)
from web.backend.services.commerce import CommerceService

router = APIRouter(prefix="/ai-market", tags=["ai-market"])
commerce = CommerceService()


def _pilot_config() -> dict[str, str]:
    chain = os.environ.get("AIFACTORY_AI_MARKET_CHAIN", "base").strip().lower() or "base"
    token = os.environ.get("AIFACTORY_AI_MARKET_TOKEN", "USDT").strip().upper() or "USDT"
    contract = os.environ.get("AIFACTORY_AI_MARKET_CONTRACT", "").strip()
    return {
        "chain": chain,
        "token": token,
        "contract": contract,
        "entitlement_ttl_days": str(int(os.environ.get("AIFACTORY_AI_MARKET_ENTITLEMENT_DAYS", "30"))),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def _fanout_external_integrations(event: dict[str, Any]) -> list[dict[str, Any]]:
    urls = [
        os.environ.get("AIFACTORY_AI_MARKET_WEBHOOK_1", "").strip(),
        os.environ.get("AIFACTORY_AI_MARKET_WEBHOOK_2", "").strip(),
    ]
    urls = [u for u in urls if u]
    results: list[dict[str, Any]] = []
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json=event)
            results.append({"url": url, "status_code": resp.status_code, "ok": resp.status_code < 300})
        except Exception as exc:
            results.append({"url": url, "ok": False, "error": str(exc)})
    _append_jsonl(
        ai_market_integrations_log_path(),
        {"time": time.time(), "event": event, "results": results},
    )
    return results


def _read_pipeline_products() -> dict[str, Any]:
    p = pipeline_json_path()
    if not p.exists():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    products = j.get("products") if isinstance(j, dict) else {}
    return products if isinstance(products, dict) else {}


@router.get("/products")
async def list_products():
    products = _read_pipeline_products()
    out: list[dict[str, Any]] = []
    for pid, p in products.items():
        state = str((p or {}).get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue
        out.append(
            {
                "id": pid,
                "name": str((p or {}).get("name") or f"Product {pid[:8]}"),
                "description": str((p or {}).get("idea") or ""),
                "category": str((p or {}).get("category") or "uncategorized"),
                "tags": (p or {}).get("tags") or [],
                "capabilities": [],
                "pricing": {},
                "license": {},
                "quality": {},
                "crypto_support": {"pilot_enabled": True, **_pilot_config()},
            }
        )
    return {"products": out, "count": len(out), "protocol_version": "v0"}


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    products = _read_pipeline_products()
    p = products.get(product_id) or {}
    return {
        "product": {
            "id": product_id,
            "name": str(p.get("name") or f"Product {product_id[:8]}"),
            "description": str(p.get("idea") or ""),
            "category": str(p.get("category") or "uncategorized"),
            "tags": p.get("tags") or [],
            "capabilities": [],
            "pricing": {},
            "license": {},
            "quality": {},
            "crypto_support": {"pilot_enabled": True, **_pilot_config()},
        },
        "protocol_version": "v0",
    }


@router.post("/products/search")
async def search_products(body: AiMarketSearchRequest):
    products = _read_pipeline_products()
    query = body.task_description.lower()
    out: list[dict[str, Any]] = []
    for pid, p in products.items():
        state = str((p or {}).get("state") or "").upper()
        if state not in {"COMPLETED", "DEPLOYED_PRODUCTION"}:
            continue
        idea = str((p or {}).get("idea") or "")
        score = 0.0
        if query and query in idea.lower():
            score = 0.95
        elif query:
            tokens = [x for x in query.split() if x]
            hits = sum(1 for t in tokens if t in idea.lower())
            score = hits / max(1, len(tokens))
        if score > 0:
            out.append({"product_id": pid, "score": round(score, 3), "reasoning": ["keyword_match"]})
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"matches": out[:20], "protocol_version": "v0"}


@router.get("/pilot/config")
async def get_pilot_config():
    cfg = _pilot_config()
    return {"pilot": {"enabled": True, **cfg}, "protocol_version": "v0"}


@router.post("/pilot/settlement/confirm")
async def confirm_pilot_settlement(body: AiMarketSettlementConfirmRequest):
    """
    Production pilot: single chain/token/contract settlement confirmation.
    On success creates order + license entitlement.
    """
    cfg = _pilot_config()
    chain = (body.chain or cfg["chain"]).strip().lower()
    token = (body.token or cfg["token"]).strip().upper()
    contract = (body.contract_address or "").strip()
    product_id = body.product_id
    tx_hash = body.tx_hash
    customer_id = body.customer_id or f"aimkt-{uuid.uuid4().hex[:8]}"
    customer_email = body.customer_email or f"{customer_id}@ai-market.local"
    wallet = body.wallet_address or ""
    amount = body.amount
    if chain != cfg["chain"] or token != cfg["token"]:
        raise HTTPException(status_code=400, detail=f"pilot supports only {cfg['chain']} + {cfg['token']}")
    if cfg["contract"] and contract.lower() != cfg["contract"].lower():
        raise HTTPException(status_code=400, detail="contract_address does not match pilot contract")
    recipient = payment_api._get_address_for_chain(chain)
    if chain == "solana":
        verify = payment_api._verify_solana_transaction(
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount,
        )
    else:
        verify = payment_api._verify_evm_transaction(
            chain=chain,
            tx_hash=tx_hash,
            expected_recipient=recipient,
            expected_amount=amount,
            expected_token=token,
        )
    if not verify.get("verified"):
        raise HTTPException(status_code=400, detail=f"on-chain verification failed: {verify.get('error')}")
    payment_id = f"aimarket-{tx_hash[:24]}"
    order = commerce.create_order_and_license(
        customer_id=customer_id,
        customer_email=customer_email,
        payment_id=payment_id,
        product_id=product_id,
        amount=amount,
        currency=token,
        tx_hash=tx_hash,
    )
    event = {
        "type": "ai_market_entitlement_activated",
        "time": time.time(),
        "product_id": product_id,
        "tx_hash": tx_hash,
        "chain": chain,
        "token": token,
        "wallet_address": wallet,
        "customer_id": customer_id,
        "license_key": order.get("license_key"),
    }
    integration_results = await _fanout_external_integrations(event)
    return {
        "status": "entitlement_activated",
        "order_id": order.get("id"),
        "license_key": order.get("license_key"),
        "integration_results": integration_results,
    }


@router.get("/entitlements/{customer_id}")
async def list_entitlements(customer_id: str):
    licenses = _read_json(store_licenses_path())
    out = []
    for lic in licenses.values():
        if str(lic.get("customer_id") or "") != customer_id:
            continue
        out.append(
            {
                "license_key": lic.get("license_key"),
                "product_id": lic.get("product_id"),
                "status": lic.get("status"),
                "created_at": lic.get("created_at"),
            }
        )
    return {"customer_id": customer_id, "entitlements": out, "count": len(out)}


@router.post("/capabilities/{product_id}/{capability_id}/invoke")
async def invoke_capability(
    product_id: str,
    capability_id: str,
    body: AiMarketCapabilityInvokeRequest,
    x_ai_market_license: str | None = Header(default=None),
):
    if not x_ai_market_license:
        raise HTTPException(status_code=401, detail="x-ai-market-license header required")
    licenses = _read_json(store_licenses_path())
    lic = licenses.get(x_ai_market_license) or {}
    if not lic or str(lic.get("status") or "").lower() != "active":
        raise HTTPException(status_code=403, detail="license not active")
    if str(lic.get("product_id") or "") != product_id:
        raise HTTPException(status_code=403, detail="license not valid for this product")
    return {
        "product_id": product_id,
        "capability_id": capability_id,
        "status": "ok",
        "result": {
            "message": "Capability invocation accepted in pilot mode",
            "echo": body.input,
        },
    }
