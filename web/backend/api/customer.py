from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from core.pipeline_state_writer import append_product_to_pipeline_state
from web.backend.schemas.api_requests import (
    CustomerCreateRunRequest,
    CustomerLoginRequest,
    CustomerRegisterRequest,
    DemoNoteCreateRequest,
    DemoNotePatchRequest,
    StripeCheckoutRequest,
)
from web.backend.services.commerce import CommerceService

router = APIRouter(prefix="/api/customer", tags=["customer"])
commerce = CommerceService()

_REG_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "5"))
_REG_WINDOW_SEC = 3600.0
_register_attempts: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else ""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    trusted = frozenset(
        p.strip() for p in (os.environ.get("AIFACTORY_TRUSTED_PROXY_IPS") or "127.0.0.1,::1").split(",") if p.strip()
    )
    if forwarded and peer in trusted:
        return forwarded.split(",")[0].strip()
    return peer or "unknown"


def _enforce_register_rate_limit(ip: str) -> None:
    now = time.time()
    window = _register_attempts[ip]
    while window and now - window[0] > _REG_WINDOW_SEC:
        window.popleft()
    if len(window) >= _REG_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    window.append(now)


def _get_token_payload(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing customer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = commerce.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired customer token")
    return payload


def _stripe_price_catalog() -> dict[str, int]:
    return {
        "maker": int(os.environ.get("AIFACTORY_STRIPE_MAKER_PRICE_CENTS", "1900")),
        "studio": int(os.environ.get("AIFACTORY_STRIPE_STUDIO_PRICE_CENTS", "9900")),
        "enterprise": int(os.environ.get("AIFACTORY_STRIPE_ENTERPRISE_PRICE_CENTS", "49900")),
    }


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    if not sig_header or not secret:
        return False
    parts: dict[str, str] = {}
    for piece in sig_header.split(","):
        if "=" not in piece:
            continue
        k, v = piece.split("=", 1)
        parts[k.strip()] = v.strip()
    ts = parts.get("t")
    sig = parts.get("v1")
    if not ts or not sig:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > 300:
        return False
    signed_payload = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@router.post("/register")
async def register(body: CustomerRegisterRequest, request: Request):
    _enforce_register_rate_limit(_client_ip(request))
    try:
        customer = commerce.register_customer(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    token = commerce.create_token(customer["id"], customer["email"])
    return {"customer": customer, "access_token": token, "token_type": "bearer"}


@router.post("/login")
async def login(body: CustomerLoginRequest):
    customer = commerce.authenticate_customer(body.email, body.password)
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = commerce.create_token(customer["id"], customer["email"])
    return {"customer": customer, "access_token": token, "token_type": "bearer"}


@router.get("/me")
async def me(payload: dict = Depends(_get_token_payload)):
    profile = commerce.get_customer(payload["sub"]) or {}
    usage = commerce.get_monthly_run_usage(payload["sub"])
    return {
        "id": payload["sub"],
        "email": payload.get("email"),
        "plan": profile.get("plan", "free"),
        "usage": usage,
    }


@router.post("/logout")
async def customer_logout():
    """JWT is stateless — clients discard the bearer token after this ack."""
    return {"ok": True, "detail": "Discard bearer token on the client"}


@router.post("/demo-notes")
async def demo_notes_create(body: DemoNoteCreateRequest, payload: dict = Depends(_get_token_payload)):
    try:
        note = commerce.create_demo_note(payload["sub"], body.title, body.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"note": note}


@router.get("/demo-notes")
async def demo_notes_list(payload: dict = Depends(_get_token_payload)):
    notes = commerce.list_demo_notes(payload["sub"])
    return {"notes": notes, "count": len(notes)}


@router.patch("/demo-notes/{note_id}")
async def demo_notes_patch(
    note_id: str,
    body: DemoNotePatchRequest,
    payload: dict = Depends(_get_token_payload),
):
    try:
        updated = commerce.update_demo_note(
            payload["sub"],
            note_id.strip(),
            body.title,
            body.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": updated}


@router.delete("/demo-notes/{note_id}")
async def demo_notes_delete(note_id: str, payload: dict = Depends(_get_token_payload)):
    ok = commerce.delete_demo_note(payload["sub"], note_id.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True, "id": note_id}


@router.post("/billing/stripe/checkout")
async def create_stripe_checkout_session(body: StripeCheckoutRequest, payload: dict = Depends(_get_token_payload)):
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    target_plan = body.target_plan
    prices = _stripe_price_catalog()
    amount = prices.get(target_plan, prices["maker"])
    if amount <= 0:
        raise HTTPException(status_code=500, detail="Stripe price catalog misconfigured")

    customer = commerce.get_customer(payload["sub"])
    if not customer:
        raise HTTPException(status_code=401, detail="Customer not found")

    idem = f"cust:{payload['sub']}:plan:{target_plan}:{int(time.time() // 30)}"
    req_body = {
        "mode": "payment",
        "success_url": body.success_url,
        "cancel_url": body.cancel_url,
        "client_reference_id": payload["sub"],
        "customer_email": customer.get("email") or payload.get("email"),
        "metadata[customer_id]": payload["sub"],
        "metadata[target_plan]": target_plan,
        "metadata[source]": "aifactory_checkout",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": f"AI-Factory {target_plan.title()} plan",
        "line_items[0][price_data][unit_amount]": str(amount),
        "line_items[0][quantity]": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {secret_key}",
                    "Idempotency-Key": idem,
                },
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Stripe error: {resp.text[:300]}")
        data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe request failed: {exc}")

    session_id = str(data.get("id") or "")
    if not session_id:
        raise HTTPException(status_code=502, detail="Stripe session id missing")
    commerce.save_stripe_checkout_session(
        session_id=session_id,
        customer_id=payload["sub"],
        customer_email=customer.get("email") or payload.get("email") or "",
        target_plan=target_plan,
        amount_total=int(data.get("amount_total") or amount),
        currency=str(data.get("currency") or "usd"),
        status=str(data.get("status") or "open"),
        payment_status=str(data.get("payment_status") or "unpaid"),
        idempotency_key=idem,
    )
    return {
        "session_id": session_id,
        "checkout_url": data.get("url"),
        "amount_total": int(data.get("amount_total") or amount),
        "currency": str(data.get("currency") or "usd"),
        "target_plan": target_plan,
    }


@router.post("/billing/stripe/webhook")
async def stripe_webhook(request: Request):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    if not _verify_stripe_signature(payload, signature, secret):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = str(event.get("type") or "")
    event_id = str(event.get("id") or "")
    obj = ((event.get("data") or {}).get("object") or {})
    session_id = str(obj.get("id") or "")
    payment_status = str(obj.get("payment_status") or "")
    session_status = str(obj.get("status") or "")
    customer_email = obj.get("customer_email")
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    if not event_id or not session_id:
        raise HTTPException(status_code=400, detail="Webhook payload missing event/session ids")

    result = commerce.apply_stripe_webhook_event(
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
        payment_status=payment_status,
        session_status=session_status,
        customer_email=customer_email,
        metadata=metadata,
    )
    return {"ok": True, "event_type": event_type, **result}


@router.get("/orders")
async def list_orders(payload: dict = Depends(_get_token_payload)):
    orders = commerce.get_orders_for_customer(payload["sub"])
    return {"orders": orders, "count": len(orders)}


@router.get("/referrals/me")
async def my_referral_dashboard(payload: dict = Depends(_get_token_payload)):
    customer = commerce.get_customer(payload["sub"])
    if not customer:
        raise HTTPException(status_code=401, detail="Customer not found")
    return commerce.get_referral_stats(
        customer_id=payload["sub"],
        customer_email=customer.get("email") or payload.get("email") or "",
    )


@router.post("/pipeline/run")
async def customer_pipeline_run(body: CustomerCreateRunRequest, payload: dict = Depends(_get_token_payload)):
    customer_id = payload["sub"]
    profile = commerce.get_customer(customer_id)
    if not profile:
        raise HTTPException(status_code=401, detail="Customer not found")
    plan = str(profile.get("plan") or "free").lower()
    # Immediate revenue model: free has strict 3 runs/month.
    if plan == "free":
        quota = commerce.consume_monthly_run(customer_id, limit=3)
        if not quota.get("allowed"):
            raise HTTPException(
                status_code=402,
                detail="Free tier limit reached (3 pipeline runs/month). Upgrade required.",
            )
    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": body.idea.strip(),
        "admin_instructions": None,
        "delivery_profile": "full_software",
        "production_mode": False,
        "category": "saas",
        "tags": [],
        "state": "IDEA_RECEIVED",
        "created_at": ts,
        "updated_at": ts,
        "tasks": [],
        "spec": None,
        "architecture": None,
        "code": None,
        "marketing": None,
        "pricing": None,
        "evolution_history": [],
        "metadata": {
            "owner_customer_id": customer_id,
            "owner_email": profile.get("email"),
            "owner_plan": plan,
            "watermark_policy": "on" if plan == "free" else "off",
        },
    }
    if not append_product_to_pipeline_state(product):
        raise HTTPException(status_code=503, detail="Pipeline store unavailable. Try again shortly.")
    return {"product_id": product_id, "state": "IDEA_RECEIVED", "plan": plan}


@router.get("/orders/{order_id}/download")
async def download_order(order_id: str, payload: dict = Depends(_get_token_payload)):
    orders = commerce.get_orders_for_customer(payload["sub"])
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    archive = commerce.build_download_archive(order)
    return FileResponse(
        path=str(archive),
        media_type="application/zip",
        filename=archive.name,
    )
