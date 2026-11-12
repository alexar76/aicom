"""Routes of the x402 bridge (aimarket_hub/x402_bridge.py).

``GET /ai-market/v2/x402-bridge``: public. Whether this hub pays x402 sellers for credit buyers, from which
wallet, with what limits, and what it spent today.

``POST /ai-market/v2/observed/invoke``: a credit buyer buys an observed x402 route (spec §2.7) through this
hub. Until now an observed route said "call the url yourself and pay per the 402": a buyer with credits and no
wallet could not. Body: ``url`` (a route this hub serves on /federation/observed-sellers), ``input`` (the JSON
body for a POST route), optional ``max_price_usd``. The buyer's credits hold the observed price, the bridge pays
the seller's own 402 — never more than that price, only to the payee this hub observed or pinned — and the
buyer is charged what was paid, once the seller answered 2xx.
"""

from __future__ import annotations

import json
import math
import secrets
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from aimarket_hub import credits, x402_bridge
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase

MAX_REPLY_BYTES = 1_048_576
REQUEST_TIMEOUT_S = 30.0
_PASSED_REPLY_HEADERS = ("payment-response", "x-payment-response", "content-type")


class _Reply:
    """What x402_bridge.pay_and_resend reads from a seller's answer."""

    def __init__(self, status: int, raw: bytes, headers: dict[str, str]):
        self.status_code, self.raw, self.headers = int(status), raw or b"", dict(headers or {})

    def json(self) -> Any:
        if not self.raw:
            raise ValueError("empty body")
        return json.loads(self.raw)


def _result_fields(reply: _Reply) -> dict[str, Any]:
    try:
        return {"result": reply.json()}
    except ValueError:
        return {"result_text": reply.raw.decode("utf-8", errors="replace")[:200_000],
                "content_type": reply.headers.get("content-type", "")}


def register(*, config: HubConfig, db: HubDatabase, hub_credits: Any, router: APIRouter,
             check_rate: Any = None) -> SimpleNamespace:
    def ledger() -> x402_bridge.BridgeLedger:
        return x402_bridge.BridgeLedger(db._conn)

    @router.get("/x402-bridge")
    async def x402_bridge_status():
        return {**x402_bridge.status(ledger(), hub_url=config.hub_url), "protocol_version": "v2"}

    @router.post("/observed/invoke")
    async def observed_invoke(request: Request, body: dict,
                              x_api_key: str | None = Header(default=None, alias="X-API-Key")):
        from aimarket_hub import observed_sellers as _observed
        from aimarket_hub.outbound_http import safe_request_capped

        # Every answer here is about the buyer's credits or the seller's terms, never an offer
        # to pay THIS hub on chain: keep the x402 middleware from adding one to a 402.
        request.state.x402_passthrough = True

        reason = x402_bridge.unavailable_reason()
        if reason:
            raise HTTPException(status_code=503, detail=f"this hub does not pay x402 sellers for you: {reason}")
        if not credits.enabled() or hub_credits is None:
            raise HTTPException(status_code=503, detail="credit accounts are off on this hub")
        account_id = hub_credits.resolve(x_api_key or "")
        if not account_id:
            raise HTTPException(status_code=401, detail="unknown or disabled X-API-Key")
        # The invoke limit, per account: each call makes this hub knock on a stranger's door, and a
        # seller that answers for free would otherwise be reachable through us without bound.
        if check_rate is not None and not check_rate("observed:" + account_id):
            return JSONResponse(status_code=429, content={
                "success": False, "error": "rate_limited", "detail": "invoke rate limit exceeded — slow down",
                "protocol_version": "v2"})
        url = body.get("url") if isinstance(body, dict) else None
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(status_code=400, detail="url (a route from /federation/observed-sellers) is required")
        url = url.strip()
        payload = body.get("input", {})
        if payload is not None and not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="input must be a JSON object")
        cap = body.get("max_price_usd")
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float))
                                or not math.isfinite(float(cap)) or float(cap) <= 0):
            raise HTTPException(status_code=400, detail="max_price_usd must be a positive number")

        sellers = db.list_observed_sellers()
        route = next((r for r in _observed.served_routes(sellers, hub_url=config.hub_url) if r["url"] == url), None)
        if route is None:
            raise HTTPException(status_code=404, detail=(
                "not a route this hub serves now: see /ai-market/v2/federation/observed-sellers "
                "(a route is served while its last observation is fresh and quoted)"))
        price = route.get("price_usd")
        if not isinstance(price, (int, float)) or not math.isfinite(float(price)) or float(price) <= 0:
            raise HTTPException(status_code=409, detail="the observed price of this route is not a positive USD amount")
        price = float(price)
        if cap is not None and price > float(cap) + 1e-9:
            return JSONResponse(status_code=409, content={
                "success": False, "error": "price_limit_exceeded", "maximum_price_usd": float(cap),
                "current_price_usd": price, "protocol_version": "v2"})
        seller = next((s for s in sellers if s["origin"] == route["seller"]), {})
        payee = str(seller.get("pinned_pay_to") or route.get("pay_to") or "")

        receipt = "xbo_" + secrets.token_hex(12)
        held = hub_credits.hold(account_id, price, receipt)
        if held.get("error"):
            return JSONResponse(status_code=402, content={
                "success": False, "error": "payment_required", "detail": held["error"], "needed": price,
                "balance": hub_credits.balance(account_id), "protocol_version": "v2"})

        method = route.get("method") or "POST"
        base_headers = {"User-Agent": _observed._crawler.USER_AGENT, "Accept": "application/json",
                        "X-AIMarket-Routing-Hub": config.hub_url}
        if method == "POST":
            base_headers["Content-Type"] = "application/json"

        async def call(extra: dict[str, str]) -> _Reply:
            try:
                status, raw, headers = await safe_request_capped(
                    method, url, json=(payload or {}) if method == "POST" else None,
                    headers={**base_headers, **extra}, timeout=REQUEST_TIMEOUT_S, max_bytes=MAX_REPLY_BYTES)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"this hub will not call that route: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=502, detail=f"the seller did not answer: {type(exc).__name__}") from exc
            return _Reply(status, raw, headers)

        captured = False
        payment = None
        try:
            first = await call({})
            if first.status_code != 402:
                if 200 <= first.status_code < 300:
                    # Served without asking to be paid: nothing was paid, nothing is charged.
                    return {"success": True, "seller": route["seller"], "url": url, "status": first.status_code,
                            "price_usd": 0.0, "paid_via": None, **_result_fields(first),
                            "note": "the seller answered without asking to be paid; nothing was charged",
                            "protocol_version": "v2"}
                return JSONResponse(status_code=502, content={
                    "success": False, "error": "seller_error", "seller_status": first.status_code,
                    "detail": f"the seller answered {first.status_code} before quoting — nothing was charged to you",
                    **_result_fields(first), "protocol_version": "v2"})
            book = ledger()
            try:
                reply, payment = await x402_bridge.pay_and_resend(
                    ledger=book, first=first, resend=call, limit_usd=price, expected_pay_to=payee or None,
                    buyer_account=account_id, receipt_id=receipt, seller=route["seller"], route=url)
            except x402_bridge.BridgeRefused as exc:
                return JSONResponse(status_code=502, content={
                    "success": False, "error": "upstream_unpaid",
                    "detail": f"this hub did not pay the seller: {exc.reason} — nothing was charged to you",
                    "bridge": {"via": "x402-bridge", "refusal": exc.code}, "protocol_version": "v2"})
            passed = {k: v for k, v in reply.headers.items() if k.lower() in _PASSED_REPLY_HEADERS[:2]}
            if 200 <= reply.status_code < 300:
                capture = hub_credits.capture_hold(receipt, amount_mc=payment.amount_mc)
                if capture.get("error") or capture.get("already") not in (None, "captured"):
                    raise HTTPException(status_code=502, detail="settlement failed: reservation could not be captured")
                captured = True
                x402_bridge.finish(book, payment, delivered=True, http_status=reply.status_code)
                return JSONResponse(headers=passed, content={
                    "success": True, "seller": route["seller"], "url": url, "status": reply.status_code,
                    "price_usd": round(payment.amount_usd, 6), "paid_via": payment.public(config.hub_url),
                    **_result_fields(reply), "protocol_version": "v2"})
            x402_bridge.finish(book, payment, delivered=False, http_status=reply.status_code,
                               detail=f"the seller answered the paid call with {reply.status_code}")
            refused = reply.status_code == 402
            return JSONResponse(status_code=502, content={
                "success": False, "error": "upstream_unpaid" if refused else "seller_error",
                "seller_status": reply.status_code,
                "detail": ("the seller refused this hub's payment" if refused
                           else f"the seller answered {reply.status_code} to the paid call")
                          + " — nothing was charged to you",
                "protocol_version": "v2"})
        finally:
            if payment is not None and payment.status == "signed":
                x402_bridge.finish(ledger(), payment, delivered=False, http_status=0,
                                   detail="paid, but the purchase did not complete")
            if not captured:
                hub_credits.release_hold(receipt)

    return SimpleNamespace(observed_invoke=observed_invoke, x402_bridge_status=x402_bridge_status)
