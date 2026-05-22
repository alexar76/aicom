"""Pre-funded payment channels (off-chain ledger, on-chain settle)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from web.backend.services.ai_market_protocol.config import demo_payment_bypass, pilot_tuple
from web.backend.services.ai_market_protocol.paths import channels_path
from web.backend.services.ai_market_protocol.signing import sign_payload


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


def open_channel(
    *,
    deposit_usd: float,
    token: str | None = None,
    chain: str | None = None,
    wallet: str = "",
    tx_hash: str = "",
) -> dict[str, Any]:
    cfg = pilot_tuple()
    token = (token or cfg["token"]).upper()
    chain = (chain or cfg["chain"]).lower()
    if deposit_usd <= 0 or deposit_usd > 10_000:
        return {"error": "invalid_deposit", "detail": "deposit must be in (0, 10000]"}
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
        "open_tx_hash": tx_hash or (f"demo-{ch_id}" if demo_payment_bypass() else ""),
        "status": "open",
        "created_at": now,
        "expires_at": now + 3600 * 24,
        "ledger": [],
    }
    data = _load_channels()
    data[ch_id] = channel
    _save_channels(data)
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


def close_channel(*, channel_id: str, settle_tx_hash: str = "") -> dict[str, Any]:
    data = _load_channels()
    ch = data.get(channel_id)
    if not ch:
        return {"error": "channel_not_found"}
    if ch.get("status") != "open":
        return {"error": "channel_already_closed"}
    refund = float(ch.get("balance_usd") or 0)
    used = float(ch.get("spent_usd") or 0)
    ch["status"] = "closed"
    ch["closed_at"] = time.time()
    ch["refund_usd"] = round(refund, 4)
    ch["settle_tx_hash"] = settle_tx_hash or (f"demo-settle-{channel_id}" if demo_payment_bypass() else "")
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
