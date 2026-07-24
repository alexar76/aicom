"""Pydantic schemas for persisted commerce JSON files.

All monetary amounts use ``Decimal`` to avoid IEEE 754 float precision loss.
JSON input (``float`` / ``int`` / ``str``) is coerced to ``Decimal`` automatically.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


def _coerce_decimal(v: Any) -> Decimal:
    """Coerce float / int / str → Decimal, stripping whitespace from strings."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        return Decimal(v.strip())
    return Decimal(str(v))


class StoreOrderRecord(BaseModel):
    """Single paid/pending order row in ``data/store/orders.json``."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = "USDT"
    status: str = ""
    created_at: float = 0.0

    @field_validator("amount", mode="before")
    @classmethod
    def _amount_to_decimal(cls, v: Any) -> Decimal:
        return _coerce_decimal(v)


class PendingPaymentRecord(BaseModel):
    """Row in ``data/state/pending_payments.json``."""

    model_config = ConfigDict(extra="ignore")

    payment_id: str = ""
    status: str = ""
    expires_at: float = 0.0
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = "USDT"

    @field_validator("amount", mode="before")
    @classmethod
    def _amount_to_decimal(cls, v: Any) -> Decimal:
        return _coerce_decimal(v)


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
