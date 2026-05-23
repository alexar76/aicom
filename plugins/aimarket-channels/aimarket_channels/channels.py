"""DEPRECATED — use aimarket_hub.channels instead.

This standalone plugin is outdated (in-memory, float math, no rate limiting).
The canonical implementation lives in aimarket-hub/aimarket_hub/channels.py
(SQLite-backed, integer cents, rate limiting, background sweep, env config).

Kept for reference only. Do not install in production.
"""

from __future__ import annotations

import time
import uuid
from typing import Any


class ChannelLedger:
    """In-memory payment channel ledger.

    In production, this would be backed by an on-chain contract.
    Here it's a simple dict for the reference implementation.
    """

    def __init__(self):
        self._channels: dict[str, dict[str, Any]] = {}

    def open(
        self,
        deposit_usd: float,
        token: str = "USDT",
        chain: str = "base",
        wallet: str = "",
        tx_hash: str = "",
    ) -> dict[str, Any]:
        """Open a pre-funded payment channel."""
        if deposit_usd <= 0 or deposit_usd > 10_000:
            return {"error": "deposit must be between 0 and 10,000 USD"}

        channel_id = f"ch_{uuid.uuid4().hex[:12]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        channel = {
            "channel_id": channel_id,
            "balance_usd": deposit_usd,
            "original_deposit_usd": deposit_usd,
            "used_usd": 0.0,
            "token": token,
            "chain": chain,
            "wallet": wallet,
            "tx_hash": tx_hash,
            "status": "open",
            "opened_at": now,
            "expires_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400)
            ),  # 24h expiry
        }
        self._channels[channel_id] = channel
        return {"channel": channel}

    def close(self, channel_id: str, settle_tx_hash: str = "") -> dict[str, Any]:
        """Close a channel and compute settlement."""
        channel = self._channels.get(channel_id)
        if not channel:
            return {"error": "channel not found"}
        if channel["status"] != "open":
            return {"error": f"channel is {channel['status']}"}

        channel["status"] = "settled"
        channel["settle_tx_hash"] = settle_tx_hash
        channel["closed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        refund = channel["balance_usd"]
        return {
            "settlement": {
                "channel_id": channel_id,
                "used_usd": channel["used_usd"],
                "refund_usd": refund,
                "original_deposit_usd": channel["original_deposit_usd"],
                "status": "settled",
                "settle_tx_hash": settle_tx_hash,
            }
        }

    def debit(self, channel_id: str, amount_usd: float) -> dict[str, Any]:
        """Deduct from a channel (called during invoke)."""
        channel = self._channels.get(channel_id)
        if not channel:
            return {"error": "channel not found"}
        if channel["status"] != "open":
            return {"error": "channel not open"}
        if amount_usd > channel["balance_usd"]:
            return {"error": "insufficient balance", "needed": amount_usd, "balance": channel["balance_usd"]}

        channel["balance_usd"] -= amount_usd
        channel["used_usd"] += amount_usd
        return {"ok": True, "channel_id": channel_id, "remaining_balance": channel["balance_usd"]}

    def refund(self, channel_id: str, amount_usd: float) -> dict[str, Any]:
        """Refund to a channel (on failure/abort)."""
        channel = self._channels.get(channel_id)
        if not channel:
            return {"error": "channel not found"}

        channel["balance_usd"] += amount_usd
        channel["used_usd"] = max(0.0, channel["used_usd"] - amount_usd)
        return {"ok": True, "channel_id": channel_id, "remaining_balance": channel["balance_usd"]}

    def get(self, channel_id: str) -> dict[str, Any] | None:
        return self._channels.get(channel_id)


# Global ledger instance for the hub
_ledger = ChannelLedger()


def open_channel(
    deposit_usd: float,
    token: str | None = None,
    chain: str | None = None,
    wallet: str = "",
    tx_hash: str = "",
) -> dict[str, Any]:
    return _ledger.open(
        deposit_usd=deposit_usd,
        token=token or "USDT",
        chain=chain or "base",
        wallet=wallet,
        tx_hash=tx_hash,
    )


def close_channel(channel_id: str, settle_tx_hash: str = "") -> dict[str, Any]:
    return _ledger.close(channel_id, settle_tx_hash=settle_tx_hash)


def debit_channel(channel_id: str, amount_usd: float) -> dict[str, Any]:
    return _ledger.debit(channel_id, amount_usd)


def refund_channel(channel_id: str, amount_usd: float) -> dict[str, Any]:
    return _ledger.refund(channel_id, amount_usd)
