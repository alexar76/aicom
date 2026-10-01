"""Background maintenance for UNI (call from pipeline worker cron or ops)."""

from __future__ import annotations

import logging
from typing import Any

from core.uni.config import uni_db_backend, uni_enabled
from core.uni.store import now_ts, row_to_dict, uni_connection
from core.uni.treasury import snapshot_treasury_audit
from core.uni.wallet import UniWalletService

logger = logging.getLogger(__name__)

_STUCK_SENDING_SEC = 3600


def run_treasury_audit_job() -> dict[str, Any]:
    if not uni_enabled():
        return {"skipped": True}
    return snapshot_treasury_audit()


def run_holds_expirer_job() -> dict[str, Any]:
    """Release expired open holds back to buyer balance."""
    if not uni_enabled():
        return {"skipped": True}
    svc = UniWalletService()
    ts = now_ts()
    released = 0
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            rows = conn.execute(
                "SELECT channel_id FROM uni_holds WHERE status = 'open' AND expires_at < %s AND channel_id IS NOT NULL",
                (ts,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT channel_id FROM uni_holds WHERE status = 'open' AND expires_at < ? AND channel_id IS NOT NULL",
                (ts,),
            ).fetchall()
        channel_ids = [str(row_to_dict(r).get("channel_id") or "") for r in rows]
    for ch in channel_ids:
        if not ch:
            continue
        try:
            svc.release_hold(ch)
            released += 1
        except Exception as exc:
            logger.warning("hold expirer failed for %s: %s", ch, exc)
    return {"released": released}


def run_withdraw_dispatcher_job(*, max_batch: int = 5) -> dict[str, Any]:
    """
    Claim queued withdrawals (one worker wins per row) and advance lifecycle.

    On-chain transfer is not wired yet: rows move to ``failed`` with refund so UNI
    is not stranded in ``sending``. Set ``AIFACTORY_UNI_WITHDRAW_DISPATCHER=1`` when
    treasury hot-wallet payout is integrated.
    """
    if not uni_enabled():
        return {"skipped": True}
    import os

    dispatcher_live = os.environ.get("AIFACTORY_UNI_WITHDRAW_DISPATCHER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    processed = 0
    refunds: list[tuple[str, int, str]] = []
    ts = now_ts()
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            rows = conn.execute(
                """
                SELECT withdrawal_id, wallet_id, amount_uni, fee_uni
                FROM uni_withdrawals
                WHERE status = 'queued'
                ORDER BY requested_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (max_batch,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT withdrawal_id, wallet_id, amount_uni, fee_uni
                FROM uni_withdrawals
                WHERE status = 'queued'
                ORDER BY requested_at
                LIMIT ?
                """,
                (max_batch,),
            ).fetchall()
        for raw in rows:
            row = row_to_dict(raw)
            wid = str(row.get("withdrawal_id") or "")
            if not wid:
                continue
            if uni_db_backend() == "postgres":
                cur = conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'sending', error = %s
                    WHERE withdrawal_id = %s AND status = 'queued'
                    """,
                    ("dispatch claimed", wid),
                )
                claimed = cur.rowcount == 1
            else:
                cur = conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'sending', error = ?
                    WHERE withdrawal_id = ? AND status = 'queued'
                    """,
                    ("dispatch claimed", wid),
                )
                claimed = cur.rowcount == 1
            if not claimed:
                continue
            processed += 1
            if dispatcher_live:
                continue
            wallet_id = str(row.get("wallet_id") or "")
            gross = int(round(float(row.get("amount_uni") or 0)))
            int(round(float(row.get("fee_uni") or 0)))
            refund = gross
            if uni_db_backend() == "postgres":
                conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'failed', error = %s, completed_at = %s
                    WHERE withdrawal_id = %s AND status = 'sending'
                    """,
                    ("withdraw dispatcher not enabled; UNI refunded", ts, wid),
                )
            else:
                conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE withdrawal_id = ? AND status = 'sending'
                    """,
                    ("withdraw dispatcher not enabled; UNI refunded", ts, wid),
                )
            if refund > 0 and wallet_id:
                owner_row = conn.execute(
                    "SELECT owner_id FROM uni_wallets WHERE wallet_id = ?"
                    if uni_db_backend() != "postgres"
                    else "SELECT owner_id FROM uni_wallets WHERE wallet_id = %s",
                    (wallet_id,),
                ).fetchone()
                owner_id = str(row_to_dict(owner_row).get("owner_id") or "") if owner_row else ""
                if owner_id:
                    refunds.append((owner_id, refund, wid))

    svc = UniWalletService()
    failed_refunded = 0
    for owner_id, refund, wid in refunds:
        try:
            svc.grant(
                owner_id,
                amount_uni=refund,
                ref=f"withdraw-refund:{wid}",
                meta={"withdrawal_id": wid},
            )
            failed_refunded += 1
        except Exception as exc:
            logger.error("withdraw refund failed for %s: %s", wid, exc)

    reaped_stuck, reap_refunds = _reap_stuck_sending_withdrawals(ts)
    for owner_id, refund, wid in reap_refunds:
        try:
            svc.grant(
                owner_id,
                amount_uni=refund,
                ref=f"withdraw-reap:{wid}",
                meta={"withdrawal_id": wid},
            )
        except Exception as exc:
            logger.error("reap refund failed for %s: %s", wid, exc)
    return {
        "processed": processed,
        "failed_refunded": failed_refunded,
        "reaped_stuck_sending": reaped_stuck,
        "dispatcher_live": dispatcher_live,
    }


def _reap_stuck_sending_withdrawals(ts: float) -> tuple[int, list[tuple[str, int, str]]]:
    """Refund withdrawals stuck in ``sending`` too long."""
    cutoff = ts - _STUCK_SENDING_SEC
    refunds: list[tuple[str, int, str]] = []
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            rows = conn.execute(
                """
                SELECT withdrawal_id, wallet_id, amount_uni
                FROM uni_withdrawals
                WHERE status = 'sending' AND requested_at < %s
                """,
                (cutoff,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT withdrawal_id, wallet_id, amount_uni
                FROM uni_withdrawals
                WHERE status = 'sending' AND requested_at < ?
                """,
                (cutoff,),
            ).fetchall()
        for raw in rows:
            row = row_to_dict(raw)
            wid = str(row.get("withdrawal_id") or "")
            wallet_id = str(row.get("wallet_id") or "")
            gross = int(round(float(row.get("amount_uni") or 0)))
            if uni_db_backend() == "postgres":
                cur = conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'failed', error = %s, completed_at = %s
                    WHERE withdrawal_id = %s AND status = 'sending'
                    """,
                    ("stuck in sending; UNI refunded", ts, wid),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE uni_withdrawals
                    SET status = 'failed', error = ?, completed_at = ?
                    WHERE withdrawal_id = ? AND status = 'sending'
                    """,
                    ("stuck in sending; UNI refunded", ts, wid),
                )
            if cur.rowcount != 1:
                continue
            owner_row = conn.execute(
                "SELECT owner_id FROM uni_wallets WHERE wallet_id = ?"
                if uni_db_backend() != "postgres"
                else "SELECT owner_id FROM uni_wallets WHERE wallet_id = %s",
                (wallet_id,),
            ).fetchone()
            owner_id = str(row_to_dict(owner_row).get("owner_id") or "") if owner_row else ""
            if owner_id and gross > 0:
                refunds.append((owner_id, gross, wid))
    return len(refunds), refunds
