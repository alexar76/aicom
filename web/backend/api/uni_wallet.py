"""UNI wallet API — unified credit bus for the ecosystem."""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from core.uni.config import (
    uni_enabled,
    uni_grant_secret,
    uni_min_withdraw_uni,
    uni_platform_fee_bps,
    uni_topup_spread_bps,
    uni_withdraw_fee_bps,
    usdt_to_uni_rate,
)
from core.uni.pricing import uni_to_usd
from core.uni.receipts import get_receipt, list_receipts_for_wallet
from core.uni.wallet import UniWalletError, UniWalletService
from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.customer_auth import require_customer
from web.backend.services.uni_bridge import uni_wallet

router = APIRouter(prefix="/api/uni", tags=["uni-wallet"])


class UniGrantRequest(BaseModel):
    owner_id: str = Field(..., min_length=3, max_length=128)
    amount_uni: float = Field(..., gt=0, le=1_000_000)
    ref: str = Field(..., min_length=4, max_length=128)
    reason: str = Field("", max_length=256)


class UniTopupConfirmRequest(BaseModel):
    tx_hash: str = Field(..., min_length=16, max_length=128)
    usd_amount: float = Field(..., gt=0, le=1_000_000)
    chain: str = Field("base", max_length=32)
    token: str = Field("USDT", max_length=16)


class UniWithdrawRequest(BaseModel):
    amount_uni: int = Field(..., gt=0, le=100_000_000)
    payout_address: str = Field(..., min_length=8, max_length=128)
    chain: str = Field("base", max_length=32)
    token: str = Field("USDT", max_length=16)


def _require_uni() -> None:
    if not uni_enabled():
        raise HTTPException(status_code=503, detail="UNI wallet is disabled")


def _require_grant_secret(x_uni_grant_secret: str | None = Header(default=None, alias="X-Uni-Grant-Secret")) -> None:
    secret = uni_grant_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="UNI grant endpoint not configured")
    if (x_uni_grant_secret or "").strip() != secret:
        raise HTTPException(status_code=403, detail="Invalid grant secret")


@router.get("/config")
async def uni_config():
    _require_uni()
    return {
        "enabled": True,
        "peg": "1 UNI = $0.01 USDT",
        "uni_per_usdt": int(usdt_to_uni_rate()),
        "usdt_to_uni_rate": usdt_to_uni_rate(),
        "topup_spread_bps": uni_topup_spread_bps(),
        "platform_fee_bps": uni_platform_fee_bps(),
        "withdraw_fee_bps": uni_withdraw_fee_bps(),
        "min_withdraw_uni": uni_min_withdraw_uni(),
        "db_backend": os.environ.get("UNI_DB_BACKEND", "sqlite"),
    }


@router.get("/wallet")
async def get_my_wallet(customer: dict = Depends(require_customer)):
    _require_uni()
    owner_id = str(customer.get("sub") or "")
    wallet = uni_wallet().get_or_create_wallet(owner_id)
    wallet["balance_usd_approx"] = uni_to_usd(wallet["balance_uni"])
    wallet["available_usd_approx"] = uni_to_usd(wallet["available_uni"])
    return {"wallet": wallet, "protocol": "uni-v1"}


@router.get("/receipts")
async def list_my_receipts(
    customer: dict = Depends(require_customer),
    since: float = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    _require_uni()
    owner_id = str(customer.get("sub") or "")
    w = uni_wallet().get_or_create_wallet(owner_id)
    receipts = list_receipts_for_wallet(w["wallet_id"], since=since, limit=limit)
    return {"receipts": receipts, "count": len(receipts)}


@router.get("/receipt/{receipt_id}")
async def fetch_receipt(receipt_id: str, customer: dict = Depends(require_customer)):
    """Fetch a receipt. Only a wallet that is a party to the receipt (the receipt's
    owning wallet, the buyer, or the seller) may read it. Non-parties receive a 404 —
    not 403 — so the endpoint does not reveal whether a given ``receipt_id`` exists,
    keeping it from being used as an enumeration oracle by anyone who scrapes IDs
    from logs or webhooks."""
    _require_uni()
    r = get_receipt(receipt_id)
    if not r:
        raise HTTPException(status_code=404, detail="receipt not found")
    owner_id = str(customer.get("sub") or "")
    wallet = uni_wallet().get_or_create_wallet(owner_id)
    receipt_wallet = str(r.pop("_wallet_id", None) or r.get("wallet_id") or "")
    buyer_wallet = str(r.get("buyer_wallet_id") or "")
    seller_wallet = str(r.get("seller_wallet_id") or "")
    requester = wallet["wallet_id"]
    if requester not in {receipt_wallet, buyer_wallet, seller_wallet} - {""}:
        # Same 404 as a missing receipt to avoid disclosing existence.
        raise HTTPException(status_code=404, detail="receipt not found")
    from core.uni.receipts import verify_receipt

    if not verify_receipt(r):
        raise HTTPException(status_code=500, detail="receipt signature invalid")
    # When OTEL_TRACE_URL_TEMPLATE is configured (e.g. for LangSmith), expose a
    # clickable trace_url so the receipt holder can audit the underlying LLM
    # work that this UNI debit paid for.
    try:
        from core.tracing import trace_url_for

        url = trace_url_for(r.get("trace_id"))
        if url:
            r["trace_url"] = url
    except Exception:
        pass
    return r


@router.get("/economy/summary")
async def economy_summary():
    """Public aggregate for Alien Monitor / Hub dashboards (no PII)."""
    _require_uni()
    summary = uni_wallet().economy_summary()
    summary["usdt_to_uni_rate"] = usdt_to_uni_rate()
    summary["ts"] = time.time()
    return summary


@router.post("/grant")
async def grant_uni(body: UniGrantRequest, _: None = Depends(_require_grant_secret)):
    """Grant UNI (monitor funding stream, referrals, admin). Requires X-Uni-Grant-Secret."""
    _require_uni()
    try:
        out = uni_wallet().grant(
            body.owner_id,
            amount_uni=body.amount_uni,
            ref=body.ref,
            meta={"reason": body.reason},
        )
    except UniWalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "granted", **out}


@router.post("/topup/intent")
async def topup_intent(customer: dict = Depends(require_customer)):
    """Treasury deposit instructions (USDT on-chain → UNI credit after confirm)."""
    _require_uni()
    from web.backend.services.ai_market_protocol.config import ai_market_chain, ai_market_contract, ai_market_token

    return {
        "treasury": {
            "chain": ai_market_chain(),
            "token": ai_market_token(),
            "contract": ai_market_contract(),
        },
        "peg": {"uni_per_usdt": int(usdt_to_uni_rate()), "topup_spread_bps": uni_topup_spread_bps()},
        "owner_id": str(customer.get("sub") or ""),
    }


@router.post("/topup/confirm")
async def confirm_topup(body: UniTopupConfirmRequest, customer: dict = Depends(require_customer)):
    """Verify on-chain deposit and credit UNI (uses same verifier as payments)."""
    _require_uni()
    from web.backend.services.ai_market_protocol.on_chain import normalize_tx_hash, verify_tx_payment

    owner_id = str(customer.get("sub") or "")
    chain = body.chain.strip().lower()
    token = body.token.strip().upper()
    tx_clean = normalize_tx_hash(body.tx_hash, chain=chain)
    if not verify_tx_payment(tx_hash=tx_clean, amount_usd=body.usd_amount, chain=chain, token=token):
        raise HTTPException(status_code=400, detail="on-chain topup not verified")
    try:
        out = uni_wallet().topup_from_chain(
            owner_id,
            usd_amount=body.usd_amount,
            tx_hash=tx_clean,
            chain=chain,
            token=token,
        )
    except UniWalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "credited", **out}


@router.post("/withdraw")
async def request_withdraw(body: UniWithdrawRequest, customer: dict = Depends(require_customer)):
    _require_uni()
    import os

    if os.environ.get("AIFACTORY_UNI_WITHDRAW_DISPATCHER", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        raise HTTPException(
            status_code=503,
            detail="On-chain withdrawals are temporarily disabled until treasury dispatcher is enabled.",
        )
    owner_id = str(customer.get("sub") or "")
    try:
        out = uni_wallet().withdraw_to_chain(
            owner_id,
            amount_uni=body.amount_uni,
            payout_address=body.payout_address.strip(),
            chain=body.chain.strip().lower(),
            token=body.token.strip().upper(),
        )
    except UniWalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "queued", **out}


@router.get("/treasury/audit")
async def treasury_audit_latest():
    """Latest reserve snapshot (strictly read-only).

    Never writes — if no snapshot exists yet, return a placeholder so an
    unauthenticated client cannot use this endpoint to flood ``uni_treasury_audit``
    or to capture an env-overridden ``usdt_observed_on_chain`` into the audit
    timeline. Snapshot creation lives behind admin auth at
    ``POST /api/uni/treasury/audit/snapshot`` and the periodic ``uni_scheduler``.
    """
    _require_uni()
    from core.uni.treasury import get_latest_treasury_audit

    latest = get_latest_treasury_audit()
    if latest:
        return latest
    return {
        "snapshot_id": None,
        "note": "no snapshot yet — run POST /api/uni/treasury/audit/snapshot (admin) or wait for the scheduler",
    }


@router.post("/treasury/audit/snapshot")
async def treasury_audit_snapshot(_admin: dict = Depends(require_admin_with_rbac)):
    """Operator-triggered treasury snapshot (mutates audit table)."""
    _require_uni()
    from core.uni.treasury import snapshot_treasury_audit

    return snapshot_treasury_audit()


@router.get("/withdraw/{withdrawal_id}")
async def get_withdraw_status(withdrawal_id: str, customer: dict = Depends(require_customer)):
    _require_uni()
    from core.uni.config import uni_db_backend
    from core.uni.store import row_to_dict, uni_connection

    owner_id = str(customer.get("sub") or "")
    wallet = uni_wallet().get_or_create_wallet(owner_id)
    wid = withdrawal_id.strip()
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT * FROM uni_withdrawals WHERE withdrawal_id = %s AND wallet_id = %s",
                (wid, wallet["wallet_id"]),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM uni_withdrawals WHERE withdrawal_id = ? AND wallet_id = ?",
                (wid, wallet["wallet_id"]),
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="withdrawal not found")
    return {"withdrawal": row_to_dict(row)}
