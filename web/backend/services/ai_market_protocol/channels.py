"""Pre-funded payment channels (off-chain ledger, on-chain settle)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.uni.config import uni_enabled
from core.uni.pricing import uni_to_usd
from web.backend.services.ai_market_protocol.config import demo_payment_bypass, pilot_tuple
from web.backend.services.ai_market_protocol.on_chain import normalize_tx_hash, verify_tx_payment
from web.backend.services.ai_market_protocol.paths import channels_path
from web.backend.services.ai_market_protocol.signing import sign_payload
from web.backend.services.commerce import CommerceService

_commerce = CommerceService()


def _load_channels() -> dict[str, Any]:
    p = channels_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_channels(data: dict[str, Any]) -> None:
    channels_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _tx_hash_already_used(tx_clean: str) -> bool:
    if not tx_clean or tx_clean.startswith("demo-"):
        return False
    if _commerce.get_order_by_tx_hash(tx_clean):
        return True
    for ch in _load_channels().values():
        if ch.get("open_tx_hash") == tx_clean:
            return True
        if ch.get("settle_tx_hash") == tx_clean:
            return True
    return False


def open_channel(
    *,
    deposit_usd: float,
    token: str | None = None,
    chain: str | None = None,
    wallet: str = "",
    tx_hash: str = "",
    customer_id: str = "",
    customer_email: str = "",
) -> dict[str, Any]:
    cfg = pilot_tuple()
    token = (token or cfg["token"]).upper()
    chain = (chain or cfg["chain"]).lower()
    if deposit_usd <= 0 or deposit_usd > 10_000:
        return {"error": "invalid_deposit", "detail": "deposit must be in (0, 10000]"}
    if not customer_id or not customer_email:
        return {"error": "customer_required", "detail": "customer authentication required"}

    tx_clean = ""
    if demo_payment_bypass():
        tx_clean = (tx_hash or "").strip() or ""
        if not tx_clean:
            ch_id_preview = f"ch_{uuid.uuid4().hex[:12]}"
            tx_clean = f"demo-{ch_id_preview}"
    else:
        if not (tx_hash or "").strip():
            return {"error": "tx_hash_required", "detail": "deposit transaction hash required"}
        tx_clean = normalize_tx_hash(tx_hash, chain=chain)
        if _tx_hash_already_used(tx_clean):
            return {"error": "tx_hash_already_used", "detail": "transaction hash already used"}
        if not verify_tx_payment(tx_hash=tx_clean, amount_usd=deposit_usd, chain=chain, token=token):
            return {"error": "tx_not_verified", "detail": "on-chain deposit not verified"}

    ch_id = f"ch_{uuid.uuid4().hex[:12]}"
    now = time.time()
    channel = {
        "channel_id": ch_id,
        "deposit_usd": round(deposit_usd, 4),
        "balance_usd": round(deposit_usd, 4),
        "spent_usd": 0.0,
        "token": token,
        "chain": chain,
        "wallet": wallet,
        "open_tx_hash": tx_clean or f"demo-{ch_id}",
        "customer_id": customer_id,
        "customer_email": customer_email,
        "status": "open",
        "created_at": now,
        "expires_at": now + 3600 * 24,
        "ledger": [],
    }
    data = _load_channels()
    data[ch_id] = channel
    _save_channels(data)

    if uni_enabled():
        from web.backend.services.uni_bridge import record_channel_open

        uni_out = record_channel_open(
            customer_id=customer_id,
            channel_id=ch_id,
            deposit_usd=deposit_usd,
            tx_hash=tx_clean or f"demo-{ch_id}",
            chain=chain,
            token=token,
        )
        if uni_out and uni_out.get("error"):
            data.pop(ch_id, None)
            _save_channels(data)
            return {"error": "uni_hold_failed", "detail": uni_out.get("error")}
        channel["uni"] = uni_out
        channel["balance_uni"] = uni_out.get("amount_uni") if uni_out else usd_to_uni(deposit_usd)

    channel["signature"] = sign_payload(
        {"channel_id": ch_id, "deposit_usd": channel["deposit_usd"], "created_at": now}
    )
    return {"channel": channel, "protocol_version": "v1"}


def get_channel(channel_id: str) -> dict[str, Any] | None:
    return _load_channels().get(channel_id)


def deduct_channel(channel_id: str, amount_usd: float, *, ref: str) -> dict[str, Any]:
    data = _load_channels()
    ch = data.get(channel_id)
    if not ch or ch.get("status") != "open":
        return {"ok": False, "error": "channel_not_open"}

    if uni_enabled() and ch.get("uni"):
        from web.backend.services.uni_bridge import record_channel_spend

        spend = record_channel_spend(channel_id=channel_id, price_usd=amount_usd, ref=ref)
        if spend and spend.get("duplicate"):
            return {"ok": False, "error": "duplicate_spend"}
        if not spend or spend.get("error"):
            return {"ok": False, "error": spend.get("error", "insufficient_balance") if spend else "uni_unavailable"}
        remaining_uni = float(spend.get("remaining_uni") or 0)
        ch["balance_usd"] = round(uni_to_usd(remaining_uni), 4)
        ch["balance_uni"] = remaining_uni
    else:
        bal = float(ch.get("balance_usd") or 0)
        if amount_usd > bal + 1e-9:
            return {"ok": False, "error": "insufficient_balance"}
        ch["balance_usd"] = round(bal - amount_usd, 4)

    ch["spent_usd"] = round(float(ch.get("spent_usd") or 0) + amount_usd, 4)
    ch.setdefault("ledger", []).append(
        {"time": time.time(), "amount_usd": amount_usd, "ref": ref, "type": "debit"}
    )
    data[channel_id] = ch
    _save_channels(data)
    return {"ok": True, "channel": ch}


def refund_channel(channel_id: str, amount_usd: float, *, ref: str) -> dict[str, Any]:
    data = _load_channels()
    ch = data.get(channel_id)
    if not ch:
        return {"ok": False, "error": "channel_not_found"}
    ch["balance_usd"] = round(float(ch.get("balance_usd") or 0) + amount_usd, 4)
    ch["spent_usd"] = round(max(0, float(ch.get("spent_usd") or 0) - amount_usd), 4)
    ch.setdefault("ledger", []).append(
        {"time": time.time(), "amount_usd": amount_usd, "ref": ref, "type": "credit"}
    )
    data[channel_id] = ch
    _save_channels(data)
    return {"ok": True, "channel": ch}


def close_channel(
    *,
    channel_id: str,
    settle_tx_hash: str = "",
    customer_id: str = "",
) -> dict[str, Any]:
    data = _load_channels()
    ch = data.get(channel_id)
    if not ch:
        return {"error": "channel_not_found"}
    if ch.get("status") != "open":
        return {"error": "channel_already_closed"}
    owner = str(ch.get("customer_id") or "")
    if owner and customer_id and owner != customer_id:
        return {"error": "forbidden", "detail": "channel belongs to another customer"}
    if owner and not customer_id:
        return {"error": "customer_required", "detail": "customer authentication required"}

    refund = float(ch.get("balance_usd") or 0)
    used = float(ch.get("spent_usd") or 0)
    chain = str(ch.get("chain") or pilot_tuple()["chain"]).lower()
    token = str(ch.get("token") or pilot_tuple()["token"]).upper()

    settle_clean = (settle_tx_hash or "").strip()
    if demo_payment_bypass():
        if not settle_clean:
            settle_clean = f"demo-settle-{channel_id}"
    elif refund > 1e-9:
        if not settle_clean:
            return {"error": "settle_tx_hash_required", "detail": "refund settlement hash required"}
        settle_clean = normalize_tx_hash(settle_clean, chain=chain)
        if _tx_hash_already_used(settle_clean):
            return {"error": "tx_hash_already_used", "detail": "settlement transaction hash already used"}
        if not verify_tx_payment(tx_hash=settle_clean, amount_usd=refund, chain=chain, token=token):
            return {"error": "settle_tx_not_verified", "detail": "on-chain settlement not verified"}
    else:
        settle_clean = settle_clean or ""

    if uni_enabled() and ch.get("uni"):
        from web.backend.services.uni_bridge import record_channel_release

        released = record_channel_release(channel_id)
        if released and not released.get("error"):
            refund = float(released.get("refund_uni") or 0)
            refund = uni_to_usd(refund)
            ch["balance_usd"] = round(refund, 4)

    ch["status"] = "closed"
    ch["closed_at"] = time.time()
    ch["refund_usd"] = round(refund, 4)
    ch["settle_tx_hash"] = settle_clean
    data[channel_id] = ch
    _save_channels(data)
    receipt = {
        "channel_id": channel_id,
        "used_usd": round(used, 4),
        "refund_usd": round(refund, 4),
        "settle_tx_hash": ch["settle_tx_hash"],
    }
    receipt["signature"] = sign_payload(receipt)
    return {"channel": ch, "settlement": receipt, "protocol_version": "v1"}
