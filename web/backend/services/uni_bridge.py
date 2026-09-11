"""Bridge UNI wallet into AI Market, payments, and monitor."""

from __future__ import annotations

import logging
from typing import Any

from core.uni.config import uni_enabled
from core.uni.pricing import usd_to_uni
from core.uni.wallet import UniWalletService

logger = logging.getLogger(__name__)

_svc: UniWalletService | None = None


def uni_wallet() -> UniWalletService:
    global _svc
    if _svc is None:
        _svc = UniWalletService()
    return _svc


def record_channel_open(
    *,
    customer_id: str,
    channel_id: str,
    deposit_usd: float,
    tx_hash: str,
    chain: str,
    token: str,
) -> dict[str, Any] | None:
    if not uni_enabled():
        return None
    try:
        topup = uni_wallet().topup_from_chain(
            customer_id,
            usd_amount=deposit_usd,
            tx_hash=tx_hash,
            chain=chain,
            token=token,
        )
        amount_uni = float(usd_to_uni(deposit_usd, apply_spread=True))
        hold = uni_wallet().hold(
            customer_id,
            amount_uni=amount_uni,
            channel_id=channel_id,
            seller_ref="ai_market",
        )
        return {"topup": topup, "hold": hold, "amount_uni": amount_uni}
    except Exception as exc:
        logger.warning("UNI channel open failed: %s", exc)
        return {"error": str(exc)}


def record_channel_spend(*, channel_id: str, price_usd: float, ref: str) -> dict[str, Any] | None:
    if not uni_enabled():
        return None
    amount_uni = usd_to_uni(price_usd, apply_spread=False)
    try:
        return uni_wallet().spend_hold(channel_id=channel_id, amount_uni=amount_uni, ref=ref)
    except Exception as exc:
        logger.warning("UNI spend_hold failed: %s", exc)
        return {"error": str(exc)}


def record_channel_release(channel_id: str) -> dict[str, Any] | None:
    if not uni_enabled():
        return None
    try:
        return uni_wallet().release_hold(channel_id)
    except Exception as exc:
        logger.warning("UNI release_hold failed: %s", exc)
        return {"error": str(exc)}


def record_capability_settlement(
    *,
    buyer_owner_id: str,
    product_id: str,
    capability_id: str,
    price_usd: float,
    payment_ref: str,
    hub_id: str = "",
    llm_tokens: int = 0,
) -> dict[str, Any] | None:
    if not uni_enabled():
        return None
    amount_uni = usd_to_uni(price_usd, apply_spread=False)
    seller_ref = f"seller:{product_id}"
    try:
        out = uni_wallet().charge(
            buyer_owner_id,
            seller_owner_id=seller_ref,
            amount_uni=amount_uni,
            meta={
                "product_id": product_id,
                "capability_id": capability_id,
                "payment_ref": payment_ref,
                "hub_id": hub_id,
                "llm_tokens": llm_tokens,
            },
            idempotency_key=f"invoke:{payment_ref}:{capability_id}",
            receipt_kind="invoke",
        )
        return {"charge": out, "uni_receipt": out.get("receipt")}
    except Exception as exc:
        logger.error("UNI capability settlement failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


def credit_payment_confirm(
    *,
    customer_id: str,
    product_id: str,
    usd_amount: float,
    tx_hash: str,
    chain: str,
    token: str,
) -> dict[str, Any] | None:
    if not uni_enabled():
        return None
    try:
        return uni_wallet().topup_from_chain(
            customer_id,
            usd_amount=usd_amount,
            tx_hash=tx_hash,
            chain=chain,
            token=token,
        )
    except Exception as exc:
        logger.warning("UNI payment topup failed: %s", exc)
        return {"error": str(exc)}
