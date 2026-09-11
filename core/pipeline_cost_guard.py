"""
Per-product LLM spend cap for the autonomous pipeline.

Monetary amounts use ``Decimal`` for precision.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from core.decimal_json import dumps as _json_dumps
from core.paths import logs_dir, state_dir

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE: dict[str, Decimal] = {}
_STATE_LOADED = False
_STATE_PATH = state_dir() / "pipeline_product_cost.json"


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


class PipelineCostBudgetExceeded(RuntimeError):
    def __init__(self, product_id: str, spent_usd: Decimal, cap_usd: Decimal):
        self.product_id = product_id
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        super().__init__(f"Pipeline LLM budget exceeded for {product_id}: ${spent_usd:.4f} spent (cap ${cap_usd:.2f})")


def effective_max_pipeline_cost_usd() -> Decimal:
    from core.quality_settings import max_pipeline_cost_usd
    return _to_decimal(max_pipeline_cost_usd())


def pipeline_cost_guard_enabled() -> bool:
    return effective_max_pipeline_cost_usd() > 0


def _load_state_file() -> dict[str, Decimal]:
    if not _STATE_PATH.exists():
        return {}
    try:
        raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read pipeline cost state: %s", exc)
        return {}
    products = raw.get("products") if isinstance(raw, dict) else None
    if not isinstance(products, dict):
        return {}
    out: dict[str, Decimal] = {}
    for pid, val in products.items():
        try:
            out[str(pid)] = _to_decimal(val)
        except (TypeError, ValueError):
            continue
    return out


def _persist_state() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": time.time(), "products": {k: float(v) for k, v in _STATE.items()}}
    tmp = _STATE_PATH.with_name(f"{_STATE_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(_json_dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(_STATE_PATH)
    finally:
        if tmp.exists() and tmp != _STATE_PATH:
            with contextlib.suppress(OSError):
                tmp.unlink()


def _ensure_loaded() -> None:
    global _STATE_LOADED
    if _STATE_LOADED:
        return
    with _LOCK:
        if _STATE_LOADED:
            return
        _STATE.update(_load_state_file())
        _STATE_LOADED = True


def _sum_jsonl_for_product(product_id: str) -> Decimal:
    log_file = logs_dir() / "llm_calls.jsonl"
    if not log_file.exists():
        return Decimal("0")
    total = Decimal("0")
    try:
        with open(log_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("product_id") != product_id:
                    continue
                est = row.get("estimated_cost_usd")
                if est is None:
                    continue
                try:
                    total += _to_decimal(est)
                except (TypeError, ValueError):
                    continue
    except OSError as exc:
        logger.debug("pipeline cost jsonl scan failed: %s", exc)
    return total


def product_spend_usd(product_id: str, *, reconcile_jsonl: bool = False) -> Decimal:
    if not product_id:
        return Decimal("0")
    _ensure_loaded()
    with _LOCK:
        spent = _STATE.get(product_id, Decimal("0"))
    if reconcile_jsonl:
        from_jsonl = _sum_jsonl_for_product(product_id)
        spent = max(spent, from_jsonl)
        with _LOCK:
            if from_jsonl > _STATE.get(product_id, Decimal("0")):
                _STATE[product_id] = from_jsonl
                _persist_state()
    return spent


def record_product_llm_spend(product_id: str, usd: float) -> None:
    if not product_id or usd <= 0:
        return
    usd_d = _to_decimal(usd)
    _ensure_loaded()
    with _LOCK:
        _STATE[product_id] = _STATE.get(product_id, Decimal("0")) + usd_d
        _persist_state()


def assert_product_within_budget(product_id: str) -> None:
    cap = effective_max_pipeline_cost_usd()
    if cap <= 0 or not product_id:
        return
    spent = product_spend_usd(product_id, reconcile_jsonl=True)
    if spent >= cap:
        raise PipelineCostBudgetExceeded(product_id, spent, cap)


def check_product_budget(product_id: str) -> tuple[bool, Decimal, Decimal]:
    cap = effective_max_pipeline_cost_usd()
    if cap <= 0 or not product_id:
        return True, Decimal("0"), cap
    spent = product_spend_usd(product_id, reconcile_jsonl=True)
    return spent < cap, spent, cap


def reset_pipeline_cost_state_for_tests() -> None:
    global _STATE_LOADED
    with _LOCK:
        _STATE.clear()
        _STATE_LOADED = False


def ingest_llm_log_entry(entry: dict[str, Any]) -> None:
    if not pipeline_cost_guard_enabled():
        return
    pid = entry.get("product_id")
    est = entry.get("estimated_cost_usd")
    if not pid or est is None:
        return
    try:
        record_product_llm_spend(str(pid), float(est))
    except (TypeError, ValueError):
        return
