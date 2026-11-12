from __future__ import annotations

import hashlib
import hmac
import json
import logging
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
logger = logging.getLogger(__name__)
commerce = CommerceService()

_REG_MAX_PER_HOUR = int(os.environ.get("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "5"))
_REG_WINDOW_SEC = 3600.0
_register_attempts: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Canonical resolver: the RIGHTMOST non-trusted X-Forwarded-For entry.
    # The inline parser this replaces trusted the LEFTMOST value, which the client
    # controls -- nginx `proxy_add_x_forwarded_for` APPENDS what it saw, so a caller
    # that sends its own X-Forwarded-For lands leftmost and can rotate a spoofed IP
    # past this per-IP limit. See web/backend/http/client_ip.py.
    from web.backend.http.client_ip import client_ip as _resolve

    return _resolve(request)


def _enforce_register_rate_limit(ip: str) -> None:
    now = time.time()
    window = _register_attempts[ip]
    while window and now - window[0] > _REG_WINDOW_SEC:
        window.popleft()
    if len(window) >= _REG_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    window.append(now)


# Failed customer logins, per client address and per email: the route had no limit at all.
_LOGIN_FAIL_WINDOW_SEC = 900.0
_LOGIN_FAIL_MAX_PER_IP = int(os.environ.get("AIFACTORY_CUSTOMER_LOGIN_FAILS_PER_IP", "20"))
_LOGIN_FAIL_MAX_PER_EMAIL = int(os.environ.get("AIFACTORY_CUSTOMER_LOGIN_FAILS_PER_EMAIL", "10"))
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def _recent_failures(key: str, now: float) -> deque[float]:
    window = _login_failures[key]
    while window and now - window[0] > _LOGIN_FAIL_WINDOW_SEC:
        window.popleft()
    return window


def _enforce_login_rate_limit(ip: str, email: str) -> None:
    now = time.time()
    if (len(_recent_failures(f"ip:{ip}", now)) >= _LOGIN_FAIL_MAX_PER_IP
            or len(_recent_failures(f"email:{email}", now)) >= _LOGIN_FAIL_MAX_PER_EMAIL):
        raise HTTPException(status_code=429, detail="Too many failed sign-ins. Try again later.")


def _record_login_failure(ip: str, email: str) -> None:
    now = time.time()
    _recent_failures(f"ip:{ip}", now).append(now)
    _recent_failures(f"email:{email}", now).append(now)
    if len(_login_failures) > 20000:
        for key in [k for k, v in _login_failures.items() if not v][:5000]:
            _login_failures.pop(key, None)


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
    ts = ""
    signatures = []
    for piece in sig_header.split(","):
        key, _, value = piece.strip().partition("=")
        if key == "t":
            ts = value
        if key == "v1":
            signatures.append(value)
    if not ts.isascii() or not ts.isdigit() or not signatures:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if abs(time.time() - ts_int) > 300:
        return False
    signed_payload = ts.encode("ascii") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures if sig.isascii())


@router.post("/register")
async def register(body: CustomerRegisterRequest, request: Request):
    _enforce_register_rate_limit(_client_ip(request))
    try:
        customer = commerce.register_customer(body.email, body.password)
    except ValueError:
        # Not "this email already has an account": that told anyone which addresses do.
        raise HTTPException(status_code=409, detail="Could not register with these details.")
    token = commerce.create_token(customer["id"], customer["email"])
    return {"customer": customer, "access_token": token, "token_type": "bearer"}


@router.post("/login")
async def login(body: CustomerLoginRequest, request: Request):
    ip = _client_ip(request)
    email = str(body.email or "").strip().lower()
    _enforce_login_rate_limit(ip, email)
    customer = commerce.authenticate_customer(body.email, body.password)
    if not customer:
        _record_login_failure(ip, email)
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
async def customer_logout(authorization: Optional[str] = Header(default=None)):
    """End the session server-side: the token's jti is revoked until it would have expired."""
    if authorization and authorization.startswith("Bearer "):
        commerce.revoke_token(authorization.split(" ", 1)[1].strip())
    return {"ok": True, "detail": "Signed out"}


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
            raise HTTPException(status_code=502, detail="Stripe checkout request failed")
        data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Stripe checkout request failed") from exc

    session_id = str(data.get("id") or "")
    expected_prefix = "cs_live_" if secret_key.startswith(("sk_live_", "rk_live_")) else "cs_test_"
    if (not session_id.startswith(expected_prefix) or data.get("amount_total") != amount
            or data.get("currency") != "usd"):
        raise HTTPException(status_code=502, detail="Stripe checkout does not match the order")
    commerce.save_stripe_checkout_session(
        session_id=session_id,
        customer_id=payload["sub"],
        customer_email=customer.get("email") or payload.get("email") or "",
        target_plan=target_plan,
        amount_total=amount,
        currency="usd",
        status=str(data.get("status") or "open"),
        payment_status="unpaid",
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

    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    event_type = str(event.get("type") or "")
    if event_type in ("charge.refunded", "charge.dispute.created"):
        return await _stripe_reversal(event, event_type)
    if event_type not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {"ok": True, "event_type": event_type, "ignored": True}
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret_key.startswith(("sk_live_", "rk_live_", "sk_test_", "rk_test_")):
        raise HTTPException(status_code=503, detail="Stripe checkout mode is not configured")
    live = secret_key.startswith(("sk_live_", "rk_live_"))
    event_id = str(event.get("id") or "")
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="Invalid Stripe checkout event")
    session_id = str(obj.get("id") or "")
    if (not event_id or not session_id.startswith("cs_live_" if live else "cs_test_")
            or event.get("livemode") is not live or obj.get("livemode") is not live
            or obj.get("object") != "checkout.session"):
        raise HTTPException(status_code=400, detail="Invalid Stripe checkout event")

    try:
        result = commerce.apply_stripe_webhook_event(
            event_id=event_id,
            event_type=event_type,
            session_id=session_id,
            payment_status=str(obj.get("payment_status") or ""),
            session_status=str(obj.get("status") or ""),
            amount_total=obj.get("amount_total"),
            currency=str(obj.get("currency") or ""),
            payment_intent=str(obj.get("payment_intent") or ""),
        )
    except LookupError as exc:
        raise HTTPException(status_code=503, detail="Stripe checkout record is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Stripe checkout amount or currency mismatch") from exc
    return {"ok": True, "event_type": event_type, **result}


async def _stripe_reversal(event: dict, event_type: str) -> dict:
    """charge.refunded (full refunds only) and charge.dispute.created take the plan back.

    Audit 2026-11-11, desks-stripe-7: these were acknowledged as ignored, so a refunded or
    charged-back customer kept the paid plan forever. A checkout paid before payment intents
    were recorded is found by asking Stripe which session the intent belongs to.
    """
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not secret_key.startswith(("sk_live_", "rk_live_", "sk_test_", "rk_test_")):
        raise HTTPException(status_code=503, detail="Stripe checkout mode is not configured")
    live = secret_key.startswith(("sk_live_", "rk_live_"))
    event_id = str(event.get("id") or "")
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict) or not event_id or event.get("livemode") is not live:
        raise HTTPException(status_code=400, detail="Invalid Stripe reversal event")
    if event_type == "charge.refunded" and obj.get("refunded") is not True:
        return {"ok": True, "event_type": event_type, "ignored": True, "reason": "partial refund"}
    payment_intent = str(obj.get("payment_intent") or "")
    if not payment_intent:
        return {"ok": True, "event_type": event_type, "ignored": True, "reason": "no payment intent"}
    try:
        result = commerce.apply_stripe_reversal(event_id, event_type, payment_intent=payment_intent)
    except LookupError:
        session_id = await _stripe_session_for_intent(secret_key, payment_intent)
        if not session_id:
            # Not a factory checkout (another product on the same Stripe account), or Stripe
            # could not be asked: 200 so Stripe does not retry forever; the log names it.
            logger.warning("stripe: %s for %s matches no factory checkout", event_type, payment_intent)
            return {"ok": True, "event_type": event_type, "ignored": True, "reason": "no factory checkout"}
        try:
            result = commerce.apply_stripe_reversal(event_id, event_type, payment_intent=payment_intent,
                                                    session_id=session_id)
        except LookupError:
            return {"ok": True, "event_type": event_type, "ignored": True, "reason": "no factory checkout"}
    return {"ok": True, "event_type": event_type, **result}


async def _stripe_session_for_intent(secret_key: str, payment_intent: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.stripe.com/v1/checkout/sessions",
                                    params={"payment_intent": payment_intent, "limit": 1},
                                    auth=(secret_key, ""))
        if resp.status_code >= 300:
            return ""
        rows = resp.json().get("data") or []
        return str(rows[0].get("id") or "") if rows else ""
    except Exception:  # noqa: BLE001
        return ""


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
    from core.generated_code_execution import unsafe_host_execution_requested

    if unsafe_host_execution_requested():
        # This is public, untrusted input even when the deployment forgot its
        # production marker. A local host-execution opt-in cannot authorize a
        # stranger to submit code to that host.
        raise HTTPException(status_code=503, detail="Customer product creation requires an isolated worker")
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

    from web.backend.services.prompt_safety import (
        prepare_untrusted_plain_text,
        rejection_reason_if_blocked,
    )

    idea_raw = (body.idea or "").strip()
    blocked = rejection_reason_if_blocked(idea_raw, context="customer_idea")
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    idea_clean = prepare_untrusted_plain_text(idea_raw, max_len=8000)
    if len(idea_clean) < 8:
        raise HTTPException(status_code=422, detail="Idea is too short.")

    product_id = f"prod-{uuid.uuid4().hex[:12]}"
    ts = time.time()
    product = {
        "id": product_id,
        "idea": idea_clean,
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
