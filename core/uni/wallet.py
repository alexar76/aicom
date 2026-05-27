"""UNI wallet — single balance + hold ledger for the ecosystem."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.uni.config import uni_db_backend, uni_min_withdraw_uni, uni_withdraw_fee_bps
from core.uni.constants import PLATFORM_OWNER_ID, PLATFORM_OWNER_TYPE
from core.uni.pricing import platform_fee_uni, usd_to_uni, withdraw_net_usd
from core.uni.store import dumps_meta, now_ts, row_to_dict, uni_connection

logger = logging.getLogger(__name__)


class UniWalletError(ValueError):
    pass


class InsufficientFundsError(UniWalletError):
    pass


def _iuni(value: float | int) -> int:
    return int(round(float(value)))


class UniWalletService:
    """Append-only ledger with holds for payment channels."""

    def wallet_id_for_owner(self, owner_id: str) -> str:
        clean = (owner_id or "").strip()
        if not clean:
            raise UniWalletError("owner_id required")
        return f"uni_wal_{uuid.uuid5(uuid.NAMESPACE_URL, clean).hex[:16]}"

    def get_or_create_wallet(self, owner_id: str, *, owner_type: str = "customer") -> dict[str, Any]:
        wallet_id = self.wallet_id_for_owner(owner_id)
        ts = now_ts()
        with uni_connection() as conn:
            row = self._fetch_wallet(conn, wallet_id)
            if row:
                return self._wallet_view(row)
            if uni_db_backend() == "postgres":
                conn.execute(
                    """
                    INSERT INTO uni_wallets (
                        wallet_id, owner_id, owner_type, balance_uni, hold_uni,
                        lifetime_in, lifetime_out, status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, 0, 0, 0, 0, 'active', %s, %s)
                    ON CONFLICT (owner_id) DO NOTHING
                    """,
                    (wallet_id, owner_id, owner_type, ts, ts),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO uni_wallets (
                        wallet_id, owner_id, owner_type, balance_uni, hold_uni,
                        lifetime_in, lifetime_out, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 0, 0, 0, 0, 'active', ?, ?)
                    """,
                    (wallet_id, owner_id, owner_type, ts, ts),
                )
            row = self._fetch_wallet(conn, wallet_id)
        return self._wallet_view(row or {})

    def get_wallet_by_owner(self, owner_id: str) -> dict[str, Any] | None:
        wallet_id = self.wallet_id_for_owner(owner_id)
        with uni_connection() as conn:
            row = self._fetch_wallet(conn, wallet_id)
        return self._wallet_view(row) if row else None

    def get_or_create_platform_wallet(self) -> dict[str, Any]:
        return self.get_or_create_wallet(PLATFORM_OWNER_ID, owner_type=PLATFORM_OWNER_TYPE)

    def charge(
        self,
        buyer_owner_id: str,
        *,
        seller_owner_id: str,
        amount_uni: int,
        meta: dict[str, Any] | None = None,
        idempotency_key: str,
        receipt_kind: str = "invoke",
    ) -> dict[str, Any]:
        """
        Atomic buyer → seller + platform fee split (5% default).

        P2P transfer between users is not supported — only seller settlement.
        """
        gross = _iuni(amount_uni)
        if gross <= 0:
            raise UniWalletError("charge amount must be positive")
        fee = platform_fee_uni(gross)
        net = gross - fee
        buyer = self.get_or_create_wallet(buyer_owner_id)
        seller = self.get_or_create_wallet(seller_owner_id)
        platform = self.get_or_create_platform_wallet()
        meta = meta or {}
        ts = now_ts()
        with uni_connection() as conn:
            if not self._claim_ledger_entry(
                conn,
                wallet_id=buyer["wallet_id"],
                entry_type="charge",
                amount_uni=-gross,
                ref=idempotency_key,
                meta={**meta, "seller": seller_owner_id, "fee_uni": fee},
                idempotency_key=idempotency_key,
            ):
                # Caller asked for an idempotent retry and the first attempt
                # already persisted. Return the ORIGINAL receipt so they can
                # quote it downstream — same contract as a fresh charge.
                # Pass `conn` to avoid re-acquiring the process-wide write lock.
                from core.uni.receipts import get_receipt_by_idempotency_key

                prior = get_receipt_by_idempotency_key(idempotency_key, conn=conn)
                return {
                    "duplicate": True,
                    "idempotency_key": idempotency_key,
                    "receipt": prior,
                    "amount_uni": gross,
                    "platform_fee_uni": fee,
                    "net_to_seller_uni": net,
                }
            if not self._debit_available(conn, buyer["wallet_id"], gross, ts):
                raise InsufficientFundsError("insufficient_balance")
            self._credit_balance(conn, seller["wallet_id"], net, ts, lifetime_in=True)
            if fee > 0:
                self._credit_balance(conn, platform["wallet_id"], fee, ts, lifetime_in=True)
        from core.uni.receipts import issue_receipt

        receipt = issue_receipt(
            wallet_id=buyer["wallet_id"],
            kind=receipt_kind,
            amount_uni=gross,
            meta={**meta, "buyer_owner_id": buyer_owner_id, "seller_owner_id": seller_owner_id},
            idempotency_key=idempotency_key,
            buyer_wallet_id=buyer["wallet_id"],
            seller_wallet_id=seller["wallet_id"],
            platform_fee_uni=fee,
            net_to_seller_uni=net,
            product_id=meta.get("product_id"),
            capability_id=meta.get("capability_id"),
            hub_id=meta.get("hub_id"),
        )
        return {
            "receipt": receipt,
            "amount_uni": gross,
            "platform_fee_uni": fee,
            "net_to_seller_uni": net,
            "buyer": self.get_wallet_by_owner(buyer_owner_id),
            "seller": self.get_wallet_by_owner(seller_owner_id),
        }

    def withdraw_to_chain(
        self,
        owner_id: str,
        *,
        amount_uni: int,
        payout_address: str,
        chain: str,
        token: str = "USDT",
    ) -> dict[str, Any]:
        gross = _iuni(amount_uni)
        if gross < uni_min_withdraw_uni():
            raise UniWalletError(f"minimum_withdraw_uni={uni_min_withdraw_uni()}")
        fee = platform_fee_uni(gross, fee_bps=uni_withdraw_fee_bps())
        if fee >= gross:
            raise UniWalletError("withdraw amount too small after fee")
        net_uni = gross - fee
        net_usdt = withdraw_net_usd(gross, fee_bps=uni_withdraw_fee_bps())
        wallet = self.get_or_create_wallet(owner_id)
        ts = now_ts()
        withdrawal_id = f"wd_{uuid.uuid4().hex[:16]}"
        idem = f"withdraw:{withdrawal_id}"
        with uni_connection() as conn:
            if not self._claim_ledger_entry(
                conn,
                wallet_id=wallet["wallet_id"],
                entry_type="withdraw",
                amount_uni=-gross,
                ref=withdrawal_id,
                meta={"fee_uni": fee, "net_usdt": net_usdt, "payout_address": payout_address, "chain": chain},
                idempotency_key=idem,
            ):
                raise UniWalletError("duplicate_withdraw")
            if not self._debit_available(conn, wallet["wallet_id"], gross, ts):
                raise InsufficientFundsError("insufficient_balance")
            platform = self.get_or_create_platform_wallet()
            if fee > 0:
                self._credit_balance(conn, platform["wallet_id"], fee, ts, lifetime_in=True)
            if uni_db_backend() == "postgres":
                conn.execute(
                    """
                    INSERT INTO uni_withdrawals (
                        withdrawal_id, wallet_id, amount_uni, fee_uni, net_usdt,
                        payout_chain, payout_token, payout_address, status, requested_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s)
                    """,
                    (withdrawal_id, wallet["wallet_id"], gross, fee, net_usdt, chain, token, payout_address, ts),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO uni_withdrawals (
                        withdrawal_id, wallet_id, amount_uni, fee_uni, net_usdt,
                        payout_chain, payout_token, payout_address, status, requested_at
                    ) VALUES (?,?,?,?,?,?,?,?,'queued',?)
                    """,
                    (withdrawal_id, wallet["wallet_id"], gross, fee, net_usdt, chain, token, payout_address, ts),
                )
        from core.uni.receipts import issue_receipt

        issue_receipt(
            wallet_id=wallet["wallet_id"],
            kind="withdraw",
            amount_uni=gross,
            meta={"fee_uni": fee, "net_usdt": net_usdt, "payout_address": payout_address, "chain": chain},
            idempotency_key=f"withdraw:{withdrawal_id}",
            tx_hash=None,
            chain=chain,
        )
        return {
            "withdrawal_id": withdrawal_id,
            "amount_uni": gross,
            "fee_uni": fee,
            "net_usdt": net_usdt,
            "status": "queued",
        }

    def topup_from_chain(
        self,
        owner_id: str,
        *,
        usd_amount: float,
        tx_hash: str,
        chain: str = "",
        token: str = "USDT",
    ) -> dict[str, Any]:
        if usd_amount <= 0:
            raise UniWalletError("topup amount must be positive")
        amount_uni = usd_to_uni(usd_amount, apply_spread=True)
        wallet = self.get_or_create_wallet(owner_id)
        idem = f"topup:{tx_hash}"
        return self._credit(
            wallet,
            amount_uni,
            entry_type="topup",
            ref=tx_hash,
            meta={"usd_amount": usd_amount, "chain": chain, "token": token, "source": "on_chain"},
            idempotency_key=idem,
            receipt_kind="topup",
        )

    def grant(
        self,
        owner_id: str,
        *,
        amount_uni: float,
        ref: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if amount_uni <= 0:
            raise UniWalletError("grant amount must be positive")
        wallet = self.get_or_create_wallet(owner_id)
        idem = f"grant:{ref}"
        return self._credit(
            wallet,
            amount_uni,
            entry_type="grant",
            ref=ref,
            meta={**(meta or {}), "source": "grant"},
            idempotency_key=idem,
            receipt_kind="grant",
        )

    def hold(
        self,
        owner_id: str,
        *,
        amount_uni: float,
        channel_id: str,
        seller_ref: str = "ai_market",
        ttl_sec: float = 86400,
    ) -> dict[str, Any]:
        if amount_uni <= 0:
            raise UniWalletError("hold amount must be positive")
        gross = _iuni(amount_uni)
        wallet = self.get_or_create_wallet(owner_id)
        wallet_id = wallet["wallet_id"]
        hold_id = f"hold_{uuid.uuid4().hex[:12]}"
        ts = now_ts()
        idem = f"hold:{channel_id}"
        with uni_connection() as conn:
            if not self._claim_ledger_entry(
                conn,
                wallet_id=wallet_id,
                entry_type="hold",
                amount_uni=-gross,
                ref=channel_id,
                meta={"hold_id": hold_id, "seller_ref": seller_ref, "channel_id": channel_id},
                idempotency_key=idem,
            ):
                row = self._fetch_wallet(conn, wallet_id)
                hold = self._fetch_hold_by_channel(conn, channel_id)
                return {
                    "hold_id": hold.get("hold_id") if hold else hold_id,
                    "channel_id": channel_id,
                    "amount_uni": gross,
                    "wallet": self._wallet_view(row or {}),
                    "duplicate": True,
                }
            if uni_db_backend() == "postgres":
                cur = conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni - %s, hold_uni = hold_uni + %s, updated_at = %s
                    WHERE wallet_id = %s AND balance_uni - hold_uni >= %s
                    """,
                    (gross, gross, ts, wallet_id, gross),
                )
                if cur.rowcount != 1:
                    raise InsufficientFundsError("insufficient_balance")
                conn.execute(
                    """
                    INSERT INTO uni_holds (hold_id, wallet_id, channel_id, amount_uni, remaining_uni, seller_ref, status, expires_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s, %s)
                    """,
                    (hold_id, wallet_id, channel_id, gross, gross, seller_ref, ts + ttl_sec, ts, ts),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni - ?, hold_uni = hold_uni + ?, updated_at = ?
                    WHERE wallet_id = ? AND balance_uni - hold_uni >= ?
                    """,
                    (gross, gross, ts, wallet_id, gross),
                )
                if cur.rowcount != 1:
                    raise InsufficientFundsError("insufficient_balance")
                conn.execute(
                    """
                    INSERT INTO uni_holds (hold_id, wallet_id, channel_id, amount_uni, remaining_uni, seller_ref, status, expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (hold_id, wallet_id, channel_id, gross, gross, seller_ref, ts + ttl_sec, ts, ts),
                )
            row = self._fetch_wallet(conn, wallet_id)
        return {"hold_id": hold_id, "channel_id": channel_id, "amount_uni": gross, "wallet": self._wallet_view(row or {})}

    def spend_hold(self, *, channel_id: str, amount_uni: float, ref: str = "") -> dict[str, Any]:
        gross = _iuni(amount_uni)
        if gross <= 0:
            raise UniWalletError("spend amount must be positive")
        fee = platform_fee_uni(gross)
        net = gross - fee
        ts = now_ts()
        idem = f"spend:{channel_id}:{ref}:{gross}"
        with uni_connection() as conn:
            hold = self._fetch_hold_by_channel(conn, channel_id)
        if not hold or hold.get("status") != "open":
            raise UniWalletError("hold_not_open")
        seller_ref = str(hold.get("seller_ref") or "ai_market")
        seller = self.get_or_create_wallet(seller_ref)
        platform = self.get_or_create_platform_wallet()
        with uni_connection() as conn:
            hold = self._fetch_hold_by_channel(conn, channel_id)
            if not hold or hold.get("status") != "open":
                raise UniWalletError("hold_not_open")
            remaining = _iuni(hold.get("remaining_uni") or 0)
            if gross > remaining:
                raise InsufficientFundsError("insufficient_hold")
            hold_id = hold["hold_id"]
            wallet_id = hold["wallet_id"]
            if not self._claim_ledger_entry(
                conn,
                wallet_id=wallet_id,
                entry_type="charge",
                amount_uni=-gross,
                ref=ref or channel_id,
                meta={"hold_id": hold_id, "channel_id": channel_id, "fee_uni": fee, "net_uni": net},
                idempotency_key=idem,
            ):
                from core.uni.receipts import get_receipt_by_idempotency_key

                prior = get_receipt_by_idempotency_key(idem, conn=conn)
                return {
                    "ok": False,
                    "duplicate": True,
                    "error": "duplicate_spend",
                    "receipt": prior,
                }
            new_remaining = remaining - gross
            status = "open" if new_remaining > 0 else "depleted"
            if uni_db_backend() == "postgres":
                conn.execute(
                    "UPDATE uni_holds SET remaining_uni = %s, status = %s, updated_at = %s WHERE hold_id = %s",
                    (new_remaining, status, ts, hold_id),
                )
                conn.execute(
                    """
                    UPDATE uni_wallets SET hold_uni = hold_uni - %s, lifetime_out = lifetime_out + %s, updated_at = %s
                    WHERE wallet_id = %s
                    """,
                    (gross, gross, ts, wallet_id),
                )
            else:
                conn.execute(
                    "UPDATE uni_holds SET remaining_uni = ?, status = ?, updated_at = ? WHERE hold_id = ?",
                    (new_remaining, status, ts, hold_id),
                )
                conn.execute(
                    """
                    UPDATE uni_wallets SET hold_uni = hold_uni - ?, lifetime_out = lifetime_out + ?, updated_at = ?
                    WHERE wallet_id = ?
                    """,
                    (gross, gross, ts, wallet_id),
                )
            self._credit_balance(conn, seller["wallet_id"], net, ts, lifetime_in=True)
            if fee > 0:
                self._credit_balance(conn, platform["wallet_id"], fee, ts, lifetime_in=True)
            row = self._fetch_wallet(conn, wallet_id)
        from core.uni.receipts import issue_receipt

        receipt = issue_receipt(
            wallet_id=wallet_id,
            kind="hold_charge",
            amount_uni=gross,
            meta={"channel_id": channel_id, "ref": ref, "seller_ref": seller_ref},
            idempotency_key=idem,
            buyer_wallet_id=wallet_id,
            seller_wallet_id=seller["wallet_id"],
            platform_fee_uni=fee,
            net_to_seller_uni=net,
        )
        return {
            "ok": True,
            "amount_uni": gross,
            "platform_fee_uni": fee,
            "net_to_seller_uni": net,
            "remaining_uni": new_remaining,
            "receipt": receipt,
        }

    def release_hold(self, channel_id: str) -> dict[str, Any]:
        ts = now_ts()
        with uni_connection() as conn:
            hold = self._fetch_hold_by_channel(conn, channel_id)
            if not hold:
                raise UniWalletError("hold_not_found")
            if hold.get("status") == "closed":
                return {"ok": True, "refund_uni": 0.0}
            remaining = float(hold.get("remaining_uni") or 0)
            hold_id = hold["hold_id"]
            wallet_id = hold["wallet_id"]
            if remaining > 0:
                rem_i = _iuni(remaining)
                if not self._claim_ledger_entry(
                    conn,
                    wallet_id=wallet_id,
                    entry_type="release",
                    amount_uni=rem_i,
                    ref=channel_id,
                    meta={"hold_id": hold_id},
                    idempotency_key=f"release:{channel_id}",
                ):
                    return {"ok": True, "refund_uni": 0, "duplicate": True}
            if uni_db_backend() == "postgres":
                conn.execute(
                    "UPDATE uni_holds SET remaining_uni = 0, status = 'closed', updated_at = %s WHERE hold_id = %s",
                    (ts, hold_id),
                )
                conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni + %s, hold_uni = hold_uni - %s, updated_at = %s
                    WHERE wallet_id = %s
                    """,
                    (remaining, remaining, ts, wallet_id),
                )
            else:
                conn.execute(
                    "UPDATE uni_holds SET remaining_uni = 0, status = 'closed', updated_at = ? WHERE hold_id = ?",
                    (ts, hold_id),
                )
                conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni + ?, hold_uni = hold_uni - ?, updated_at = ?
                    WHERE wallet_id = ?
                    """,
                    (remaining, remaining, ts, wallet_id),
                )
        return {"ok": True, "refund_uni": remaining}

    def credit_seller(
        self,
        seller_ref: str,
        *,
        amount_uni: float,
        meta: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        wallet = self.get_or_create_wallet(seller_ref)
        return self._credit(
            wallet,
            amount_uni,
            entry_type="credit",
            ref=meta.get("ref", ""),
            meta=meta,
            idempotency_key=idempotency_key,
            receipt_kind="capability_sale",
        )

    def economy_summary(self) -> dict[str, Any]:
        with uni_connection() as conn:
            if uni_db_backend() == "postgres":
                wallets = conn.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(balance_uni),0) AS bal, COALESCE(SUM(hold_uni),0) AS held, COALESCE(SUM(lifetime_in),0) AS lin, COALESCE(SUM(lifetime_out),0) AS lout FROM uni_wallets"
                ).fetchone()
                receipts = conn.execute("SELECT COUNT(*) AS n FROM uni_receipts").fetchone()
            else:
                wallets = conn.execute(
                    "SELECT COUNT(*) AS n, COALESCE(SUM(balance_uni),0) AS bal, COALESCE(SUM(hold_uni),0) AS held, COALESCE(SUM(lifetime_in),0) AS lin, COALESCE(SUM(lifetime_out),0) AS lout FROM uni_wallets"
                ).fetchone()
                receipts = conn.execute("SELECT COUNT(*) AS n FROM uni_receipts").fetchone()
        w = row_to_dict(wallets)
        r = row_to_dict(receipts)
        return {
            "wallets": int(w.get("n") or 0),
            "balance_uni_total": round(float(w.get("bal") or 0), 4),
            "hold_uni_total": round(float(w.get("held") or 0), 4),
            "lifetime_in_uni": round(float(w.get("lin") or 0), 4),
            "lifetime_out_uni": round(float(w.get("lout") or 0), 4),
            "receipts_count": int(r.get("n") or 0),
        }

    def _credit(
        self,
        wallet: dict[str, Any],
        amount_uni: float,
        *,
        entry_type: str,
        ref: str,
        meta: dict[str, Any],
        idempotency_key: str,
        receipt_kind: str,
    ) -> dict[str, Any]:
        wallet_id = wallet["wallet_id"]
        delta = _iuni(amount_uni)
        ts = now_ts()
        with uni_connection() as conn:
            if not self._claim_ledger_entry(
                conn,
                wallet_id=wallet_id,
                entry_type=entry_type,
                amount_uni=delta,
                ref=ref,
                meta=meta,
                idempotency_key=idempotency_key,
            ):
                row = self._fetch_wallet(conn, wallet_id)
                from core.uni.receipts import get_receipt_by_idempotency_key

                prior = get_receipt_by_idempotency_key(idempotency_key, conn=conn)
                return {
                    "wallet": self._wallet_view(row or {}),
                    "duplicate": True,
                    "receipt": prior,
                }
            if uni_db_backend() == "postgres":
                conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni + %s, lifetime_in = lifetime_in + %s, updated_at = %s
                    WHERE wallet_id = %s
                    """,
                    (delta, delta, ts, wallet_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni + ?, lifetime_in = lifetime_in + ?, updated_at = ?
                    WHERE wallet_id = ?
                    """,
                    (delta, delta, ts, wallet_id),
                )
            row = self._fetch_wallet(conn, wallet_id)
        from core.uni.receipts import issue_receipt

        receipt = issue_receipt(
            wallet_id=wallet_id,
            kind=receipt_kind,
            amount_uni=amount_uni,
            meta={**meta, "ref": ref, "entry_type": entry_type},
            idempotency_key=idempotency_key,
        )
        return {"wallet": self._wallet_view(row or {}), "receipt": receipt}

    def _fetch_wallet(self, conn: Any, wallet_id: str) -> dict[str, Any] | None:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT * FROM uni_wallets WHERE wallet_id = %s",
                (wallet_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM uni_wallets WHERE wallet_id = ?", (wallet_id,)).fetchone()
        return row_to_dict(row) if row else None

    def _fetch_hold_by_channel(self, conn: Any, channel_id: str) -> dict[str, Any] | None:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT * FROM uni_holds WHERE channel_id = %s ORDER BY created_at DESC LIMIT 1",
                (channel_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM uni_holds WHERE channel_id = ? ORDER BY created_at DESC LIMIT 1",
                (channel_id,),
            ).fetchone()
        return row_to_dict(row) if row else None

    def _claim_ledger_entry(
        self,
        conn: Any,
        *,
        wallet_id: str,
        entry_type: str,
        amount_uni: int,
        ref: str,
        meta: dict[str, Any],
        idempotency_key: str,
    ) -> bool:
        """INSERT-first idempotency claim; returns False when key already used."""
        if not idempotency_key:
            return True
        row = self._fetch_wallet(conn, wallet_id)
        if not row:
            return False
        bal = _iuni(row.get("balance_uni"))
        held = _iuni(row.get("hold_uni"))
        if entry_type == "hold":
            balance_after = bal + amount_uni
            hold_after = held - amount_uni
        elif entry_type == "release":
            balance_after = bal + amount_uni
            hold_after = max(0, held - amount_uni)
        elif entry_type == "charge":
            balance_after = bal
            hold_after = max(0, held + amount_uni)
        elif entry_type == "withdraw":
            balance_after = bal + amount_uni
            hold_after = held
        else:
            balance_after = bal + amount_uni
            hold_after = held
        ts = now_ts()
        if uni_db_backend() == "postgres":
            cur = conn.execute(
                """
                INSERT INTO uni_ledger (wallet_id, entry_type, amount_uni, balance_after, hold_after, ref, meta_json, ts, idempotency_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    wallet_id,
                    entry_type,
                    amount_uni,
                    balance_after,
                    hold_after,
                    ref,
                    dumps_meta(meta),
                    ts,
                    idempotency_key,
                ),
            )
            return cur.fetchone() is not None
        try:
            conn.execute(
                """
                INSERT INTO uni_ledger (wallet_id, entry_type, amount_uni, balance_after, hold_after, ref, meta_json, ts, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wallet_id,
                    entry_type,
                    amount_uni,
                    balance_after,
                    hold_after,
                    ref,
                    dumps_meta(meta),
                    ts,
                    idempotency_key,
                ),
            )
            return True
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                return False
            raise

    def _ledger_idempotency(self, conn: Any, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT meta_json FROM uni_ledger WHERE idempotency_key = %s",
                (key,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT meta_json FROM uni_ledger WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return {"idempotent": True, "meta": row_to_dict(row).get("meta_json")}

    def _debit_available(self, conn: Any, wallet_id: str, amount_uni: int, ts: float) -> bool:
        if uni_db_backend() == "postgres":
            cur = conn.execute(
                """
                UPDATE uni_wallets
                SET balance_uni = balance_uni - %s,
                    lifetime_out = lifetime_out + %s,
                    updated_at = %s
                WHERE wallet_id = %s AND balance_uni - hold_uni >= %s
                """,
                (amount_uni, amount_uni, ts, wallet_id, amount_uni),
            )
            return cur.rowcount == 1
        cur = conn.execute(
            """
            UPDATE uni_wallets
            SET balance_uni = balance_uni - ?,
                lifetime_out = lifetime_out + ?,
                updated_at = ?
            WHERE wallet_id = ? AND balance_uni - hold_uni >= ?
            """,
            (amount_uni, amount_uni, ts, wallet_id, amount_uni),
        )
        return cur.rowcount == 1

    def _credit_balance(self, conn: Any, wallet_id: str, amount_uni: int, ts: float, *, lifetime_in: bool) -> None:
        if amount_uni <= 0:
            return
        if uni_db_backend() == "postgres":
            if lifetime_in:
                conn.execute(
                    """
                    UPDATE uni_wallets
                    SET balance_uni = balance_uni + %s, lifetime_in = lifetime_in + %s, updated_at = %s
                    WHERE wallet_id = %s
                    """,
                    (amount_uni, amount_uni, ts, wallet_id),
                )
            else:
                conn.execute(
                    "UPDATE uni_wallets SET balance_uni = balance_uni + %s, updated_at = %s WHERE wallet_id = %s",
                    (amount_uni, ts, wallet_id),
                )
        elif lifetime_in:
            conn.execute(
                """
                UPDATE uni_wallets
                SET balance_uni = balance_uni + ?, lifetime_in = lifetime_in + ?, updated_at = ?
                WHERE wallet_id = ?
                """,
                (amount_uni, amount_uni, ts, wallet_id),
            )
        else:
            conn.execute(
                "UPDATE uni_wallets SET balance_uni = balance_uni + ?, updated_at = ? WHERE wallet_id = ?",
                (amount_uni, ts, wallet_id),
            )

    @staticmethod
    def _wallet_view(row: dict[str, Any]) -> dict[str, Any]:
        bal = _iuni(row.get("balance_uni"))
        held = _iuni(row.get("hold_uni"))
        return {
            "wallet_id": row.get("wallet_id"),
            "owner_id": row.get("owner_id"),
            "owner_type": row.get("owner_type") or "customer",
            "balance_uni": bal,
            "hold_uni": held,
            "available_uni": max(0, bal - held),
            "lifetime_in": _iuni(row.get("lifetime_in")),
            "lifetime_out": _iuni(row.get("lifetime_out")),
            "status": row.get("status") or "active",
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
