"""Pre-funded payment channels (off-chain ledger, on-chain settle)."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any

from core.uni.config import uni_enabled
from core.uni.pricing import uni_to_usd
from web.backend.services.ai_market_protocol.config import demo_payment_bypass, pilot_tuple
from web.backend.services.ai_market_protocol.on_chain import normalize_tx_hash, verify_tx_payment
from web.backend.services.ai_market_protocol.paths import channels_path
from web.backend.services.ai_market_protocol.signing import sign_payload
from web.backend.services.commerce import CommerceService

_commerce = CommerceService()

logger = logging.getLogger(__name__)

# In-process serialization of the channel store. Combined with an OS file lock
# (flock) below, this makes load→modify→save atomic across threads AND processes
# (FastAPI runs sync handlers in a threadpool; deployments run multiple workers).
# Without it two concurrent deduct_channel() calls double-spend a channel balance.
_STORE_LOCK = threading.RLock()


@contextmanager
def channel_store_lock():
    """Hold an exclusive process- and cross-process lock on the channel store.

    Wrap every read-modify-write sequence in this so balance checks and writes
    are atomic. Network/on-chain verification should happen *outside* the lock.
    """
    p = channels_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.parent / (p.name + ".lock")
    with _STORE_LOCK:
        with open(lock_path, "a+") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)


def _load_channels() -> dict[str, Any]:
    p = channels_path()
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Never silently return {} for a corrupt-but-present store: a subsequent
        # save would wipe every channel (and every real balance). Abort instead.
        logger.error("channel store at %s is corrupt: %s", p, e)
        raise RuntimeError("channel store is corrupt; refusing to overwrite") from e
    return data if isinstance(data, dict) else {}


def _save_channels(data: dict[str, Any]) -> None:
    # Atomic write: a crash mid-write can't truncate/corrupt the live store.
    p = channels_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.parent / (p.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


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
    with channel_store_lock():
        # Re-check the deposit tx hash inside the lock to close the TOCTOU where two
        # concurrent opens reuse one on-chain deposit (and to avoid clobbering a
        # channel another worker just inserted).
        if tx_clean and not tx_clean.startswith("demo-") and _tx_hash_already_used(tx_clean):
            return {"error": "tx_hash_already_used", "detail": "transaction hash already used"}
        data = _load_channels()
        data[ch_id] = channel

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

        _save_channels(data)

    channel["signature"] = sign_payload(
        {"channel_id": ch_id, "deposit_usd": channel["deposit_usd"], "created_at": now}
    )
    return {"channel": channel, "protocol_version": "v1"}


def get_channel(channel_id: str) -> dict[str, Any] | None:
    return _load_channels().get(channel_id)


def deduct_channel(channel_id: str, amount_usd: float, *, ref: str) -> dict[str, Any]:
    # Whole balance check→debit→persist runs under the store lock so concurrent
    # invokes on the same channel cannot double-spend (see C1/H3).
    with channel_store_lock():
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
    with channel_store_lock():
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
    snapshot = _load_channels().get(channel_id)
    if not snapshot:
        return {"error": "channel_not_found"}
    if snapshot.get("status") != "open":
        return {"error": "channel_already_closed"}
    owner = str(snapshot.get("customer_id") or "")
    if owner and customer_id and owner != customer_id:
        return {"error": "forbidden", "detail": "channel belongs to another customer"}
    if owner and not customer_id:
        return {"error": "customer_required", "detail": "customer authentication required"}

    refund = float(snapshot.get("balance_usd") or 0)
    chain = str(snapshot.get("chain") or pilot_tuple()["chain"]).lower()
    token = str(snapshot.get("token") or pilot_tuple()["token"]).upper()

    # On-chain settlement verification (network I/O) runs OUTSIDE the store lock.
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

    # Re-load + re-check status under the lock so a concurrent close can't settle twice.
    with channel_store_lock():
        data = _load_channels()
        ch = data.get(channel_id)
        if not ch:
            return {"error": "channel_not_found"}
        if ch.get("status") != "open":
            return {"error": "channel_already_closed"}

        refund = float(ch.get("balance_usd") or 0)
        used = float(ch.get("spent_usd") or 0)

        if uni_enabled() and ch.get("uni"):
            from web.backend.services.uni_bridge import record_channel_release

            released = record_channel_release(channel_id)
            if released and not released.get("error"):
                refund = uni_to_usd(float(released.get("refund_uni") or 0))
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
