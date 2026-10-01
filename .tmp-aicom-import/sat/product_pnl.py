"""
Per-product live P&L (unit economics) for the autonomous factory.

Joins the two halves the factory already records:

* **Revenue** — paid rows in ``data/store/commerce.db`` (orders carry ``product_id``),
  converted to approximate USD with the same FX helper used by ``finance_stats``.
* **Inference COGS** — accumulated LLM spend per product from
  ``core.pipeline_cost_guard`` (``pipeline_product_cost.json`` reconciled against
  ``data/logs/llm_calls.jsonl``).

Monetary calculations use ``Decimal`` to avoid IEEE 754 float precision loss.

Output is a per-product unit-economics row (revenue, COGS, gross profit/margin,
ROI, cost-recovery) plus a portfolio rollup.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from core.paths import resolve_data_root

logger = logging.getLogger(__name__)

# Reuse the exact FX conversion finance_stats uses so portfolio totals reconcile.
try:
    from finance_stats import _amount_to_approx_usd as _to_usd
    from finance_stats import _norm_currency as _norm_currency
except Exception:

    def _norm_currency(c: str) -> str:
        return (c or "").strip().upper()

    def _to_usd(amount: Any, currency: str) -> Decimal:
        try:
            return Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")


def _to_decimal(value: Any) -> Decimal:
    """Coerce float / int / str / Decimal → Decimal safely."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _round2(x: Decimal) -> float:
    return float(round(x, 2))


def _pct(numer: Decimal, denom: Decimal) -> float | None:
    """Percentage numer/denom*100, or None when denominator is zero."""
    if denom == 0:
        return None
    return float(round((numer / denom) * Decimal("100"), 1))


# ────────────────────────────── revenue ──────────────────────────────


def _revenue_by_product(commerce_db: Path) -> dict[str, dict[str, Any]]:
    """Aggregate paid orders by ``product_id`` from commerce.db (read-only)."""
    out: dict[str, dict[str, Any]] = {}
    if not commerce_db.is_file():
        return out
    try:
        conn = sqlite3.connect(f"file:{commerce_db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        logger.warning("product_pnl: cannot open commerce.db: %s", exc)
        return out
    try:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT product_id, customer_id, amount, currency, status, created_at "
                "FROM orders WHERE status = 'paid'"
            ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("product_pnl: orders query failed: %s", exc)
            return out
    finally:
        conn.close()

    for r in rows:
        pid = str(r["product_id"] or "").strip()
        if not pid:
            continue
        amount = _to_decimal(r["amount"] or 0)
        currency = _norm_currency(str(r["currency"] or "USDT"))
        usd = _to_usd(amount, currency)
        ts = float(r["created_at"] or 0.0)
        cust = str(r["customer_id"] or "")

        entry = out.setdefault(
            pid,
            {
                "revenue_usd": Decimal("0"),
                "units_sold": 0,
                "_customers": set(),
                "first_sale_at": None,
                "last_sale_at": None,
            },
        )
        entry["revenue_usd"] += usd
        entry["units_sold"] += 1
        if cust:
            entry["_customers"].add(cust)
        if ts > 0:
            if entry["first_sale_at"] is None or ts < entry["first_sale_at"]:
                entry["first_sale_at"] = ts
            if entry["last_sale_at"] is None or ts > entry["last_sale_at"]:
                entry["last_sale_at"] = ts
    return out


# ────────────────────────────── cost ──────────────────────────────


def _cost_by_product(state_file: Path, llm_jsonl: Path) -> dict[str, Decimal]:
    """
    Inference COGS per product.

    Mirrors ``pipeline_cost_guard.product_spend_usd(reconcile_jsonl=True)`` —
    ``max(persisted_state, jsonl_sum)`` per product — but in a single pass over
    the JSONL rather than one scan per product.
    """
    state_map: dict[str, Decimal] = {}
    if state_file.is_file():
        try:
            raw = json.loads(state_file.read_text(encoding="utf-8"))
            products = raw.get("products") if isinstance(raw, dict) else None
            if isinstance(products, dict):
                for pid, val in products.items():
                    try:
                        state_map[str(pid)] = _to_decimal(val)
                    except (TypeError, ValueError):
                        continue
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("product_pnl: state read failed: %s", exc)

    jsonl_map: dict[str, Decimal] = {}
    if llm_jsonl.is_file():
        try:
            with open(llm_jsonl, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    pid = row.get("product_id")
                    est = row.get("estimated_cost_usd")
                    if not pid or est is None:
                        continue
                    try:
                        jsonl_map[str(pid)] = jsonl_map.get(str(pid), Decimal("0")) + _to_decimal(est)
                    except (TypeError, ValueError):
                        continue
        except OSError as exc:
            logger.debug("product_pnl: jsonl scan failed: %s", exc)

    out: dict[str, Decimal] = {}
    for pid in set(state_map) | set(jsonl_map):
        out[pid] = max(state_map.get(pid, Decimal("0")), jsonl_map.get(pid, Decimal("0")))
    return out


# ────────────────────────────── metadata ──────────────────────────────


def _display_name(state_root: Path, pid: str) -> str:
    """Best-effort human name from the product's state artifacts."""
    mr = state_root / pid / "market_research.json"
    if mr.is_file():
        try:
            idea = json.loads(mr.read_text(encoding="utf-8")).get("idea")
            if isinstance(idea, str) and idea.strip():
                words = idea.strip().split()
                return " ".join(words[:6])[:80]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return pid


def _discover_products(state_root: Path) -> set[str]:
    out: set[str] = set()
    if not state_root.is_dir():
        return out
    try:
        for d in state_root.iterdir():
            if d.is_dir() and d.name.startswith("prod-"):
                out.add(d.name)
    except OSError as exc:
        logger.debug("product_pnl: state scan failed: %s", exc)
    return out


# ────────────────────────────── public API ──────────────────────────────


def _classify(revenue: Decimal, cost: Decimal) -> str:
    if revenue <= 0:
        return "pre_revenue"
    if revenue >= cost:
        return "profitable"
    return "recovering"


def compute_product_pnl(
    data_root: str | Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Live per-product P&L plus portfolio rollup."""
    root = resolve_data_root(data_root)
    now = now or time.time()

    commerce_db = root / "store" / "commerce.db"
    state_root = root / "state"
    state_file = state_root / "pipeline_product_cost.json"
    llm_jsonl = root / "logs" / "llm_calls.jsonl"

    revenue = _revenue_by_product(commerce_db)
    cost = _cost_by_product(state_file, llm_jsonl)
    universe = set(revenue) | set(cost) | _discover_products(state_root)

    products: list[dict[str, Any]] = []
    tot_rev = Decimal("0")
    tot_cost = Decimal("0")

    for pid in sorted(universe):
        rev_entry = revenue.get(pid, {})
        rev = _to_decimal(rev_entry.get("revenue_usd", 0))
        units = int(rev_entry.get("units_sold", 0))
        customers = len(rev_entry.get("_customers", set()))
        cogs = _to_decimal(cost.get(pid, 0))
        profit = rev - cogs

        tot_rev += rev
        tot_cost += cogs

        products.append(
            {
                "product_id": pid,
                "name": _display_name(state_root, pid),
                "status": _classify(rev, cogs),
                "revenue_usd": _round2(rev),
                "units_sold": units,
                "paying_customers": customers,
                "arpu_usd": _round2(rev / customers) if customers else 0.0,
                "inference_cost_usd": float(round(cogs, 4)),
                "gross_profit_usd": _round2(profit),
                "gross_margin_pct": _pct(profit, rev),
                "roi_pct": _pct(profit, cogs),
                "cost_recovery_pct": _pct(rev, cogs),
                "is_profitable": profit > 0,
                "first_sale_at": rev_entry.get("first_sale_at"),
                "last_sale_at": rev_entry.get("last_sale_at"),
            }
        )

    ranked = sorted(products, key=lambda p: p["gross_profit_usd"], reverse=True)
    net = tot_rev - tot_cost
    portfolio = {
        "product_count": len(products),
        "products_profitable": sum(1 for p in products if p["status"] == "profitable"),
        "products_recovering": sum(1 for p in products if p["status"] == "recovering"),
        "products_pre_revenue": sum(1 for p in products if p["status"] == "pre_revenue"),
        "total_revenue_usd": _round2(tot_rev),
        "total_inference_cost_usd": float(round(tot_cost, 4)),
        "net_profit_usd": _round2(net),
        "blended_margin_pct": _pct(net, tot_rev),
        "blended_roi_pct": _pct(net, tot_cost),
        "cost_recovery_pct": _pct(tot_rev, tot_cost),
        "best_product": ranked[0]["product_id"] if ranked else None,
        "worst_product": ranked[-1]["product_id"] if ranked else None,
    }

    return {
        "generated_at": now,
        "fx_note": "Inference cost & FX are estimates (ops visibility, not billing).",
        "products": ranked,
        "portfolio": portfolio,
    }
