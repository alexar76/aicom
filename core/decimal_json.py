"""JSON encoder for Decimal values — serializes as numbers (not strings).

Python's ``json.dumps`` raises ``TypeError`` on ``Decimal`` objects. This module
provides a ``default`` hook that converts ``Decimal`` → ``float`` so persisted
state files (llm_usage_guard.json, pipeline_product_cost.json, factory_wallet.json,
orders.json, llm_calls.jsonl, …) keep the same JSON number schema and the frontend
(TypeScript ``number`` / ``.toFixed(N)``) doesn't break.

For forward-compatibility, callers that want to serialize Decimal→string can pass
``allow_nan=False, default=decimal_json_decimal_string`` instead.

Usage:
    json.dumps(data, default=decimal_json_default)
    # or to serialize as "1.50" strings:
    json.dumps(data, default=decimal_json_string)
"""

from __future__ import annotations

import decimal
import json
from typing import Any


def decimal_json_default(obj: Any) -> Any:
    """json.dumps *default*: Decimal → float (JSON number)."""
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable"
    )


def decimal_json_string(obj: Any) -> Any:
    """json.dumps *default*: Decimal → "1.50" string (exact)."""
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable"
    )


def dumps(obj: Any, **kw: Any) -> str:
    """json.dumps with Decimal→float default baked in."""
    kw.setdefault("default", decimal_json_default)
    return json.dumps(obj, **kw)
