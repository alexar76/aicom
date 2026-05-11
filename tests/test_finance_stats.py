"""Tests for finance aggregation from orders and pending payments."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from finance_stats import compute_dashboard_revenue, compute_financial_metrics


def test_financial_metrics_empty(tmp_path: Path):
    root = tmp_path / "data"
    (root / "store").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    m = compute_financial_metrics(root)
    assert m["transactions_completed"] == 0
    assert m["total_revenue_approx_usd"] == 0
    assert m["revenue_last_24h"] == 0


def test_financial_metrics_orders(tmp_path: Path):
    root = tmp_path / "data"
    (root / "store").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    now = time.time()
    orders = {
        "ord-a": {
            "id": "ord-a",
            "amount": 10.0,
            "currency": "USDT",
            "status": "paid",
            "created_at": now,
        }
    }
    (root / "store" / "orders.json").write_text(json.dumps(orders), encoding="utf-8")

    m = compute_financial_metrics(root, now=now + 10)
    assert m["transactions_completed"] == 1
    assert m["total_revenue_usdt"] == 10.0
    assert m["total_revenue_approx_usd"] == 10.0


def test_pending_count(tmp_path: Path):
    root = tmp_path / "data"
    (root / "state").mkdir(parents=True)
    now = time.time()
    pending = {
        "pay-1": {
            "payment_id": "pay-1",
            "status": "pending",
            "expires_at": now + 3600,
        }
    }
    (root / "state" / "pending_payments.json").write_text(json.dumps(pending), encoding="utf-8")
    m = compute_financial_metrics(root, now=now + 10)
    assert m["transactions_pending"] == 1


def test_dashboard_revenue_keys(tmp_path: Path):
    root = tmp_path / "data"
    (root / "store").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    r = compute_dashboard_revenue(root)
    assert "last_24h" in r and "total_approx_usd" in r
