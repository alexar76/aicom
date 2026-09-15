"""Tests for per-product live P&L (unit economics) aggregation."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from product_pnl import compute_product_pnl


def _make_orders_db(db_path: Path, rows: list[dict]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE orders ("
            "id TEXT PRIMARY KEY, customer_id TEXT, product_id TEXT, "
            "amount REAL, currency TEXT, status TEXT, created_at REAL)"
        )
        conn.executemany(
            "INSERT INTO orders (id, customer_id, product_id, amount, currency, status, created_at) "
            "VALUES (:id, :customer_id, :product_id, :amount, :currency, :status, :created_at)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _seed(tmp_path: Path) -> tuple[Path, float]:
    root = tmp_path / "data"
    now = time.time()
    (root / "store").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)

    # ── Revenue: prod-a has 3 paid orders from 2 customers; pending/failed excluded.
    _make_orders_db(
        root / "store" / "commerce.db",
        [
            {"id": "o1", "customer_id": "c1", "product_id": "prod-a", "amount": 30.0,
             "currency": "USDT", "status": "paid", "created_at": now - 100},
            {"id": "o2", "customer_id": "c2", "product_id": "prod-a", "amount": 20.0,
             "currency": "USDT", "status": "paid", "created_at": now - 50},
            {"id": "o3", "customer_id": "c1", "product_id": "prod-a", "amount": 10.0,
             "currency": "USDT", "status": "paid", "created_at": now - 10},
            {"id": "o4", "customer_id": "c3", "product_id": "prod-a", "amount": 99.0,
             "currency": "USDT", "status": "pending", "created_at": now},
            {"id": "o5", "customer_id": "c4", "product_id": "prod-b", "amount": 12.0,
             "currency": "USDT", "status": "failed", "created_at": now},
        ],
    )

    # ── Cost: state baseline; JSONL reconcile should win for prod-a (max).
    (root / "state" / "pipeline_product_cost.json").write_text(
        json.dumps({"products": {"prod-a": 4.0, "prod-b": 5.0}}), encoding="utf-8"
    )
    jsonl = root / "logs" / "llm_calls.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"product_id": "prod-a", "estimated_cost_usd": 6.0},
                {"product_id": "prod-a", "estimated_cost_usd": 4.0},  # prod-a jsonl sum = 10
                {"product_id": "prod-a"},  # no cost -> ignored
                {"estimated_cost_usd": 1.0},  # no product -> ignored
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # ── A discovered pre-revenue product (state dir only, no cost, no orders).
    (root / "state" / "prod-c").mkdir()
    (root / "state" / "prod-c" / "market_research.json").write_text(
        json.dumps({"idea": "Cool widget thing here with extra words beyond six"}),
        encoding="utf-8",
    )
    return root, now


def test_pnl_empty(tmp_path: Path):
    root = tmp_path / "data"
    (root / "store").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    out = compute_product_pnl(root)
    assert out["products"] == []
    assert out["portfolio"]["product_count"] == 0
    assert out["portfolio"]["net_profit_usd"] == 0.0


def test_pnl_unit_economics(tmp_path: Path):
    root, _ = _seed(tmp_path)
    out = compute_product_pnl(root)
    by_id = {p["product_id"]: p for p in out["products"]}

    # Universe = revenue ∪ cost ∪ prod-* dirs.
    assert set(by_id) == {"prod-a", "prod-b", "prod-c"}

    # prod-a: revenue 60 from 2 customers, COGS = max(state 4, jsonl 10) = 10.
    a = by_id["prod-a"]
    assert a["revenue_usd"] == 60.0
    assert a["units_sold"] == 3
    assert a["paying_customers"] == 2
    assert a["arpu_usd"] == 30.0
    assert a["inference_cost_usd"] == 10.0
    assert a["gross_profit_usd"] == 50.0
    assert a["gross_margin_pct"] == round(50 / 60 * 100, 1)  # ~83.3
    assert a["roi_pct"] == 500.0
    assert a["cost_recovery_pct"] == 600.0
    assert a["is_profitable"] is True
    assert a["status"] == "profitable"

    # prod-b: cost only, no revenue -> in the red, undefined margin.
    b = by_id["prod-b"]
    assert b["revenue_usd"] == 0.0
    assert b["inference_cost_usd"] == 5.0
    assert b["gross_profit_usd"] == -5.0
    assert b["gross_margin_pct"] is None
    assert b["roi_pct"] == -100.0
    assert b["status"] == "pre_revenue"

    # prod-c: discovered, fully zero, name derived from idea (first 6 words).
    c = by_id["prod-c"]
    assert c["revenue_usd"] == 0.0
    assert c["inference_cost_usd"] == 0.0
    assert c["name"] == "Cool widget thing here with extra"
    assert c["status"] == "pre_revenue"


def test_pnl_portfolio_rollup(tmp_path: Path):
    root, _ = _seed(tmp_path)
    pf = compute_product_pnl(root)["portfolio"]
    assert pf["product_count"] == 3
    assert pf["products_profitable"] == 1
    assert pf["products_pre_revenue"] == 2
    assert pf["total_revenue_usd"] == 60.0
    assert pf["total_inference_cost_usd"] == 15.0
    assert pf["net_profit_usd"] == 45.0
    assert pf["blended_margin_pct"] == 75.0
    assert pf["blended_roi_pct"] == 300.0
    assert pf["cost_recovery_pct"] == 400.0
    assert pf["best_product"] == "prod-a"
    assert pf["worst_product"] == "prod-b"
