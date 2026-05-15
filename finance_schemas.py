"""Pydantic schemas for persisted commerce JSON files."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class StoreOrderRecord(BaseModel):
    """Single paid/pending order row in ``data/store/orders.json``."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    amount: float = Field(default=0.0, ge=0)
    currency: str = "USDT"
    status: str = ""
    created_at: float = 0.0


class PendingPaymentRecord(BaseModel):
    """Row in ``data/state/pending_payments.json``."""

    model_config = ConfigDict(extra="ignore")

    payment_id: str = ""
    status: str = ""
    expires_at: float = 0.0
    amount: float = Field(default=0.0, ge=0)
    currency: str = "USDT"


def parse_orders_blob(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            logger.warning("Skipping non-object order entry %s", key)
            continue
        try:
            out[str(key)] = StoreOrderRecord.model_validate(val).model_dump()
        except ValidationError as exc:
            logger.warning("Skipping invalid order %s: %s", key, exc)
    return out


def parse_pending_payments_blob(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            logger.warning("Skipping non-object pending payment %s", key)
            continue
        try:
            out[str(key)] = PendingPaymentRecord.model_validate(val).model_dump()
        except ValidationError as exc:
            logger.warning("Skipping invalid pending payment %s: %s", key, exc)
    return out
