"""
Aggregate commerce revenue from persisted orders and pending payments.
Used by Director metrics collector and admin dashboard (single source of truth).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.paths import resolve_data_root
from finance_schemas import parse_orders_blob, parse_pending_payments_blob

logger = logging.getLogger(__name__)

DEFAULT_ETH_USD = float(os.environ.get("AIFACTORY_ETH_USD", "3500"))
DEFAULT_SOL_USD = float(os.environ.get("AIFACTORY_SOL_USD", "150"))


def _norm_currency(c: str) -> str:
    return (c or "").strip().upper()


def _amount_to_approx_usd(amount: float, currency: str) -> float:
    """Map token amounts to approximate USD for mixed-currency totals (no live FX API)."""
    c = _norm_currency(currency)
    if c in ("USDT", "USDC", "DAI"):
        return float(amount)
    if c == "ETH":
        return float(amount) * DEFAULT_ETH_USD
    if c == "SOL":
        return float(amount) * DEFAULT_SOL_USD
    logger.debug("Unknown currency %s — counting amount as USD-equivalent raw", c)
    return float(amount)


def load_orders_dict(orders_path: Path) -> dict[str, Any]:
    if not orders_path.is_file():
        return {}
    try:
        with open(orders_path, encoding="utf-8") as f:
            data = json.load(f)
        return parse_orders_blob(data)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in orders %s: %s", orders_path, e)
        return {}
    except Exception as e:
        logger.warning("Failed to read orders %s: %s", orders_path, e)
        return {}


def load_pending_payments(pending_path: Path) -> dict[str, Any]:
    if not pending_path.is_file():
        return {}
    try:
        with open(pending_path, encoding="utf-8") as f:
            data = json.load(f)
        return parse_pending_payments_blob(data)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in pending payments %s: %s", pending_path, e)
        return {}
    except Exception as e:
        logger.warning("Failed to read pending payments %s: %s", pending_path, e)
        return {}


def compute_financial_metrics(
    data_root: str | Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """
    Full financial snapshot from orders.json + pending_payments.json.
    All monetary aggregates include approximate USD for SOL/ETH via env rates.
    """
    root = resolve_data_root(data_root)
    now = now or time.time()
    orders_path = root / "store" / "orders.json"
    pending_path = root / "state" / "pending_payments.json"

    orders = load_orders_dict(orders_path)
    pending_all = load_pending_payments(pending_path)

    total_revenue_usdt = 0.0
    total_revenue_usdc = 0.0
    total_revenue_eth = 0.0
    total_revenue_sol = 0.0
    transactions_completed = 0

    for order in orders.values():
        if not isinstance(order, dict):
            continue
        if order.get("status") != "paid":
            continue
        transactions_completed += 1
        amt = float(order.get("amount") or 0)
        cur = _norm_currency(str(order.get("currency") or "USDT"))
        if cur == "USDT":
            total_revenue_usdt += amt
        elif cur == "USDC":
            total_revenue_usdc += amt
        elif cur == "ETH":
            total_revenue_eth += amt
        elif cur == "SOL":
            total_revenue_sol += amt

    def window_sum(seconds: float) -> dict[str, float]:
        cutoff = now - seconds
        usd = 0.0
        for order in orders.values():
            if not isinstance(order, dict) or order.get("status") != "paid":
                continue
            ts = float(order.get("created_at") or 0)
            if ts < cutoff:
                continue
            usd += _amount_to_approx_usd(
                float(order.get("amount") or 0),
                str(order.get("currency") or "USDT"),
            )
        return {"approx_usd": usd}

    w24 = window_sum(86400)
    w7 = window_sum(86400 * 7)
    w30 = window_sum(86400 * 30)

    transactions_pending = 0
    transactions_failed = 0
    for pay in pending_all.values():
        if not isinstance(pay, dict):
            continue
        st = pay.get("status")
        exp = float(pay.get("expires_at") or 0)
        if st == "pending" and exp > now:
            transactions_pending += 1
        elif st == "failed":
            transactions_failed += 1

    total_approx_usd = (
        total_revenue_usdt
        + total_revenue_usdc
        + total_revenue_eth * DEFAULT_ETH_USD
        + total_revenue_sol * DEFAULT_SOL_USD
    )

    out = {
        "total_revenue_usdt": round(total_revenue_usdt, 6),
        "total_revenue_usdc": round(total_revenue_usdc, 6),
        "total_revenue_eth": round(total_revenue_eth, 8),
        "total_revenue_sol": round(total_revenue_sol, 8),
        "total_revenue_approx_usd": round(total_approx_usd, 2),
        "transactions_pending": transactions_pending,
        "transactions_completed": transactions_completed,
        "transactions_failed": transactions_failed,
        "revenue_last_24h_approx_usd": round(w24["approx_usd"], 2),
        "revenue_last_7d_approx_usd": round(w7["approx_usd"], 2),
        "revenue_last_30d_approx_usd": round(w30["approx_usd"], 2),
        "fx_note": f"ETH_USD={DEFAULT_ETH_USD} SOL_USD={DEFAULT_SOL_USD} (override via AIFACTORY_ETH_USD / AIFACTORY_SOL_USD)",
    }
    # Backward-compatible aliases (older dashboards / docs)
    out["revenue_last_24h"] = out["revenue_last_24h_approx_usd"]
    out["revenue_last_7d"] = out["revenue_last_7d_approx_usd"]
    out["revenue_last_30d"] = out["revenue_last_30d_approx_usd"]
    try:
        from core.uni.config import uni_enabled
        from core.uni.wallet import UniWalletService

        if uni_enabled():
            out["uni"] = UniWalletService().economy_summary()
    except Exception as exc:
        logger.debug("UNI finance metrics skipped: %s", exc)
    return out


def compute_dashboard_revenue(
    data_root: str | Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Subset for admin dashboard (backward-compatible keys + detail)."""
    m = compute_financial_metrics(data_root, now)
    return {
        "last_24h": m["revenue_last_24h_approx_usd"],
        "last_7d": m["revenue_last_7d_approx_usd"],
        "last_30d": m["revenue_last_30d_approx_usd"],
        "total_approx_usd": m["total_revenue_approx_usd"],
        "total_usdt": m["total_revenue_usdt"],
        "total_usdc": m["total_revenue_usdc"],
        "orders_completed": m["transactions_completed"],
        "payments_pending": m["transactions_pending"],
    }
