"""
Per-product LLM spend cap for the autonomous pipeline.

When ``quality.max_pipeline_cost_usd`` in Admin settings (or ``AIFACTORY_MAX_PIPELINE_COST_USD`` env) is > 0, each product_id accumulates
``estimated_cost_usd`` from ``data/logs/llm_calls.jsonl`` (and in-memory state) until
the cap is reached; further agent tasks abort with :class:`PipelineCostBudgetExceeded`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from typing import Any

from core.paths import logs_dir, state_dir

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE: dict[str, float] = {}
_STATE_LOADED = False
_STATE_PATH = state_dir() / "pipeline_product_cost.json"


class PipelineCostBudgetExceeded(RuntimeError):
    """Raised when a product exceeds its configured LLM budget."""

    def __init__(self, product_id: str, spent_usd: float, cap_usd: float):
        self.product_id = product_id
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        super().__init__(
            f"Pipeline LLM budget exceeded for {product_id}: "
            f"${spent_usd:.4f} spent (cap ${cap_usd:.2f})"
        )


def effective_max_pipeline_cost_usd() -> float:
    """0 disables the per-product cap. See ``core.quality_settings.max_pipeline_cost_usd``."""
    from core.quality_settings import max_pipeline_cost_usd

    return max_pipeline_cost_usd()


def pipeline_cost_guard_enabled() -> bool:
    return effective_max_pipeline_cost_usd() > 0


def _load_state_file() -> dict[str, float]:
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
    out: dict[str, float] = {}
    for pid, val in products.items():
        try:
            out[str(pid)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _persist_state() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": time.time(), "products": dict(_STATE)}
    tmp = _STATE_PATH.with_name(f"{_STATE_PATH.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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


def _sum_jsonl_for_product(product_id: str) -> float:
    log_file = logs_dir() / "llm_calls.jsonl"
    if not log_file.exists():
        return 0.0
    total = 0.0
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
                    total += float(est)
                except (TypeError, ValueError):
                    continue
    except OSError as exc:
        logger.debug("pipeline cost jsonl scan failed: %s", exc)
    return total


def product_spend_usd(product_id: str, *, reconcile_jsonl: bool = False) -> float:
    """Return accumulated USD spend for ``product_id``."""
    if not product_id:
        return 0.0
    _ensure_loaded()
    with _LOCK:
        spent = float(_STATE.get(product_id, 0.0))
    if reconcile_jsonl:
        from_jsonl = _sum_jsonl_for_product(product_id)
        spent = max(spent, from_jsonl)
        with _LOCK:
            if from_jsonl > _STATE.get(product_id, 0.0):
                _STATE[product_id] = from_jsonl
                _persist_state()
    return spent


def record_product_llm_spend(product_id: str, usd: float) -> None:
    if not product_id or usd <= 0:
        return
    _ensure_loaded()
    with _LOCK:
        _STATE[product_id] = float(_STATE.get(product_id, 0.0)) + float(usd)
        _persist_state()


def assert_product_within_budget(product_id: str) -> None:
    """Raise :class:`PipelineCostBudgetExceeded` when the cap is exceeded."""
    cap = effective_max_pipeline_cost_usd()
    if cap <= 0 or not product_id:
        return
    spent = product_spend_usd(product_id, reconcile_jsonl=True)
    if spent >= cap:
        raise PipelineCostBudgetExceeded(product_id, spent, cap)


def check_product_budget(product_id: str) -> tuple[bool, float, float]:
    """Return ``(ok, spent_usd, cap_usd)``; cap 0 means disabled (always ok)."""
    cap = effective_max_pipeline_cost_usd()
    if cap <= 0 or not product_id:
        return True, 0.0, cap
    spent = product_spend_usd(product_id, reconcile_jsonl=True)
    return spent < cap, spent, cap


def reset_pipeline_cost_state_for_tests() -> None:
    """Test helper — clear in-memory cache (does not delete the state file)."""
    global _STATE_LOADED
    with _LOCK:
        _STATE.clear()
        _STATE_LOADED = False


def ingest_llm_log_entry(entry: dict[str, Any]) -> None:
    """Hook from ``record_llm_call_spend`` when ``product_id`` is present."""
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
