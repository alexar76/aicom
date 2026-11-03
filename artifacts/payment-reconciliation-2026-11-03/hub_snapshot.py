"""Read the live Hub database using a WAL-aware SQLite read transaction."""
import json
import os
import sqlite3
import re
from datetime import datetime, timezone

import sys

dsn = os.getenv("DATABASE_URL")
if dsn:
    import psycopg
    from psycopg.rows import dict_row

    db = psycopg.connect(dsn, row_factory=dict_row)
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
else:
    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("AIMARKET_DB_PATH", "/app/data/hub.db")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only = ON")
    db.execute("BEGIN")

queries = {
    "x402": """SELECT status, asset, network, COUNT(*) n, SUM(CAST(amount_atomic AS INTEGER)) units,
      SUM(CASE WHEN COALESCE(receipt_id,'')='' THEN 1 ELSE 0 END) missing_receipt
      FROM x402_payments GROUP BY 1,2,3""",
    "x402_receipt_gaps": """SELECT nonce, capability_id, amount_atomic, asset, network,
      settle_tx_hash, created_at FROM x402_payments
      WHERE status = 'settled' AND COALESCE(receipt_id,'')='' ORDER BY created_at""",
    "x402_uncollected": """SELECT nonce, status, capability_id, amount_atomic, asset, network,
      created_at, COALESCE(receipt_id,'') receipt_id, COALESCE(settle_tx_hash,'') settle_tx_hash
      FROM x402_payments WHERE status <> 'settled' ORDER BY created_at""",
    "seller_invoice_orphans": """SELECT i.nonce, i.capability_id, i.tx_hash, i.amount_units,
      datetime(i.consumed_at,'unixepoch') consumed_utc FROM settle_invoices i
      WHERE i.consumed_at>0 AND NOT EXISTS (SELECT 1 FROM x402_payments x WHERE x.nonce=i.nonce)""",
    "seller_invoice_stats": """SELECT COUNT(*) n, SUM(consumed_at>0) consumed
      FROM settle_invoices""",
    "card": """SELECT status, livemode, COUNT(*) n, SUM(amount_cents) principal_cents,
      SUM(charge_cents) charge_cents, SUM(credited_mc) credited_mc FROM card_topups GROUP BY 1,2""",
    "card_candidates": """SELECT topup_id, status, session_id, payment_intent, livemode,
      amount_cents, charge_cents, credited_mc, datetime(created_at,'unixepoch') created_utc
      FROM card_topups WHERE status NOT IN ('credited','expired') ORDER BY created_at""",
    "channels": """SELECT status, chain, token, COUNT(*) n, SUM(balance_cents) balance_cents,
      SUM(original_deposit_cents) deposit_cents, SUM(used_cents) used_cents FROM channels GROUP BY 1,2,3""",
    "channels_with_balance": """SELECT channel_id, status, chain, token, balance_cents,
      original_deposit_cents, used_cents, tx_hash, expires_at, escrow_channel
      FROM channels WHERE balance_cents>0 ORDER BY expires_at""",
    "obligations": """SELECT o.status, o.chain, o.token, o.kind,
      CASE WHEN COALESCE(c.escrow_channel,'')<>'' THEN 'escrow' ELSE 'custodial' END rail,
      COUNT(*) n, SUM(o.amount_cents) amount_cents FROM channel_payout_obligations o
      LEFT JOIN channels c ON c.channel_id=o.channel_id GROUP BY 1,2,3,4,5""",
    "obligations_owed": """SELECT o.channel_id, o.chain, o.token, o.kind, o.amount_cents,
      o.deposit_tx_hash, o.payout_tx_hash, o.created_at, c.escrow_channel
      FROM channel_payout_obligations o LEFT JOIN channels c ON c.channel_id=o.channel_id
      WHERE o.status='owed' ORDER BY o.created_at""",
    "obligation_duplicate_payouts": """SELECT chain, payout_tx_hash, COUNT(*) n, SUM(amount_cents) cents
      FROM channel_payout_obligations WHERE status='paid' AND payout_tx_hash LIKE '0x%'
      GROUP BY 1,2 HAVING COUNT(*)>1""",
    "deposits": """SELECT status, COUNT(*) n, SUM(amount_units) units FROM hub_deposits GROUP BY 1""",
    "deposit_candidates": """SELECT tx_hash, block, status, amount_units, detail,
      datetime(seen_at,'unixepoch') seen_utc FROM hub_deposits
      WHERE status NOT IN ('credited','ignored') ORDER BY seen_at""",
    "credit_holds": """SELECT status, COUNT(*) n, SUM(amount_mc) amount_mc, MIN(created_at) oldest
      FROM credit_holds GROUP BY 1""",
    "credit_held": """SELECT receipt_id, amount_mc, created_at FROM credit_holds WHERE status='held'""",
    "channel_holds": """SELECT status, COUNT(*) n, SUM(amount_cents) amount_cents, MIN(created_at) oldest
      FROM channel_holds GROUP BY 1""",
    "channel_held": """SELECT receipt_id, channel_id, amount_cents, created_at
      FROM channel_holds WHERE status='held'""",
    "pipeline_refunds": """SELECT run_id, step_id, original_tx_hash, busy,
      json_extract(state_json,'$.status') state,
      json_extract(response_json,'$.status') outcome, datetime(updated_at,'unixepoch') updated_utc
      FROM pipeline_refunds WHERE json_valid(response_json) AND json_valid(state_json)""",
    "pipeline_refund_count": "SELECT COUNT(*) n, SUM(busy) busy FROM pipeline_refunds",
    "verified_pending": """SELECT nonce, channel_id, status, price_usd, attempts, created_at
      FROM verified_settlements WHERE status IN ('pending','processing')""",
    "credit_topups": """SELECT COUNT(*) n, SUM(amount_mc) amount_mc FROM credit_topups""",
}

result = {"snapshot_utc": datetime.now(timezone.utc).isoformat()}
result["card_environment"] = {k: os.environ[k] for k in
    ("AIMARKET_CARD_TOPUP_ENABLED", "AIMARKET_CARD_TOPUP", "AIMARKET_CARD_TOPUP_LIVE")
    if k in os.environ and os.environ[k].lower() in ("true", "false", "0", "1", "yes", "no", "on", "off")}
for label, query in queries.items():
    try:
        if dsn:
            query = re.sub(r"datetime\(([^,]+),'unixepoch'\)", r"to_timestamp(\1)", query)
            query = query.replace("SUM(consumed_at>0)", "SUM(CASE WHEN consumed_at>0 THEN 1 ELSE 0 END)")
            query = query.replace("CAST(amount_atomic AS INTEGER)", "CAST(amount_atomic AS BIGINT)")
            if label == "pipeline_refunds":
                query = query.replace("json_extract(state_json,'$.status')", "state_json::jsonb->>'status'")
                query = query.replace("json_extract(response_json,'$.status')", "NULLIF(response_json::text,'')::jsonb->>'status'")
                query = query.replace("WHERE json_valid(response_json) AND json_valid(state_json)", "")
            with db.transaction():
                result[label] = [dict(row) for row in db.execute(query)]
        else:
            result[label] = [dict(row) for row in db.execute(query)]
    except Exception as exc:
        result[label] = {"error": str(exc)}
db.rollback()
print(json.dumps(result, indent=2, default=str))
