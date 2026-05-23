"""Tests for Discovery glue, auto-listing, and factory wallet."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.factory_wallet import FactoryBalance, FactoryWallet


class TestDiscoveryGlue:
    def test_enrich_discovery_with_hub(self):
        from aimarket_hub.discovery_glue import enrich_discovery_with_hub

        # Should handle unreachable hub gracefully
        result = enrich_discovery_with_hub(
            "B2B invoice automation landing",
            hub_url="http://127.0.0.1:9999",  # unreachable
        )
        assert result["idea"] == "B2B invoice automation landing"
        assert result["recommendation"] == "proceed_without_enrichment"
        assert "enrichment_error" in result

    def test_enrich_discovery_returns_structure(self):
        from aimarket_hub.discovery_glue import enrich_discovery_with_hub

        result = enrich_discovery_with_hub("test idea", hub_url="http://127.0.0.1:9999")
        for key in ["market_signals", "reusable_capabilities", "data_available", "recommendation"]:
            assert key in result

    def test_purchase_data_unreachable(self):
        from aimarket_hub.discovery_glue import purchase_data_for_discovery

        result = purchase_data_for_discovery(
            "data.test@v1", "market trends for SaaS",
            hub_url="http://127.0.0.1:9999",
        )
        assert not result["success"]


class TestAutoListing:
    def test_auto_list_missing_pipeline(self):
        from aimarket_hub.auto_listing import auto_list_product

        with tempfile.TemporaryDirectory() as tmp:
            db = HubDatabase(Path(tmp) / "test.db")
            result = auto_list_product("prod-xxx", db, pipeline_path="/nonexistent/pipeline.json")
            assert "errors" in result
            assert result["errors"]
            db.close()

    def test_auto_list_nonexistent_product(self):
        from aimarket_hub.auto_listing import auto_list_product

        with tempfile.TemporaryDirectory() as tmp:
            db = HubDatabase(Path(tmp) / "test.db")
            pipe = Path(tmp) / "pipeline.json"
            pipe.write_text(json.dumps({"products": {}}))

            result = auto_list_product("prod-xxx", db, pipeline_path=str(pipe))
            assert "errors" in result
            db.close()

    def test_auto_list_product_not_completed(self):
        from aimarket_hub.auto_listing import auto_list_product

        with tempfile.TemporaryDirectory() as tmp:
            db = HubDatabase(Path(tmp) / "test.db")
            pipe = Path(tmp) / "pipeline.json"
            pipe.write_text(json.dumps({
                "products": {"prod-test": {"state": "IDEA_RECEIVED", "name": "Test", "idea": "test idea"}}
            }))

            result = auto_list_product("prod-test", db, pipeline_path=str(pipe))
            assert "errors" in result
            assert "not COMPLETED" in result["errors"][0]
            db.close()

    def test_auto_list_completed_product(self):
        from aimarket_hub.auto_listing import auto_list_product

        with tempfile.TemporaryDirectory() as tmp:
            db = HubDatabase(Path(tmp) / "test.db")
            pipe = Path(tmp) / "pipeline.json"
            pipe.write_text(json.dumps({
                "products": {"prod-done": {
                    "state": "COMPLETED",
                    "name": "InvoiceFlow SaaS",
                    "idea": "B2B invoice automation SaaS platform with Stripe integration",
                }}
            }))

            result = auto_list_product("prod-done", db, pipeline_path=str(pipe))
            assert result["listed_capabilities"], f"Expected capabilities, got errors: {result['errors']}"
            assert len(result["listed_capabilities"]) >= 1

            # Verify capability was actually registered in DB
            caps = db.list_capabilities("local")
            assert len(caps) >= 1
            db.close()


class TestFactoryWallet:
    def test_wallet_initial_state(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x029B5e4c5E326b9a9C2e8A1F09c885908EA8eb35")
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            bal = wallet.get_balance()
            # First run seeds $20.00 USDT on Base
            assert bal.balance_usd == 20.0
            assert bal.total_earned_usd == 0.0
            assert bal.wallet_address == "0x029B5e4c5E326b9a9C2e8A1F09c885908EA8eb35"
            assert bal.chain == "base"

    def test_wallet_top_up_requires_tx_hash(self):
        """top_up rejects empty tx_hash (EXP-63: prevent fabricated funding)."""
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            wallet._balance.wallet_address = "0xtest"
            result = wallet.top_up(100.0, tx_hash="", hub_url="http://127.0.0.1:9999")
            assert not result["success"]
            assert "tx_hash" in result["error"]

    def test_wallet_top_up_unreachable(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0xtest")
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            result = wallet.top_up(
                100.0,
                tx_hash="0x" + "ab" * 32,
                hub_url="http://127.0.0.1:9999",
            )
            assert not result["success"]

    def test_wallet_purchase_requires_channel(self):
        """purchase_data requires an active channel (EXP-64: real invoke, not accounting fiction)."""
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            result = wallet.purchase_data("p1", "data.test@v1", {"q": "x"}, 50.0)
            assert not result["success"]
            assert "channel" in result["error"].lower()

    def test_wallet_purchase_insufficient_balance(self):
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            wallet._balance.channel_id = "ch_test"
            wallet._balance.balance_usd = 10.0  # less than 50
            result = wallet.purchase_data("p1", "data.test@v1", {"q": "x"}, 50.0)
            assert not result["success"]
            assert "Insufficient" in result["error"]

    def test_wallet_record_sale(self):
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            wallet.record_sale("translate.multi@v2", 0.40)
            assert wallet.get_balance().total_earned_usd == 0.40
            assert wallet.get_balance().capabilities_sold == 1
            assert wallet.get_balance().net_position_usd == 0.40
            assert wallet.get_balance().is_profitable

    def test_wallet_record_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            wallet.record_listing("test.cap@v1")
            wallet.record_listing("test.cap2@v1")
            assert wallet.get_balance().capabilities_listed == 2

    def test_wallet_report(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x029B5e4c5E326b9a9C2e8A1F09c885908EA8eb35")
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            wallet._balance.balance_usd = 100.0
            wallet.record_sale("cap1@v1", 10.0)
            wallet.record_sale("cap2@v1", 5.0)
            # Simulate a spend without going through the (now-real) purchase_data HTTP call
            wallet._balance.balance_usd -= 3.0
            wallet._balance.total_spent_usd += 3.0
            wallet._balance.data_purchases += 1
            report = wallet.report()
            assert report["total_earned_usd"] == 15.0
            assert report["total_spent_usd"] == 3.0
            assert report["net_position_usd"] == 12.0
            assert report["is_profitable"]
            assert len(report["recent_transactions"]) >= 1
            assert report["wallet"]["address"] == "0x029B5e4c5E326b9a9C2e8A1F09c885908EA8eb35"
            assert report["wallet"]["chain"] == "base"
            assert report["wallet"]["token"] == "USDT"
            assert "basescan.org" in report["wallet"]["explorer"]

    def test_wallet_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wallet.json"
            wallet1 = FactoryWallet(path)
            wallet1._balance.balance_usd = 100.0
            wallet1.record_sale("cap@v1", 25.0)
            # After sale: balance = 100 + 25 = 125, earned = 25

            wallet2 = FactoryWallet(path)
            assert wallet2.get_balance().balance_usd == 125.0
            assert wallet2.get_balance().total_earned_usd == 25.0
            assert wallet2.get_balance().capabilities_sold == 1

    def test_wallet_settle_no_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            wallet = FactoryWallet(Path(tmp) / "wallet.json")
            result = wallet.settle_channel()
            assert not result["success"]

    def test_net_position(self):
        bal = FactoryBalance(
            total_earned_usd=100.0,
            total_spent_usd=30.0,
        )
        assert bal.net_position_usd == 70.0
        assert bal.is_profitable

        bal2 = FactoryBalance(
            total_earned_usd=10.0,
            total_spent_usd=50.0,
        )
        assert bal2.net_position_usd == -40.0
        assert not bal2.is_profitable
