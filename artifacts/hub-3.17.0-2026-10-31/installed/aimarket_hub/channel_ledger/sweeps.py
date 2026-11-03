"""Background work on the ledger: expiring channels, payout obligations to depositors,
unresolved settlements and stale holds.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Any

from aimarket_hub.paging import page_limit

logger = logging.getLogger("aimarket_hub.channels")


class LedgerSweepsMixin:
    """Expiry sweeps, payout obligations, unresolved settlements and stale holds."""

    # ── Background sweep ──────────────────────────────────────────

    def _start_sweep(self) -> None:
        """Start a background thread that sweeps expired channels."""
        self._running = True
        self._sweep_thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._sweep_thread.start()

    def _sweep_loop(self) -> None:
        while self._running:
            time.sleep(channels._SWEEP_INTERVAL_SECS)
            try:
                self._sweep_expired()
            except Exception as exc:
                logger.error("Channel sweep error: %s", exc)
            try:
                self.reap_stale_holds()
            except Exception as exc:
                logger.error("Channel hold-reaper error: %s", exc)

    def _sweep_expired(self) -> int:
        """Expire stale open channels, recording the unspent remainder as a payout
        obligation. Returns count.

        NOTE: nothing is transferred here — the deposit was paid to the platform's own
        settlement wallet, so the remainder is a DEBT to the depositor, not a refund
        this process can perform. The previous log line claimed "%d cents refunded",
        and the number it printed was balance + used (i.e. the whole deposit, including
        what the buyer actually spent).
        """
        now = channels._now_iso()
        with self._lock, self._get_conn() as conn:
            # Defer expiry of channels that still have a held Pay-on-Verified hold:
            # the reserved cents are in neither balance nor used, so expiring now
            # would strand them. The verified-settlement worker always resolves the
            # hold eventually (capture/release, or the reaper below), and a later
            # sweep pass then expires the channel with correct accounting. Mirrors
            # close()'s pending-holds guard.
            rows = conn.execute(
                "SELECT * FROM channels WHERE status = 'open' AND expires_at < ? "
                "AND channel_id NOT IN "
                "(SELECT channel_id FROM channel_holds WHERE status = 'held')",
                (now,),
            ).fetchall()

            count = 0
            for candidate in rows:
                channel_id = candidate["channel_id"]
                # Expire only if still open, and owe what the channel holds NOW: another
                # hub process may have debited or closed it since the scan. A hold placed
                # in between is seen here and the channel waits for a later pass.
                cur = conn.execute(
                    "UPDATE channels SET status = 'expired', closed_at = ? "
                    "WHERE channel_id = ? AND status = 'open'",
                    (now, channel_id),
                )
                if getattr(cur, "rowcount", 0) != 1:
                    continue
                held = conn.execute(
                    "SELECT COUNT(*) FROM channel_holds WHERE channel_id = ? AND status = 'held'",
                    (channel_id,),
                ).fetchone()[0]
                if held:
                    conn.execute(
                        "UPDATE channels SET status = 'open', closed_at = '' WHERE channel_id = ?",
                        (channel_id,),
                    )
                    continue
                row = conn.execute(
                    "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
                ).fetchone()
                obligation = self._record_payout_obligation(
                    conn, row, kind="expiry_remainder", now=now,
                )
                count += 1
                logger.info(
                    "Channel %s expired — %d cents unspent, %s (no funds moved)",
                    row["channel_id"], row["balance_cents"],
                    (
                        "recorded as payout obligation owed to %s"
                        % (row["wallet"][:10] or "an unidentified depositor")
                        if obligation else "nothing owed"
                    ),
                )

            conn.commit()
            if count:
                logger.info("Swept %d expired channels", count)
            return count

    # ── Payout obligations (honest accounting, never a transfer) ───

    def _record_payout_obligation(
        self, conn: Any, row: Any, *, kind: str, now: str,
    ) -> dict[str, Any] | None:
        """Record the channel's unspent remainder as an explicit debt to the depositor.

        Returns the obligation dict, or None when nothing is owed. Idempotent: the
        table is keyed by channel_id, so a re-run (close after a crashed close, or a
        second sweep pass) cannot double-book the same remainder.

        Only balance_cents is owed — used_cents was genuinely spent on delivered
        invokes, and held cents belong to an unresolved hold (callers guarantee there
        are none at this point).

        Escrow-funded channels record NOTHING. The debt exists because on the transfer
        path the deposit landed in the platform's settlement wallet, so the operator
        physically holds money that is not theirs. An escrow channel is the opposite:
        the deposit never leaves AIMarketEscrow, and `settleChannel` pays the remainder
        straight back to the depositor from the contract. Booking a debt there invents
        one — the live hub was publishing `outstanding_obligations_usd: 3.84` as its
        public solvency figure while all four remainders had already been returned
        on-chain (two Settled, two Refunded). Real debt was zero.
        """
        remainder = int(row["balance_cents"] or 0)
        if remainder <= 0:
            return None
        if str(row["escrow_channel"] or "").strip():
            logger.info(
                "channel %s is escrow-funded — the contract returns the remainder, "
                "no operator obligation recorded", row["channel_id"],
            )
            return None
        channel_id = row["channel_id"]
        existing = conn.execute(
            "SELECT * FROM channel_payout_obligations WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if existing:
            return self._obligation_dict(existing)
        try:
            conn.execute(
                "INSERT INTO channel_payout_obligations "
                "(channel_id, wallet, chain, token, amount_cents, kind, status, "
                " deposit_tx_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'owed', ?, ?)",
                (channel_id, row["wallet"], row["chain"], row["token"],
                 remainder, kind, row["tx_hash"], now),
            )
        except Exception as exc:  # PK violation → a concurrent writer booked it first
            msg = str(exc).lower()
            if not any(k in msg for k in ("unique", "constraint", "duplicate")):
                raise
            existing = conn.execute(
                "SELECT * FROM channel_payout_obligations WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            return self._obligation_dict(existing) if existing else None
        if not row["wallet"]:
            # An unbound (stub/demo-only) channel leaves a debt with no payee. Loud on
            # purpose: in production every channel is bound to its on-chain payer.
            logger.warning(
                "Channel %s owes %d cents but carries no wallet — obligation has no payee",
                channel_id, remainder,
            )
        return {
            "channel_id": channel_id,
            "wallet": row["wallet"],
            "chain": row["chain"],
            "token": row["token"],
            "amount_usd": channels._cents_to_dollars(remainder),
            "amount_cents": remainder,
            "kind": kind,
            "status": "owed",
            "created_at": now,
            "payout_tx_hash": "",
            "settled_at": "",
        }

    @staticmethod
    def _obligation_dict(row: Any) -> dict[str, Any]:
        return {
            "channel_id": row["channel_id"],
            "wallet": row["wallet"],
            "chain": row["chain"],
            "token": row["token"],
            "amount_usd": channels._cents_to_dollars(row["amount_cents"]),
            "amount_cents": row["amount_cents"],
            "kind": row["kind"],
            "status": row["status"],
            "created_at": row["created_at"],
            "payout_tx_hash": row["payout_tx_hash"],
            "settled_at": row["settled_at"],
        }

    def obligations(self, status: str = "owed", limit: int = 500) -> list[dict[str, Any]]:
        """Outstanding (or, with status='', all) payout obligations, newest first."""
        limit = page_limit(limit, default=1, maximum=channels.OBLIGATIONS_PAGE_MAX)
        with self._get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM channel_payout_obligations WHERE status = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM channel_payout_obligations "
                    "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._obligation_dict(r) for r in rows]

    def obligations_total(self, status: str = "owed") -> dict[str, Any]:
        """Count + total of payout obligations in a given state (default: still owed)."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS cents "
                "FROM channel_payout_obligations WHERE status = ?",
                (status,),
            ).fetchone()
        cents = int(row["cents"] or 0)
        return {
            "status": status,
            "count": int(row["n"] or 0),
            "total_cents": cents,
            "total_usd": channels._cents_to_dollars(cents),
        }

    def mark_obligation_paid(self, channel_id: str, payout_tx_hash: str) -> dict[str, Any]:
        """Record that the operator has paid an obligation OUT-OF-BAND.

        This is an operator attestation, not a transfer and not an on-chain proof: this
        module never moves funds. A tx hash is REQUIRED, and it must be SHAPED like a
        real transaction id for the obligation's own chain — the previous check was
        "non-empty string", so `"paid"` cleared a depositor's debt and left an audit
        trail that can never be checked against any chain.
        """
        tx = (payout_tx_hash or "").strip()
        if not tx:
            return {"error": "payout_tx_hash is required to mark an obligation paid"}
        now = channels._now_iso()
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM channel_payout_obligations WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            if not row or row["status"] != "owed":
                return {"error": "no outstanding obligation for this channel"}
            shape_error = channels._payout_tx_shape_error(tx, row["chain"])
            if shape_error:
                return {"error": shape_error}
            cur = conn.execute(
                "UPDATE channel_payout_obligations SET status = 'paid', "
                "payout_tx_hash = ?, settled_at = ? "
                "WHERE channel_id = ? AND status = 'owed'",
                (tx, now, channel_id),
            )
            if getattr(cur, "rowcount", 0) != 1:
                # A concurrent writer settled it between the SELECT and the UPDATE.
                return {"error": "no outstanding obligation for this channel"}
            conn.commit()
        logger.warning(
            "Obligation on channel %s marked PAID out-of-band by the operator "
            "(payout tx %s) — attestation only, no funds moved by this process",
            channel_id, tx[:14],
        )
        return {"ok": True, "channel_id": channel_id, "payout_tx_hash": tx, "settled_at": now}

    # ── Orphaned-hold reaper ──────────────────────────────────────

    def _unresolved_settlement_nonces(self, receipt_ids: list[str]) -> set[str] | None:
        """Which of these hold receipts a live Pay-on-Verified verification still owns.

        Returns None when ownership cannot be determined — the caller must then reap
        NOTHING: releasing a hold a running verification later captures would let the
        same cents be spent twice (capture only adds to used_cents, it does not
        re-check the balance).

        The holds live in the ledger DB while `verified_settlements` lives in the hub
        index DB, so on SQLite this is a read-only cross-file lookup.

        A hold is owned when its receipt id IS an unresolved settlement's nonce (the invoke
        hold), or is `appeal_<nonce>` of one (the appellant's bond). Both readings are
        tried for a bond-shaped id, so the over-approximation errs towards reaping less.
        """
        if not receipt_ids:
            return set()
        wanted = set(receipt_ids)
        wanted.update(
            r[len(channels.APPEAL_BOND_PREFIX):] for r in receipt_ids if r.startswith(channels.APPEAL_BOND_PREFIX)
        )
        nonces = sorted(wanted)
        statuses = ",".join(f"'{s}'" for s in channels.UNRESOLVED_SETTLEMENT_STATUSES)

        def _query(conn: Any) -> set[str]:
            live: set[str] = set()
            for i in range(0, len(nonces), 200):
                chunk = nonces[i:i + 200]
                marks = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    "SELECT nonce FROM verified_settlements "
                    f"WHERE status IN ({statuses}) AND nonce IN ({marks})",
                    tuple(chunk),
                ).fetchall()
                live.update(r["nonce"] for r in rows)
            return {
                r for r in receipt_ids
                if r in live or (
                    r.startswith(channels.APPEAL_BOND_PREFIX) and r[len(channels.APPEAL_BOND_PREFIX):] in live
                )
            }

        backend_type = getattr(self._backend, "backend_type", "sqlite")
        target = channels._settlements_db_path()
        own_path = str(getattr(self._backend, "db_path", "") or "")
        try:
            if backend_type != "sqlite" or (own_path and os.path.abspath(own_path) == os.path.abspath(target)):
                # Same database (PostgreSQL, or the hub and ledger sharing one file):
                # our own connection can see verified_settlements.
                with self._get_conn() as conn:
                    return _query(conn)
            conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=10)
            try:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'verified_settlements'"
                ).fetchone()
                if not exists:
                    logger.error(
                        "Hold reaper: no verified_settlements table in %s — refusing to "
                        "release holds whose ownership cannot be checked", target,
                    )
                    return None
                return _query(conn)
            finally:
                conn.close()
        except Exception as exc:
            logger.error(
                "Hold reaper: cannot read verified_settlements from %s (%s) — "
                "refusing to release any hold", target, exc,
            )
            return None

    def reap_stale_holds(self, max_age_secs: float | None = None) -> dict[str, Any]:
        """Release holds stuck in 'held' with no live verification behind them.

        hold() commits to the ledger DB while the Pay-on-Verified row is committed to a
        different database; a hard kill between the two leaves a 'held' hold no
        reconciler will ever resolve, and close() refuses while a hold is pending — the
        buyer's balance is frozen forever. This reaper is the missing bound.

        Safety rules:
          * only holds older than the configured age (0 disables the reaper entirely);
          * only holds NOT owned by an unresolved settlement row (any of
            UNRESOLVED_SETTLEMENT_STATUSES — a verdict under appeal owns its hold AND the
            appellant's bond) — and if that cannot be read, nothing is reaped (fail closed);
          * never a hold whose receipt already appears in debited_receipts (a capture is
            partially recorded; crediting the balance back would double-count it);
          * bounded work per pass, and idempotent: the status flip is row-count guarded,
            so a concurrent capture_hold/release_hold wins and the reaper skips.

        Releasing returns the cents to the channel balance (buyer-safe direction) — no
        funds move, and the buyer can then close and be owed the remainder as usual.
        """
        age = float(channels._hold_reap_after_secs() if max_age_secs is None else max_age_secs)
        if age <= 0:
            return {"reaped": 0, "released_usd": 0.0, "skipped": 0, "disabled": True}

        cutoff = time.time() - age
        with self._get_conn() as conn:
            held = conn.execute(
                "SELECT receipt_id, channel_id, amount_cents, created_at "
                "FROM channel_holds WHERE status = 'held' "
                "ORDER BY created_at LIMIT ?",
                (channels._HOLD_REAP_SCAN_LIMIT,),
            ).fetchall()

        candidates = []
        undatable = 0
        for row in held:
            created = channels._parse_ts(row["created_at"])
            if created is None:
                # Cannot age it → cannot prove it is abandoned → leave it alone.
                undatable += 1
                continue
            if created <= cutoff:
                candidates.append(row)

        if not candidates:
            return {"reaped": 0, "released_usd": 0.0, "skipped": undatable, "scanned": len(held)}

        owned = self._unresolved_settlement_nonces([r["receipt_id"] for r in candidates])
        if owned is None:
            return {
                "reaped": 0, "released_usd": 0.0, "skipped": len(candidates) + undatable,
                "scanned": len(held),
                "error": "settlement ownership unavailable — refusing to release holds",
            }

        now = channels._now_iso()
        reaped = 0
        released_cents = 0
        skipped = undatable
        inconsistent = 0
        with self._lock, self._get_conn() as conn:
            for row in candidates:
                receipt_id = row["receipt_id"]
                if receipt_id in owned:
                    skipped += 1
                    continue
                captured = conn.execute(
                    "SELECT 1 FROM debited_receipts WHERE receipt_id = ?", (receipt_id,)
                ).fetchone()
                if captured:
                    # A capture is (at least partially) recorded for this receipt.
                    # Returning the cents to the balance would credit the buyer for an
                    # invoke already billed — refuse and surface it for the operator.
                    inconsistent += 1
                    logger.error(
                        "Hold %s is 'held' but already has a debit receipt — refusing to "
                        "release; ledger needs operator reconciliation", receipt_id,
                    )
                    continue
                channel = conn.execute(
                    "SELECT status FROM channels WHERE channel_id = ?",
                    (row["channel_id"],),
                ).fetchone()
                if not channel or channel["status"] != "open":
                    # A hold is only ever created on an open channel, and close/sweep
                    # both refuse while one is held — so this is an inconsistency, not a
                    # routine case. Crediting a closed channel's balance would resurrect
                    # money after settlement, so refuse.
                    inconsistent += 1
                    logger.error(
                        "Hold %s belongs to channel %s in state %s — refusing to release",
                        receipt_id, row["channel_id"],
                        channel["status"] if channel else "missing",
                    )
                    continue
                note = f"reaped: no live verification after {int(age)}s"
                cur = conn.execute(
                    "UPDATE channel_holds SET status = 'reaped', resolved_at = ?, "
                    "resolution_note = ? WHERE receipt_id = ? AND status = 'held'",
                    (now, note, receipt_id),
                )
                if getattr(cur, "rowcount", 0) != 1:
                    # capture_hold/release_hold resolved it between the scan and now.
                    skipped += 1
                    continue
                conn.execute(
                    "UPDATE channels SET balance_cents = balance_cents + ? "
                    "WHERE channel_id = ?",
                    (row["amount_cents"], row["channel_id"]),
                )
                reaped += 1
                released_cents += int(row["amount_cents"] or 0)
                logger.warning(
                    "Reaped orphaned hold %s on channel %s — %d cents returned to "
                    "balance (%s)", receipt_id, row["channel_id"],
                    row["amount_cents"], note,
                )
            if reaped:
                conn.commit()

        result = {
            "reaped": reaped,
            "released_usd": channels._cents_to_dollars(released_cents),
            "skipped": skipped,
            "scanned": len(held),
        }
        if inconsistent:
            result["inconsistent"] = inconsistent
        return result

    def stop_sweep(self) -> None:
        self._running = False


# Imported after the class on purpose: methods read aimarket_hub.channels at call time
# (where its settings and test patches live), and either module may load first.
from aimarket_hub import channels  # noqa: E402
