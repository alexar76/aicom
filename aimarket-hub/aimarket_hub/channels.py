"""Pre-funded payment channels for off-chain capability invocation.

Implements channel/open, channel/close from Protocol v1/v2 spec.

Storage: SQLite-backed (survives process restart).
Amounts: integer cents internally (no IEEE 754 drift).
Rate limiting: per-wallet caps on open/close.
Background sweep: auto-refunds expired channels every 5 min.

In production, channel state is mirrored on-chain via AIMarketEscrow contract.
The ledger holds authoritative state; the contract holds funds in escrow.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Env-driven defaults ──────────────────────────────────────────

_DEFAULT_CHAIN = os.getenv("AIMARKET_PAYMENT_CHAIN", "base")
_DEFAULT_TOKEN = os.getenv("AIMARKET_PAYMENT_TOKEN", "USDT")
_RECIPIENT = os.getenv("AIMARKET_PAYMENT_RECIPIENT", "")
_VERIFY_STUB = os.getenv("AIFACTORY_PAYMENT_VERIFY_STUB", "0") == "1"
_MIN_CONFIRMATIONS = int(os.getenv("AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "2"))
_DB_PATH = os.getenv("AIMARKET_CHANNELS_DB_PATH", "data/channels.db")

# Rate limits
_MAX_OPENS_PER_WALLET_PER_HOUR = 20
_MAX_CLOSES_PER_WALLET_PER_HOUR = 60
_DEFAULT_MAX_CHANNELS = 10_000
_CHANNEL_EXPIRY_SECS = 86400  # 24h
_SWEEP_INTERVAL_SECS = 300     # 5 min

# Cents per USD (no floats for money)
_CENTS_PER_USD = 100


def _validate_recipient() -> None:
    if not _RECIPIENT:
        logger.warning(
            "AIMARKET_PAYMENT_RECIPIENT is not set. "
            "Payment channels will work in demo mode but real USDT/USDC "
            "transfers will fail. Set it in .env or environment."
        )


_validate_recipient()


# ── Helpers ──────────────────────────────────────────────────────

def _dollars_to_cents(usd: float) -> int:
    return round(usd * _CENTS_PER_USD)


def _cents_to_dollars(cents: int) -> float:
    return cents / _CENTS_PER_USD


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expiry_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _CHANNEL_EXPIRY_SECS))


# ── SQLite Channel Ledger ────────────────────────────────────────

class ChannelLedger:
    """Payment channel ledger — SQLite or PostgreSQL via DATABASE_URL.

    All amounts stored as integer cents. Public API accepts float USD
    and returns float USD for backward compatibility.
    """

    def __init__(self, db_path: str = "", database_url: str = ""):
        from aimarket_hub.db_backend import create_backend
        from aimarket_hub.migrations import Migrations

        self._backend = create_backend(
            database_url=database_url,
            db_path=db_path or _DB_PATH,
        )
        self._lock = threading.Lock()
        self._rate_state: dict[str, list[float]] = {}  # wallet -> [open_timestamps]
        self._close_rate: dict[str, list[float]] = {}   # wallet -> [close_timestamps]
        self._max_channels = _DEFAULT_MAX_CHANNELS
        self._sweep_thread: threading.Thread | None = None
        self._running = False
        Migrations(self._backend).apply(target_version=4)
        self._start_sweep()

    # ── Database ──────────────────────────────────────────────────

    def _init_db(self) -> None:
        pass  # Handled by Migrations in __init__

    def _legacy_init_db(self) -> None:
        self._backend.dir.mkdir(parents=True, exist_ok=True) if hasattr(self._backend, 'dir') else None
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    balance_cents INTEGER NOT NULL,
                    original_deposit_cents INTEGER NOT NULL,
                    used_cents INTEGER NOT NULL DEFAULT 0,
                    token TEXT NOT NULL DEFAULT 'USDT',
                    chain TEXT NOT NULL DEFAULT 'base',
                    wallet TEXT NOT NULL DEFAULT '',
                    tx_hash TEXT NOT NULL DEFAULT '',
                    recipient TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    opened_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    settle_tx_hash TEXT NOT NULL DEFAULT '',
                    closed_at TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debited_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_status
                ON channels(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_wallet
                ON channels(wallet)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_expires
                ON channels(expires_at) WHERE status = 'open'
            """)
            conn.commit()

    def _get_conn(self):
        """Return a context-managed DB connection (SQLite or PG)."""
        return self._backend.get_connection()

    # ── Rate limiting ─────────────────────────────────────────────

    def _check_rate(self, wallet: str, rate_store: dict[str, list[float]],
                    max_per_hour: int) -> bool:
        """Return True if within rate limit, False if exceeded."""
        if not wallet:
            return True  # anonymous channels not rate-limited
        now = time.time()
        window = now - 3600
        rate_store[wallet] = [t for t in rate_store.get(wallet, []) if t > window]
        if len(rate_store[wallet]) >= max_per_hour:
            return False
        rate_store[wallet].append(now)
        return True

    # ── Background sweep ──────────────────────────────────────────

    def _start_sweep(self) -> None:
        """Start a background thread that sweeps expired channels."""
        self._running = True
        self._sweep_thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._sweep_thread.start()

    def _sweep_loop(self) -> None:
        while self._running:
            time.sleep(_SWEEP_INTERVAL_SECS)
            try:
                self._sweep_expired()
            except Exception as exc:
                logger.error("Channel sweep error: %s", exc)

    def _sweep_expired(self) -> int:
        """Auto-refund all expired open channels. Returns count."""
        now = _now_iso()
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(
                "SELECT channel_id, balance_cents, used_cents, wallet "
                "FROM channels WHERE status = 'open' AND expires_at < ?",
                (now,),
            ).fetchall()

            count = 0
            for row in rows:
                total_cents = row["balance_cents"] + row["used_cents"]
                conn.execute(
                    "UPDATE channels SET status = 'expired', closed_at = ? "
                    "WHERE channel_id = ?",
                    (now, row["channel_id"]),
                )
                count += 1
                logger.info(
                    "Channel %s expired — %d cents refunded to %s",
                    row["channel_id"], total_cents, row["wallet"][:10] or "anonymous",
                )

            if count:
                conn.commit()
                logger.info("Swept %d expired channels", count)
            return count

    def stop_sweep(self) -> None:
        self._running = False

    # ── Channel operations ────────────────────────────────────────

    def open(
        self,
        deposit_usd: float,
        token: str = "",
        chain: str = "",
        wallet: str = "",
        tx_hash: str = "",
    ) -> dict[str, Any]:
        """Open a pre-funded payment channel."""
        if deposit_usd <= 0 or deposit_usd > 10_000:
            return {"error": "deposit must be between 0 and 10,000 USD"}

        if not self._check_rate(wallet, self._rate_state, _MAX_OPENS_PER_WALLET_PER_HOUR):
            return {"error": "rate limit exceeded — max 20 channel opens per hour per wallet"}

        deposit_cents = _dollars_to_cents(deposit_usd)
        token = token or _DEFAULT_TOKEN
        chain = chain or _DEFAULT_CHAIN

        with self._lock, self._get_conn() as conn:
            # DoS check
            open_count = conn.execute(
                "SELECT COUNT(*) FROM channels WHERE status = 'open'"
            ).fetchone()[0]
            if open_count >= self._max_channels:
                return {"error": "too many open channels, try again later"}

            channel_id = f"ch_{uuid.uuid4().hex[:16]}"
            now = _now_iso()
            expires = _expiry_iso()

            conn.execute(
                """INSERT INTO channels
                   (channel_id, balance_cents, original_deposit_cents, used_cents,
                    token, chain, wallet, tx_hash, recipient, status,
                    opened_at, expires_at)
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (channel_id, deposit_cents, deposit_cents,
                 token, chain, wallet, tx_hash, _RECIPIENT, now, expires),
            )
            conn.commit()

            channel = dict(conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone())

        balance_usd = _cents_to_dollars(deposit_cents)
        return {"channel": {
            "channel_id": channel_id,
            "balance_usd": balance_usd,
            "original_deposit_usd": balance_usd,
            "used_usd": 0.0,
            "token": token,
            "chain": chain,
            "wallet": wallet,
            "tx_hash": tx_hash,
            "recipient": _RECIPIENT,
            "verify_stub": _VERIFY_STUB,
            "status": "open",
            "opened_at": now,
            "expires_at": expires,
        }}

    def close(
        self,
        channel_id: str,
        settle_tx_hash: str = "",
        wallet: str = "",
    ) -> dict[str, Any]:
        """Close a channel and compute settlement.

        Args:
            wallet: Must match the wallet that opened the channel.
        """
        if not self._check_rate(wallet, self._close_rate, _MAX_CLOSES_PER_WALLET_PER_HOUR):
            return {"error": "rate limit exceeded — max 60 close per hour per wallet"}

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": f"channel is {row['status']}"}

            # Authorization: wallet must match (anonymous channels cannot be closed by strangers)
            if row["wallet"] != wallet:
                return {"error": "unauthorized: wallet does not match channel owner"}

            now = _now_iso()
            conn.execute(
                "UPDATE channels SET status = 'settled', settle_tx_hash = ?, "
                "closed_at = ? WHERE channel_id = ?",
                (settle_tx_hash, now, channel_id),
            )
            conn.commit()

            used = _cents_to_dollars(row["used_cents"])
            refund = _cents_to_dollars(row["balance_cents"])
            original = _cents_to_dollars(row["original_deposit_cents"])

        return {
            "settlement": {
                "channel_id": channel_id,
                "used_usd": used,
                "refund_usd": refund,
                "original_deposit_usd": original,
                "status": "settled",
                "settle_tx_hash": settle_tx_hash,
            }
        }

    def debit(
        self,
        channel_id: str,
        amount_usd: float,
        receipt_id: str = "",
    ) -> dict[str, Any]:
        """Deduct from a channel (called during invoke).

        Args:
            receipt_id: Unique ID for replay protection.
        """
        amount_cents = _dollars_to_cents(amount_usd)

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": "channel not open"}

            balance_cents = row["balance_cents"]
            if amount_cents > balance_cents:
                return {
                    "error": "insufficient balance",
                    "needed": amount_usd,
                    "balance": _cents_to_dollars(balance_cents),
                }

            # Replay protection
            if receipt_id:
                existing = conn.execute(
                    "SELECT 1 FROM debited_receipts WHERE receipt_id = ?",
                    (receipt_id,),
                ).fetchone()
                if existing:
                    return {"error": "receipt already processed (replay rejected)"}
                conn.execute(
                    "INSERT INTO debited_receipts (receipt_id, channel_id, amount_cents, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (receipt_id, channel_id, amount_cents, _now_iso()),
                )

            new_balance = balance_cents - amount_cents
            new_used = row["used_cents"] + amount_cents
            conn.execute(
                "UPDATE channels SET balance_cents = ?, used_cents = ? "
                "WHERE channel_id = ?",
                (new_balance, new_used, channel_id),
            )
            conn.commit()

            remaining = _cents_to_dollars(new_balance)

        return {"ok": True, "channel_id": channel_id, "remaining_balance": remaining}

    def refund(self, channel_id: str, amount_usd: float) -> dict[str, Any]:
        """Refund to a channel (on failure/abort).

        Only allowed on open channels. Amount capped at original deposit
        minus current balance to prevent unbounded refund.
        """
        amount_cents = _dollars_to_cents(amount_usd)

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": f"channel is {row['status']} — refund only allowed on open channels"}

            # Cap refund at original deposit minus current balance
            max_refund = row["original_deposit_cents"] - row["balance_cents"]
            amount_cents = min(amount_cents, max_refund)
            if amount_cents <= 0:
                return {"error": "refund amount would exceed original deposit"}

            new_balance = row["balance_cents"] + amount_cents
            new_used = max(0, row["used_cents"] - amount_cents)
            conn.execute(
                "UPDATE channels SET balance_cents = ?, used_cents = ? "
                "WHERE channel_id = ?",
                (new_balance, new_used, channel_id),
            )
            conn.commit()

            remaining = _cents_to_dollars(new_balance)

        return {"ok": True, "channel_id": channel_id, "remaining_balance": remaining}

    def get(self, channel_id: str) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "channel_id": row["channel_id"],
                "balance_usd": _cents_to_dollars(row["balance_cents"]),
                "original_deposit_usd": _cents_to_dollars(row["original_deposit_cents"]),
                "used_usd": _cents_to_dollars(row["used_cents"]),
                "token": row["token"],
                "chain": row["chain"],
                "wallet": row["wallet"],
                "tx_hash": row["tx_hash"],
                "recipient": row["recipient"],
                "status": row["status"],
                "opened_at": row["opened_at"],
                "expires_at": row["expires_at"],
                "settle_tx_hash": row["settle_tx_hash"],
                "closed_at": row["closed_at"],
            }

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        with self._get_conn() as conn:
            open_count = conn.execute(
                "SELECT COUNT(*) FROM channels WHERE status = 'open'"
            ).fetchone()[0]
            settled = conn.execute(
                "SELECT COUNT(*), SUM(used_cents) FROM channels WHERE status = 'settled'"
            ).fetchone()
            expired = conn.execute(
                "SELECT COUNT(*) FROM channels WHERE status = 'expired'"
            ).fetchone()[0]

        return {
            "open_channels": open_count,
            "settled_channels": settled[0] or 0,
            "settled_volume_cents": settled[1] or 0,
            "settled_volume_usd": _cents_to_dollars(settled[1] or 0),
            "expired_channels": expired,
            "max_channels": self._max_channels,
        }


# ── Global instance ──────────────────────────────────────────────

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
        token=token or _DEFAULT_TOKEN,
        chain=chain or _DEFAULT_CHAIN,
        wallet=wallet,
        tx_hash=tx_hash,
    )


def close_channel(channel_id: str, settle_tx_hash: str = "", wallet: str = "") -> dict[str, Any]:
    return _ledger.close(channel_id, settle_tx_hash=settle_tx_hash, wallet=wallet)


def debit_channel(channel_id: str, amount_usd: float, receipt_id: str = "") -> dict[str, Any]:
    return _ledger.debit(channel_id, amount_usd, receipt_id=receipt_id)


def refund_channel(channel_id: str, amount_usd: float) -> dict[str, Any]:
    return _ledger.refund(channel_id, amount_usd)


def channel_stats() -> dict[str, Any]:
    return _ledger.stats()
