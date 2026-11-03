"""Proof-of-Audit hub ledger tests — coverage sync, invoke revenue routing, claims."""

import importlib
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def ledgers(monkeypatch):
    monkeypatch.setenv("ACEX_REVENUE_SHARE_BPS", "5000")
    monkeypatch.setenv("ACEX_DEFAULT_MAX_SUPPLY", "1000000")
    monkeypatch.setenv("ACEX_TREASURY_HOLDER", "factory-treasury")
    monkeypatch.setenv("ACEX_MIN_AUDIT_SCORE_BPS", "7000")
    monkeypatch.setenv("ACEX_AUDIT_FEE_BPS", "100")
    with tempfile.TemporaryDirectory() as tmp:
        import aimarket_hub.acex_ipo as ipo
        import aimarket_hub.acex_audit as audit

        importlib.reload(ipo)
        importlib.reload(audit)
        ipo_db = Path(tmp) / "acex_ipo.db"
        audit_db = Path(tmp) / "acex_audit.db"
        ipo_led = ipo.AcexIpoLedger(str(ipo_db))
        ipo._ledger = ipo_led
        audit._ledger = audit.AcexAuditLedger(str(audit_db))
        yield ipo_led, audit


def test_bootstrap_coverage_from_approved_ipo(ledgers):
    ipo, audit = ledgers
    ipo.float_product("prod-a", audit_score_bps=8000)
    st = audit.listing_audit_state("prod-a")
    assert st["enabled"] is True
    assert st["aggregate_score_bps"] == 8000
    assert st["auditor_count"] == 1
    assert st["coverages"][0]["auditor"] == "ai-auditor:acex-v1"


def test_accrue_splits_fee_by_cover_weight(ledgers):
    ipo, audit = ledgers
    ipo.float_product("prod-b", audit_score_bps=7500)
    audit.sync_coverage("prod-b", "auditor-big", cover_usd=9000.0, score_bps=8000)
    audit.sync_coverage("prod-b", "auditor-small", cover_usd=1000.0, score_bps=7500)

    r = audit.accrue_audit_rewards("prod-b", 10.0)
    assert r["ok"] is True
    assert r["to_auditors_usd"] == 0.10  # 1% of $10

    st = audit.listing_audit_state("prod-b")
    by_auditor = {c["auditor"]: c for c in st["coverages"]}
    assert by_auditor["auditor-big"]["pending_rewards_usd"] == 0.045
    assert by_auditor["auditor-small"]["pending_rewards_usd"] == 0.005
    assert by_auditor["ai-auditor:acex-v1"]["pending_rewards_usd"] == 0.05


def test_claim_audit_reward(ledgers):
    ipo, audit = ledgers
    ipo.float_product("prod-c")
    audit.accrue_audit_rewards("prod-c", 5.0)
    claim = audit.claim_audit_reward("prod-c", "ai-auditor:acex-v1")
    assert claim["ok"] is True
    assert claim["claimed_usd"] == 0.05
    assert audit.claim_audit_reward("prod-c", "ai-auditor:acex-v1")["error"] == "nothing_to_claim"


def test_accrue_unknown_listing_without_ipo(ledgers):
    _, audit = ledgers
    assert audit.accrue_audit_rewards("nope", 1.0)["error"] == "no_insuring_coverage"


def test_sync_coverage_guards(ledgers):
    ipo, audit = ledgers
    ipo.float_product("prod-d")
    assert audit.sync_coverage("prod-d", "x", cover_usd=0.5, score_bps=8000)["error"] == "cover_too_low"
    assert audit.sync_coverage("prod-d", "x", cover_usd=2000, score_bps=5000)["error"] == "invalid_score_bps"


def test_default_risk_from_drawdown(ledgers):
    ipo, audit = ledgers
    ipo.float_product("prod-e")
    audit.observe_prices("prod-e", baseline_price_usd=1.0, twap_price_usd=0.40)
    st = audit.listing_audit_state("prod-e")
    assert st["default_risk"] == "elevated"
    assert st["default"]["drawdown_bps"] == 6000
