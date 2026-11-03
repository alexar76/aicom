"""ACEX Agent IPO ledger tests — listing, CapShares, revenue routing, claims.

Pure-module tests (no HTTP app), so they run on Python 3.9+ regardless of the
plugin entry-points API. Each test gets an isolated SQLite file.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setenv("ACEX_REVENUE_SHARE_BPS", "5000")  # 50%
    monkeypatch.setenv("ACEX_DEFAULT_MAX_SUPPLY", "1000000")
    monkeypatch.setenv("ACEX_TREASURY_HOLDER", "factory-treasury")
    monkeypatch.setenv("ACEX_MIN_AUDIT_SCORE_BPS", "7000")
    with tempfile.TemporaryDirectory() as tmp:
        # Reload module so env vars above are picked up, then point it at a temp DB.
        import importlib

        import aimarket_hub.acex_ipo as ipo
        importlib.reload(ipo)
        db_path = Path(tmp) / "acex_ipo.db"
        led = ipo.AcexIpoLedger(str(db_path))
        yield led


def test_float_mints_full_supply_to_treasury(ledger):
    state = ledger.float_product("prod-translate", name="Translator", symbol="CAPTR")
    assert state["already_listed"] is False
    assert state["status"] == "approved"
    assert state["trading_enabled"] is True
    assert state["shares_outstanding"] == 1_000_000

    cap = ledger.cap_table("prod-translate")
    assert cap["holders"] == [
        {"holder": "factory-treasury", "shares": 1_000_000, "pct": 100.0}
    ]


def test_float_is_idempotent(ledger):
    a = ledger.float_product("prod-x")
    b = ledger.float_product("prod-x")
    assert a["already_listed"] is False
    assert b["already_listed"] is True
    assert ledger.cap_table("prod-x")["shares_outstanding"] == 1_000_000


def test_audit_gate_rejects_low_score(ledger):
    res = ledger.float_product("prod-bad", audit_score_bps=5000)
    assert res["error"] == "audit_score_too_low"
    assert ledger.listing_state("prod-bad").get("error") == "unknown_listing"


def test_revenue_share_bps_applied_on_accrue(ledger):
    ledger.float_product("prod-y", revenue_share_bps=5000)
    r = ledger.accrue_revenue("prod-y", 1.00)  # 50% → pool
    assert r["to_pool_usd"] == 0.50
    rev = ledger.revenue_state("prod-y")
    assert rev["gross_revenue_usd"] == 1.00
    assert rev["accrued_undistributed_usd"] == 0.50


def test_accrue_on_unknown_listing_is_safe(ledger):
    assert ledger.accrue_revenue("nope", 1.0)["error"] == "unknown_listing"


def test_distribute_pro_rata_after_secondary_allocation(ledger):
    ledger.float_product("prod-z", revenue_share_bps=10000)  # 100% to pool for clean math
    # Treasury sells 250k shares (25%) to an investor.
    assert ledger.transfer_shares("prod-z", "factory-treasury", "investor-a", 250_000)["ok"]

    ledger.accrue_revenue("prod-z", 4.00)  # whole $4 to pool
    dist = ledger.distribute("prod-z")
    assert dist["distributed_usd"] == 4.00

    payouts = {p["holder"]: p["amount_usd"] for p in dist["payouts"]}
    assert payouts["factory-treasury"] == 3.00   # 75%
    assert payouts["investor-a"] == 1.00          # 25%

    # Claimable reflects distribution; claim zeroes it.
    assert ledger.holder_position("prod-z", "investor-a")["claimable_usd"] == 1.00
    assert ledger.claim("prod-z", "investor-a")["claimed_usd"] == 1.00
    assert ledger.holder_position("prod-z", "investor-a")["claimable_usd"] == 0.0

    # Pool drained after distribution.
    assert ledger.revenue_state("prod-z")["accrued_undistributed_usd"] == 0.0
    assert ledger.revenue_state("prod-z")["distributed_usd"] == 4.00


def test_distribution_is_exact_no_drift(ledger):
    """Indivisible pool across 3 unequal holders must sum back to the pool exactly."""
    ledger.float_product("prod-d", revenue_share_bps=10000)
    ledger.transfer_shares("prod-d", "factory-treasury", "b", 333_333)
    ledger.transfer_shares("prod-d", "factory-treasury", "c", 333_333)
    # treasury now holds 333_334; total 1_000_000

    ledger.accrue_revenue("prod-d", 0.01)  # 1 cent — not cleanly divisible by 3
    dist = ledger.distribute("prod-d")
    total = round(sum(p["amount_usd"] for p in dist["payouts"]), 6)
    assert total == 0.01
    assert dist["distributed_usd"] == 0.01


def test_transfer_guards(ledger):
    ledger.float_product("prod-g")
    assert ledger.transfer_shares("prod-g", "factory-treasury", "x", 5_000_000)["error"] == "insufficient_shares"
    assert ledger.transfer_shares("prod-g", "factory-treasury", "factory-treasury", 1)["error"] == "self_transfer"
    assert ledger.transfer_shares("unknown", "a", "b", 1)["error"] == "unknown_listing"


def test_claim_nothing_is_safe(ledger):
    ledger.float_product("prod-c")
    res = ledger.claim("prod-c", "factory-treasury")
    assert res["ok"] is True
    assert res["claimed_usd"] == 0.0


# ── F7 anti-Sybil revenue gate ───────────────────────────────────


def test_listing_revenue_gate_off_by_default(ledger):
    # ACEX_MIN_LISTING_REVENUE_USD unset → gate disabled, zero-revenue float still works.
    res = ledger.float_product("prod-default")
    assert "error" not in res
    assert res["status"] == "approved"


def test_listing_revenue_gate_blocks_zero_revenue_sybil(ledger, monkeypatch):
    monkeypatch.setenv("ACEX_MIN_LISTING_REVENUE_USD", "5")
    res = ledger.float_product("prod-sybil")  # prior_revenue_usd defaults to 0
    assert res["error"] == "insufficient_prior_revenue"
    assert res["min_listing_revenue_usd"] == 5.0


def test_listing_revenue_gate_allows_proven_revenue(ledger, monkeypatch):
    monkeypatch.setenv("ACEX_MIN_LISTING_REVENUE_USD", "5")
    res = ledger.float_product("prod-real", prior_revenue_usd=10.0)
    assert "error" not in res
    assert res["status"] == "approved"
