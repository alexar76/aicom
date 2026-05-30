"""ACEX Phase 2 integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from acex.integrations.jupiter import (
    JupiterRouteError,
    build_swap_plan,
    synthetic_quote_for_tests,
)
from acex.integrations.pricing import build_pricing_snapshot


def test_build_pricing_snapshot_groups_by_product():
    caps = [
        {
            "product_id": "prod-alpha",
            "capability_id": "chat",
            "price_per_call_usd": 0.05,
            "success_rate_30d": 0.98,
            "trust_score": 0.9,
        },
        {
            "product_id": "prod-alpha",
            "capability_id": "summarize",
            "price_per_call_usd": 0.03,
            "success_rate_30d": 0.96,
            "trust_score": 0.88,
        },
        {
            "product_id": "prod-beta",
            "capability_id": "code",
            "price_per_call_usd": 0.12,
            "success_rate_30d": 0.94,
            "trust_score": 0.85,
        },
    ]
    body = build_pricing_snapshot(caps, chain="solana", limit=10)
    assert body["protocol"] == "acex"
    assert body["chain"] == "solana"
    assert len(body["listings"]) == 2
    assert body["liquidity"]["primary"]["provider"] == "jupiter"
    assert body["capsense"]["enabled"] is True
    assert body["pulse_terminal"]["pricing_endpoint"] == "/api/v2/capital/pricing"


def test_pricing_listing_filter():
    caps = [
        {"product_id": "prod-a", "capability_id": "x", "price_per_call_usd": 0.1},
        {"product_id": "prod-b", "capability_id": "y", "price_per_call_usd": 0.2},
    ]
    body = build_pricing_snapshot(caps, listing_id="prod-a")
    assert len(body["listings"]) == 1
    assert body["listings"][0]["listing_id"] == "prod-a"


def test_jupiter_synthetic_quote_and_swap_plan():
    quote = synthetic_quote_for_tests(
        input_mint="ShareMint111",
        output_mint="USDcMint222",
        amount=1_000_000,
    )
    plan = build_swap_plan(quote, user_public_key="BuyerPubkey")
    assert plan["provider"] == "jupiter"
    assert plan["out_amount"] == str(int(1_000_000 * 0.99))


def test_acex_phase2_files_present():
    root = Path(__file__).resolve().parents[1]
    assert (root / "acex" / "integrations" / "pricing.py").is_file()
    assert (root / "acex" / "integrations" / "jupiter.py").is_file()
    assert (root / "acex" / "docs" / "jupiter-routing.md").is_file()
    assert (root / "apps" / "pulse-terminal" / "README.md").is_file()
    lib = (root / "acex" / "contracts" / "solana" / "programs" / "acex-capital" / "src" / "lib.rs").read_text()
    assert "create_capsense_series" in lib
    assert "buy_capsense_option" in lib
    assert "stake_audit" in lib
    assert "fund_audit_rewards" in lib


def test_factory_capital_pricing_route_source():
    src = (Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "acex_capital.py").read_text()
    assert "/pricing" in src
    assert "/pricing/ws" in src
    assert "/pricing/stream" in src
    assert "build_pricing_snapshot" in src


def test_pulse_terminal_app_present():
    root = Path(__file__).resolve().parents[1] / "apps" / "pulse-terminal"
    assert (root / "package.json").is_file()
    assert (root / "src" / "App.tsx").is_file()
    assert (root / "src" / "hooks" / "usePricingStream.ts").is_file()


def test_pricing_audit_overlay():
    caps = [
        {"product_id": "prod-a", "capability_id": "x", "price_per_call_usd": 0.1},
    ]
    audit_overlay = {
        "prod-a": {
            "enabled": True,
            "aggregate_score_bps": 8000,
            "total_cover_usd": 10_000.0,
            "auditor_count": 1,
            "audit_fee_bps": 100,
            "accrued_audit_rewards_usd": 0.5,
            "suggested_note_spread_bps": 400,
            "default_risk": "none",
            "default": {"defaulted": False, "baseline_price_usd": None, "twap_price_usd": None, "drawdown_bps": None},
            "coverages": [],
        }
    }
    body = build_pricing_snapshot(caps, audit_overlay=audit_overlay)
    row = body["listings"][0]
    assert row["proof_of_audit"]["enabled"] is True
    assert body["proof_of_audit"]["listings_with_coverage"] == 1


def test_hub_capital_pricing_route_source():
    src = (Path(__file__).resolve().parents[1] / "aimarket-hub" / "aimarket_hub" / "api.py").read_text()
    assert "/capital/pricing" in src
    assert "/api/v2/capital" in src
