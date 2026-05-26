"""Signed UNI receipts (shared across Factory, Market, Hub, Monitor)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.uni.config import uni_db_backend
from core.uni.store import dumps_meta, row_to_dict, uni_connection


def canonical_receipt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Stable signing body: scalar fields only, sorted keys, string amounts."""
    body: dict[str, Any] = {}
    for key in sorted(payload):
        if key == "signature":
            continue
        val = payload[key]
        if key.endswith("_uni") and val is not None:
            body[key] = str(int(round(float(val))))
        elif isinstance(val, (str, int, float, bool)) or val is None:
            body[key] = val
    return body


def verify_receipt(payload: dict[str, Any]) -> bool:
    """Verify ed25519 signature over canonical receipt fields."""
    if not isinstance(payload, dict):
        return False
    sig_block = payload.get("signature")
    if not isinstance(sig_block, dict):
        return False
    signature = str(sig_block.get("value") or "")
    if not signature:
        return False
    from core.uni.signing import public_key_b64, sign_payload

    if str(sig_block.get("public_key") or "") != public_key_b64():
        return False
    body = canonical_receipt_payload(payload)
    expected = sign_payload(body)
    return expected == signature


def issue_receipt(
    *,
    wallet_id: str,
    kind: str,
    amount_uni: int | float,
    meta: dict[str, Any],
    idempotency_key: str | None = None,
    buyer_wallet_id: str | None = None,
    seller_wallet_id: str | None = None,
    platform_fee_uni: int = 0,
    net_to_seller_uni: int = 0,
    product_id: str | None = None,
    capability_id: str | None = None,
    tx_hash: str | None = None,
    chain: str | None = None,
    hub_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    receipt_id = f"rcpt_{uuid.uuid4().hex[:16]}"
    ts = time.time()
    from core.uni.signing import public_key_b64, sign_payload

    # Capture the OTel trace id at issue-time when the caller didn't supply
    # one explicitly. Goes into the signed payload so a receipt holder can
    # later prove "this UNI debit produced THIS LLM trace in LangSmith".
    if not trace_id:
        try:
            from core.tracing import current_trace_id_hex

            trace_id = current_trace_id_hex()
        except Exception:
            trace_id = None

    amount_i = int(round(float(amount_uni)))
    payload: dict[str, Any] = {
        "id": receipt_id,
        "wallet_id": wallet_id,
        "kind": kind,
        "amount_uni": str(amount_i),
        "platform_fee_uni": str(int(platform_fee_uni)),
        "net_to_seller_uni": str(int(net_to_seller_uni)),
        "ts": ts,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    for k, v in meta.items():
        if k in payload or k == "signature":
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            payload[k] = v
    sign_body = canonical_receipt_payload(payload)
    signature = sign_payload(sign_body)
    payload["signature"] = {
        "algorithm": "ed25519",
        "public_key": public_key_b64(),
        "value": signature,
    }
    stored_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    idem = (idempotency_key or receipt_id).strip()[:128]
    cols = [
        "receipt_id", "wallet_id", "kind", "amount_uni", "payload_json", "signature", "ts", "idempotency_key",
        "buyer_wallet_id", "seller_wallet_id", "platform_fee_uni", "net_to_seller_uni",
        "product_id", "capability_id", "tx_hash", "chain", "hub_id", "status", "trace_id",
    ]
    vals = [
        receipt_id, wallet_id, kind, amount_i, stored_json, signature, ts, idem,
        buyer_wallet_id, seller_wallet_id, int(platform_fee_uni), int(net_to_seller_uni),
        product_id, capability_id, tx_hash, chain, hub_id, "committed", trace_id,
    ]
    placeholders = ", ".join(["%s"] * len(cols)) if uni_db_backend() == "postgres" else ", ".join(["?"] * len(cols))
    col_sql = ", ".join(cols)
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            conn.execute(
                f"""
                INSERT INTO uni_receipts ({col_sql})
                VALUES ({placeholders})
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                tuple(vals),
            )
        else:
            try:
                conn.execute(
                    f"INSERT INTO uni_receipts ({col_sql}) VALUES ({placeholders})",
                    tuple(vals),
                )
            except Exception as exc:
                if "UNIQUE" not in str(exc).upper():
                    raise
    return payload


def get_receipt(receipt_id: str) -> dict[str, Any] | None:
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            row = conn.execute(
                "SELECT payload_json, wallet_id FROM uni_receipts WHERE receipt_id = %s",
                (receipt_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT payload_json, wallet_id FROM uni_receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
    if not row:
        return None
    data = row_to_dict(row)
    try:
        payload = json.loads(data.get("payload_json") or "{}")
    except json.JSONDecodeError:
        return None
    payload["_wallet_id"] = data.get("wallet_id")
    return payload


def list_receipts_for_wallet(wallet_id: str, *, since: float = 0.0, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with uni_connection() as conn:
        if uni_db_backend() == "postgres":
            rows = conn.execute(
                """
                SELECT payload_json FROM uni_receipts
                WHERE wallet_id = %s AND ts >= %s
                ORDER BY ts DESC LIMIT %s
                """,
                (wallet_id, since, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT payload_json FROM uni_receipts
                WHERE wallet_id = ? AND ts >= ?
                ORDER BY ts DESC LIMIT ?
                """,
                (wallet_id, since, limit),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append(json.loads(row_to_dict(row).get("payload_json") or "{}"))
        except json.JSONDecodeError:
            continue
    return out
