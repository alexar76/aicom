"""Signed payment receipts."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from web.backend.services.ai_market_protocol.paths import receipts_path
from web.backend.services.ai_market_protocol.signing import sign_payload


def _load_receipts() -> dict[str, Any]:
    p = receipts_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_receipts(data: dict[str, Any]) -> None:
    receipts_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def create_receipt(
    *,
    product_id: str,
    capability_id: str,
    amount_usd: float,
    payment_kind: str,
    payment_ref: str,
    success: bool,
    result_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nonce = f"rcpt_{uuid.uuid4().hex[:16]}"
    body = {
        "nonce": nonce,
        "time": time.time(),
        "product_id": product_id,
        "capability_id": capability_id,
        "amount_usd": round(amount_usd, 4),
        "payment_kind": payment_kind,
        "payment_ref": payment_ref,
        "success": success,
        "result_summary": result_summary or {},
    }
    body["signature"] = sign_payload(body)
    data = _load_receipts()
    data[nonce] = body
    _save_receipts(data)
    return body


def get_receipt(nonce: str) -> dict[str, Any] | None:
    return _load_receipts().get(nonce)
