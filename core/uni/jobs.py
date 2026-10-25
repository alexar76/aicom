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
    """Recover unsent payouts through a durable, idempotent refund queue.

    There is no chain payout adapter yet. Enabling the configuration flag must
    never masquerade as sending money or strand a request in ``sending``.
    Rows with a transaction hash are ambiguous and require chain reconciliation;
    elapsed time alone is never evidence that a transfer did not land.
    """
    if not uni_enabled():
        return {"skipped": True}
    import os

    dispatcher_live = os.environ.get("AIFACTORY_UNI_WITHDRAW_DISPATCHER", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    ts = now_ts()
    pg = uni_db_backend() == "postgres"
    query = """
        SELECT withdrawal_id, status FROM uni_withdrawals w
        WHERE (tx_hash IS NULL OR tx_hash = '') AND (
          status IN ('queued', 'refund_due')
          OR (status = 'sending' AND requested_at < ?)
          OR (status = 'failed' AND (fee_credited != 0 OR NOT EXISTS (
            SELECT 1 FROM uni_ledger l WHERE l.idempotency_key IN (
              'grant:withdraw-refund:' || w.withdrawal_id,
              'grant:withdraw-reap:' || w.withdrawal_id))))
        )
        ORDER BY requested_at LIMIT ?
    """
    if pg:
        query = query.replace("?", "%s") + " FOR UPDATE SKIP LOCKED"
    processed = reaped = 0
    pending = []
    with uni_connection() as conn:
        rows = conn.execute(query, (ts - _STUCK_SENDING_SEC, max(1, int(max_batch)))).fetchall()
        for raw in rows:
            row = row_to_dict(raw)
            wid = row["withdrawal_id"]
            processed += row["status"] == "queued"
            reaped += row["status"] == "sending"
            statement = ("UPDATE uni_withdrawals SET status='refund_due', "
                         "error='payout adapter unavailable; refund pending' WHERE withdrawal_id=?")
            conn.execute(statement.replace("?", "%s") if pg else statement, (wid,))
            pending.append(wid)

    svc = UniWalletService()
    failed_refunded = 0
    for wid in pending:
        try:
            result = svc.refund_withdrawal(wid)
            failed_refunded += not result["duplicate"]
        except Exception:
            # The durable refund_due row survives both exceptions and a process
            # exit. A later pass retries, and the ledger key prevents duplicates.
            logger.exception("withdraw refund pending for %s", wid)
    return {
        "processed": processed,
        "failed_refunded": failed_refunded,
        "reaped_stuck_sending": reaped,
        "dispatcher_live": dispatcher_live,
        "payout_available": False,
    }
