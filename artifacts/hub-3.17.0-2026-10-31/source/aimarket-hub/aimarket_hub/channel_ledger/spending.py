"""Spending from an open channel: debits, holds and their capture or release, refunds, and the
channel's balance and statistics.
"""

from __future__ import annotations

import hmac
import math
from typing import Any


def _move(conn: Any, sql: str, params: tuple) -> bool:
    """Run one conditional UPDATE; True when it matched exactly one row.

    Every money move on a channel is a single statement whose WHERE re-checks what the
    caller read (still open, enough balance, hold still held), so the database decides
    against the row as it is at write time. The ledger's lock serializes one process only:
    with two ledgers on one database (two hub workers, or a CLI beside the server) the
    old read-then-write lost half of 240 concurrent debits, and a close racing a debit
    booked the whole deposit as owed after 30 cents of it were spent (tested in
    tests/test_channel_ledger_races.py). On a miss the transaction is rolled back here.
    Each call runs on the connection's own `get_connection()`, so rowcount is this
    statement's alone.
    """
    cur = conn.execute(sql, params)
    if getattr(cur, "rowcount", 0) == 1:
        return True
    conn.rollback()
    return False


def _insert_once(conn: Any, sql: str, params: tuple) -> bool:
    """INSERT a row keyed by a receipt id; False (rolled back) when another writer has it."""
    try:
        conn.execute(sql, params)
    except Exception as exc:
        msg = str(exc).lower()
        if not any(k in msg for k in ("unique", "constraint", "duplicate")):
            raise
        conn.rollback()
        return False
    return True


def _balance_cents(conn: Any, channel_id: str) -> int:
    row = conn.execute(
        "SELECT balance_cents FROM channels WHERE channel_id = ?", (channel_id,),
    ).fetchone()
    return int(row["balance_cents"]) if row else 0


def _lost_race(conn: Any, channel_id: str, amount_usd: float) -> dict[str, Any]:
    """Why a debit or hold matched no row: the channel changed after it was read."""
    row = conn.execute(
        "SELECT status, balance_cents FROM channels WHERE channel_id = ?", (channel_id,),
    ).fetchone()
    if not row:
        return {"error": "channel not found"}
    if row["status"] != "open":
        return {"error": "channel not open"}
    return {
        "error": "insufficient balance",
        "needed": amount_usd,
        "balance": channels._cents_to_dollars(row["balance_cents"]),
    }


class LedgerSpendingMixin:
    """Debits, holds, refunds, balances and statistics."""

    def debit(
        self,
        channel_id: str,
        amount_usd: float,
        receipt_id: str = "",
        requester_wallet: str = "",
        secret: str = "",
    ) -> dict[str, Any]:
        """Deduct from a channel (called during invoke).

        Args:
            receipt_id: Unique ID for replay protection.
            requester_wallet: authenticated caller wallet (defense-in-depth; must match owner
                when supplied).
            secret: the per-channel debit secret returned at open. Always required;
                legacy channels with no stored hash fail closed.
        """
        # Bill with a ceiling so a positive sub-cent price is never served free.
        amount_cents = channels._dollars_to_cents_bill(amount_usd)
        # Replay protection is a property of the function, not of its callers: a debit that
        # moves money must name the operation it pays for, so a retried or duplicated request
        # cannot be charged twice. (Every caller passes one today; this keeps it that way.)
        if amount_cents > 0 and not receipt_id:
            return {"error": "receipt_id is required for a debit"}

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": "channel not open"}

            # A channel id or public wallet cannot authorize spending. No stored secret
            # means ownership cannot be proved, so legacy channels must fail closed.
            stored_hash = (row["secret_hash"] if "secret_hash" in row.keys() else "") or ""
            if not stored_hash or not secret or not hmac.compare_digest(stored_hash, channels._hash_secret(secret)):
                return {"error": "unauthorized: invalid or missing channel secret"}

            # Defense-in-depth: if the caller's wallet is known, it must own the channel.
            if requester_wallet and row["wallet"] and not channels._wallet_matches(
                row["wallet"], requester_wallet
            ):
                return {"error": "unauthorized: wallet does not match channel owner"}

            balance_cents = row["balance_cents"]
            if amount_cents > balance_cents:
                return {
                    "error": "insufficient balance",
                    "needed": amount_usd,
                    "balance": channels._cents_to_dollars(balance_cents),
                }

            # Replay protection
            if receipt_id:
                existing = conn.execute(
                    "SELECT 1 FROM debited_receipts WHERE receipt_id = ?",
                    (receipt_id,),
                ).fetchone()
                if existing:
                    return {"error": "receipt already processed (replay rejected)"}
                if not _insert_once(
                    conn,
                    "INSERT INTO debited_receipts (receipt_id, channel_id, amount_cents, timestamp) "
                    "VALUES (?, ?, ?, ?)",
                    (receipt_id, channel_id, amount_cents, channels._now_iso()),
                ):
                    return {"error": "receipt already processed (replay rejected)"}

            # One conditional statement moves the money (see _move).
            if not _move(
                conn,
                "UPDATE channels SET balance_cents = balance_cents - ?, used_cents = used_cents + ? "
                "WHERE channel_id = ? AND status = 'open' AND balance_cents >= ?",
                (amount_cents, amount_cents, channel_id, amount_cents),
            ):
                return _lost_race(conn, channel_id, amount_usd)
            new_balance = _balance_cents(conn, channel_id)
            conn.commit()

            remaining = channels._cents_to_dollars(new_balance)

        return {"ok": True, "channel_id": channel_id, "remaining_balance": remaining}

    def hold(
        self,
        channel_id: str,
        amount_usd: float,
        receipt_id: str,
        requester_wallet: str = "",
        secret: str = "",
    ) -> dict[str, Any]:
        """Reserve funds for a Pay-on-Verified invoke (auth leg of auth/capture).

        Same authorization as debit (channel secret + wallet defense) — the buyer
        authorizes the reservation while their secret is in-request, so the later
        capture/release can run from a background worker WITHOUT the secret.
        Balance drops immediately: a pending verification can never be double-spent.
        """
        if not receipt_id:
            return {"error": "receipt_id is required for a hold"}
        amount_cents = channels._dollars_to_cents_bill(amount_usd)

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": "channel not open"}

            stored_hash = (row["secret_hash"] if "secret_hash" in row.keys() else "") or ""
            if not stored_hash or not secret or not hmac.compare_digest(stored_hash, channels._hash_secret(secret)):
                return {"error": "unauthorized: invalid or missing channel secret"}
            if requester_wallet and row["wallet"] and not channels._wallet_matches(
                row["wallet"], requester_wallet
            ):
                return {"error": "unauthorized: wallet does not match channel owner"}

            balance_cents = row["balance_cents"]
            if amount_cents > balance_cents:
                return {
                    "error": "insufficient balance",
                    "needed": amount_usd,
                    "balance": channels._cents_to_dollars(balance_cents),
                }

            # Replay protection — a receipt nonce may be used by at most one
            # debit OR one hold, ever.
            for table in ("debited_receipts", "channel_holds"):
                existing = conn.execute(
                    f"SELECT 1 FROM {table} WHERE receipt_id = ?", (receipt_id,)
                ).fetchone()
                if existing:
                    return {"error": "receipt already processed (replay rejected)"}

            if not _insert_once(
                conn,
                "INSERT INTO channel_holds (receipt_id, channel_id, amount_cents, status, created_at) "
                "VALUES (?, ?, ?, 'held', ?)",
                (receipt_id, channel_id, amount_cents, channels._now_iso()),
            ):
                return {"error": "receipt already processed (replay rejected)"}
            if not _move(
                conn,
                "UPDATE channels SET balance_cents = balance_cents - ? "
                "WHERE channel_id = ? AND status = 'open' AND balance_cents >= ?",
                (amount_cents, channel_id, amount_cents),
            ):
                return _lost_race(conn, channel_id, amount_usd)
            new_balance = _balance_cents(conn, channel_id)
            conn.commit()
            remaining = channels._cents_to_dollars(new_balance)

        return {
            "ok": True,
            "channel_id": channel_id,
            "remaining_balance": remaining,
            "held_usd": channels._cents_to_dollars(amount_cents),
        }

    def capture_hold(self, receipt_id: str) -> dict[str, Any]:
        """Capture a hold after a passing verdict: reservation becomes a recorded debit.

        No secret needed — the buyer pre-authorized the amount at hold time. Works
        regardless of current channel status (the cents were reserved while open).
        """
        with self._lock, self._get_conn() as conn:
            hold = conn.execute(
                "SELECT * FROM channel_holds WHERE receipt_id = ? AND status = 'held'",
                (receipt_id,),
            ).fetchone()
            if not hold:
                return {"error": "hold not found or already resolved"}

            # The hold changes state first and only if it is still held: a capture and a
            # release racing from two processes both read 'held', and without the condition
            # each moved the cents (into used AND back into balance), minting them.
            if not _move(
                conn,
                "UPDATE channel_holds SET status = 'captured', resolved_at = ? "
                "WHERE receipt_id = ? AND status = 'held'",
                (channels._now_iso(), receipt_id),
            ):
                return {"error": "hold not found or already resolved"}
            conn.execute(
                "INSERT INTO debited_receipts (receipt_id, channel_id, amount_cents, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (receipt_id, hold["channel_id"], hold["amount_cents"], channels._now_iso()),
            )
            conn.execute(
                "UPDATE channels SET used_cents = used_cents + ? WHERE channel_id = ?",
                (hold["amount_cents"], hold["channel_id"]),
            )
            conn.commit()

        return {
            "ok": True,
            "channel_id": hold["channel_id"],
            "captured_usd": channels._cents_to_dollars(hold["amount_cents"]),
        }

    def release_hold(self, receipt_id: str) -> dict[str, Any]:
        """Release a hold after a failing verdict: reservation returns to balance."""
        with self._lock, self._get_conn() as conn:
            hold = conn.execute(
                "SELECT * FROM channel_holds WHERE receipt_id = ? AND status = 'held'",
                (receipt_id,),
            ).fetchone()
            if not hold:
                return {"error": "hold not found or already resolved"}

            if not _move(
                conn,
                "UPDATE channel_holds SET status = 'released', resolved_at = ? "
                "WHERE receipt_id = ? AND status = 'held'",
                (channels._now_iso(), receipt_id),
            ):
                return {"error": "hold not found or already resolved"}
            conn.execute(
                "UPDATE channels SET balance_cents = balance_cents + ? WHERE channel_id = ?",
                (hold["amount_cents"], hold["channel_id"]),
            )
            row = conn.execute(
                "SELECT balance_cents FROM channels WHERE channel_id = ?",
                (hold["channel_id"],),
            ).fetchone()
            conn.commit()

        return {
            "ok": True,
            "channel_id": hold["channel_id"],
            "released_usd": channels._cents_to_dollars(hold["amount_cents"]),
            "remaining_balance": channels._cents_to_dollars(row["balance_cents"] if row else 0),
        }

    def hold_state(self, receipt_id: str) -> str:
        """The status of one hold ('held' / 'captured' / 'released' / 'reaped'), or "".

        capture_hold/release_hold answer "already resolved" without saying HOW. A settlement
        re-run after a crash between moving the money and recording the verdict needs the
        difference: a hold its own earlier attempt already captured is settled, a hold
        something else released is a ledger fault to report — not the same envelope.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM channel_holds WHERE receipt_id = ?", (receipt_id,),
            ).fetchone()
        return str(row["status"]) if row else ""

    def secret_error(self, channel_id: str, secret: str) -> str:
        """"" when `secret` is this channel's debit secret, else why not.

        Uses the same fail-closed policy as debit/hold/close/refund: a channel without
        a stored secret cannot authenticate its owner, including for an appeal bond.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,),
            ).fetchone()
        if not row:
            return "channel not found"
        stored = (row["secret_hash"] if "secret_hash" in row.keys() else "") or ""
        if not stored:
            return "this channel has no debit secret, so its owner cannot be authenticated"
        if not secret or not hmac.compare_digest(stored, channels._hash_secret(secret)):
            return "invalid or missing channel secret"
        return ""

    def refund(
        self,
        channel_id: str,
        amount_usd: float,
        requester_wallet: str = "",
        secret: str = "",
    ) -> dict[str, Any]:
        """Reverse a recorded debit back into the channel's spendable balance.

        In-ledger correction only — no funds move. Only allowed on open channels.

        Authorization mirrors debit(): a stored secret and its matching credential are
        required, and a supplied requester_wallet must own the channel.
        Without that, the only thing standing between a leaked channel id and a
        rewritten balance was the deposit cap.
        """
        try:
            amount_usd = float(amount_usd)
        except (TypeError, ValueError):
            return {"error": "refund amount must be a number"}
        if not math.isfinite(amount_usd):
            return {"error": "refund amount must be a finite number"}
        amount_cents = channels._dollars_to_cents(amount_usd)

        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
            if not row:
                return {"error": "channel not found"}
            if row["status"] != "open":
                return {"error": f"channel is {row['status']} — refund only allowed on open channels"}

            stored_hash = (row["secret_hash"] if "secret_hash" in row.keys() else "") or ""
            if not stored_hash or not secret or not hmac.compare_digest(stored_hash, channels._hash_secret(secret)):
                return {"error": "unauthorized: invalid or missing channel secret"}
            if requester_wallet and row["wallet"] and not channels._wallet_matches(
                row["wallet"], requester_wallet
            ):
                return {"error": "unauthorized: wallet does not match channel owner"}

            # Cap at what was actually SPENT. `original - balance` (the old cap) also
            # counted cents reserved by an unresolved hold: refunding those put them back
            # in the spendable balance while the hold could still be captured, minting
            # value the deposit never covered.
            max_refund = row["used_cents"]
            amount_cents = min(amount_cents, max_refund)
            if amount_cents <= 0:
                return {"error": "refund amount would exceed recorded spend"}

            if not _move(
                conn,
                "UPDATE channels SET balance_cents = balance_cents + ?, used_cents = used_cents - ? "
                "WHERE channel_id = ? AND status = 'open' AND used_cents >= ?",
                (amount_cents, amount_cents, channel_id, amount_cents),
            ):
                current = conn.execute(
                    "SELECT status FROM channels WHERE channel_id = ?", (channel_id,),
                ).fetchone()
                if current and current["status"] != "open":
                    return {"error": f"channel is {current['status']} — refund only allowed on open channels"}
                return {"error": "refund amount would exceed recorded spend"}
            new_balance = _balance_cents(conn, channel_id)
            conn.commit()

            remaining = channels._cents_to_dollars(new_balance)

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
                "balance_usd": channels._cents_to_dollars(row["balance_cents"]),
                "original_deposit_usd": channels._cents_to_dollars(row["original_deposit_cents"]),
                "used_usd": channels._cents_to_dollars(row["used_cents"]),
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

    def recorded_spend_usd(self, wallet: str) -> float | None:
        """Total USD the ledger has actually debited across a wallet's channels.

        Returns None when the wallet owns no channels on record — i.e. the hub
        holds no settlement data for it. Used to ground self-bond slashing in
        hub-recorded settlement rather than a caller-supplied number.

        EVM addresses are compared case-insensitively: since deposit binding stores the
        VERIFIER's rendering of the payer (EIP-55 checksummed), an exact match against a
        self-bond that registered the same address in lower case found nothing and the
        slash route refused every real production channel with "no hub-recorded
        settlement". Case is significant for base58 ids, which stay exact.
        """
        wallet = (wallet or "").strip()
        if not wallet:
            return None
        with self._get_conn() as conn:
            if channels._is_evm_address(wallet):
                row = conn.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                    "FROM channels WHERE LOWER(wallet) = ?",
                    (wallet.lower(),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                    "FROM channels WHERE wallet = ?",
                    (wallet,),
                ).fetchone()
        if not row or not row["n"]:
            return None
        return channels._cents_to_dollars(row["used"])

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics.

        Volume is reported for expired channels too: summing used_cents only over
        'settled' rows silently dropped everything spent through a channel that timed
        out instead of being closed, understating real settled volume.
        """
        with self._get_conn() as conn:
            open_row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                "FROM channels WHERE status = 'open'"
            ).fetchone()
            settled = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                "FROM channels WHERE status = 'settled'"
            ).fetchone()
            expired = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(used_cents), 0) AS used "
                "FROM channels WHERE status = 'expired'"
            ).fetchone()
        owed = self.obligations_total("owed")

        settled_cents = int(settled["used"] or 0)
        expired_cents = int(expired["used"] or 0)
        closed_cents = settled_cents + expired_cents
        return {
            "open_channels": int(open_row["n"] or 0),
            "open_used_cents": int(open_row["used"] or 0),
            "settled_channels": int(settled["n"] or 0),
            "settled_volume_cents": settled_cents,
            "settled_volume_usd": channels._cents_to_dollars(settled_cents),
            "expired_channels": int(expired["n"] or 0),
            "expired_volume_cents": expired_cents,
            "expired_volume_usd": channels._cents_to_dollars(expired_cents),
            "closed_volume_cents": closed_cents,
            "closed_volume_usd": channels._cents_to_dollars(closed_cents),
            "outstanding_obligations": owed["count"],
            "outstanding_obligations_usd": owed["total_usd"],
            "max_channels": self._max_channels,
        }


# Imported after the class on purpose: methods read aimarket_hub.channels at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import channels  # noqa: E402
