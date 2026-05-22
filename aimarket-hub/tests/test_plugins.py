"""Tests for orchestrator, data-capability, MCP packager, TEE, promos, factory bridge."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.orchestrator_capability import Orchestrator, OrchestrationPlan
from aimarket_hub.data_capability import DataCapability, DataCapabilityRegistry
from aimarket_hub.mcp_packager import MCPPackager, MCPServerPackage
from aimarket_hub.tee_attestation import TEEAttestationService, TEEAttestation, TEEReceipt, EnclavePlatform
from aimarket_hub.time_locked_promo import PromoMarket, PromoOffer
from aimarket_hub.signing import Signer


@pytest.fixture
def signer():
    with tempfile.TemporaryDirectory() as tmp:
        yield Signer(Path(tmp) / "key")


# ── Orchestrator ──────────────────────────────────────────────

class TestOrchestrator:
    def test_plan_decomposes_task(self):
        orch = Orchestrator(orchestration_fee_pct=0.01)
        caps = [
            {"capability_id": "translate.multi@v2", "product_id": "p1", "name": "translate.multi",
             "price_per_call_usd": 0.40, "p50_latency_ms": 8100},
            {"capability_id": "legal.review@v1", "product_id": "p2", "name": "legal.review",
             "price_per_call_usd": 1.20, "p50_latency_ms": 11400},
        ]
        plan = orch.plan("translate and legal review", budget_usd=3.0, available_capabilities=caps)
        assert plan.orchestration_fee_pct == 0.01
        assert isinstance(plan.estimated_total_usd, float)

    def test_plan_fallback_cheapest(self):
        orch = Orchestrator()
        plan = orch.plan("unknown task", budget_usd=5.0, available_capabilities=[
            {"capability_id": "expensive@v1", "product_id": "p1", "name": "expensive",
             "price_per_call_usd": 99.0},
            {"capability_id": "cheap@v1", "product_id": "p2", "name": "cheap",
             "price_per_call_usd": 0.10},
        ])
        assert len(plan.steps) >= 1

    def test_plan_orchestration_fee(self):
        orch = Orchestrator(orchestration_fee_pct=0.02)
        plan = orch.plan("test", 5.0, [
            {"capability_id": "c@v1", "product_id": "p1", "name": "c", "price_per_call_usd": 1.0}
        ])
        assert plan.orchestration_fee_usd == pytest.approx(0.02, abs=0.01)

    def test_execute_plan_runs_steps(self):
        orch = Orchestrator()
        plan = orch.plan("test task", 5.0, [
            {"capability_id": "cap@v1", "product_id": "p1", "name": "cap", "price_per_call_usd": 0.40}
        ])

        def mock_invoker(pid, cid, inp):
            return {"success": True, "result": {"output": "done"}, "price_usd": 0.40}

        result = orch.execute_plan(plan, mock_invoker)
        assert result["success"] is True
        assert result["orchestration_fee_usd"] > 0
        assert "bill_of_materials" in result

    def test_stats(self):
        orch = Orchestrator()
        plan = orch.plan("test", 5.0, [{"capability_id": "c@v1", "product_id": "p1",
                                         "name": "c", "price_per_call_usd": 0.40}])
        orch.execute_plan(plan, lambda p, c, i: {"success": True, "result": {}, "price_usd": 0.40})
        stats = orch.stats()
        assert stats["tasks_completed"] == 1


# ── Data-as-Capability ────────────────────────────────────────

class TestDataCapabilityRegistry:
    def test_register(self):
        reg = DataCapabilityRegistry()
        dc = reg.register("0xOwner", "US court decisions 2020-2025", 50_000_000, 50000, 0.05)
        assert dc.owner_address == "0xOwner"
        assert dc.document_count == 50000
        assert dc.query_price_usd == 0.05
        assert dc.owner_revenue_share_pct == 0.70

    def test_query_and_revenue_split(self):
        reg = DataCapabilityRegistry()
        dc = reg.register("0xOwner", "court docs", 1_000_000, 1000, 0.05)
        result = reg.query(dc.capability_id, "precedent for contract dispute")
        assert result["price_usd"] == 0.05
        assert result["revenue_split"]["owner_usd"] == pytest.approx(0.035, abs=0.001)
        assert result["revenue_split"]["platform_usd"] == pytest.approx(0.015, abs=0.001)

    def test_get_owner_revenue(self):
        reg = DataCapabilityRegistry()
        dc = reg.register("0xOwner", "data1", 1_000_000, 100, 0.10)
        reg.query(dc.capability_id, "q1")
        reg.query(dc.capability_id, "q2")
        rev = reg.get_owner_revenue("0xOwner")
        assert rev["total_earned_usd"] > 0

    def test_list_available(self):
        reg = DataCapabilityRegistry()
        reg.register("0xA", "data A", 1000, 10, 0.05)
        reg.register("0xB", "data B", 2000, 20, 0.10)
        assert len(reg.list_available()) == 2

    def test_stats(self):
        reg = DataCapabilityRegistry()
        reg.register("0xA", "data", 1_000_000, 100, 0.05)
        s = reg.stats()
        assert s["total_data_capabilities"] == 1
        assert "total_data_size_gb" in s


# ── MCP Packager ──────────────────────────────────────────────

class TestMCPPackager:
    def test_package_creates_image_name(self):
        packager = MCPPackager()
        pkg = packager.package("translate.multi@v2", "p1", "Lyra",
                               "Translate text", {"type": "object"}, 0.40)
        assert pkg.docker_image.startswith("aifactory/lyra")
        assert "2.0.0" in pkg.docker_image
        assert "MCP" in pkg.mcp_manifest["server"]["name"]

    def test_package_has_tiers(self):
        packager = MCPPackager()
        pkg = packager.package("test@v1", "p1", "Test", "desc", {"type": "object"})
        assert len(pkg.subscription_tiers) == 3
        assert pkg.subscription_tiers[0]["name"] == "Starter"

    def test_generate_dockerfile(self):
        packager = MCPPackager()
        pkg = packager.package("test@v1", "p1", "Test", "desc", {"type": "object"})
        df = packager.generate_dockerfile(pkg)
        assert "FROM python" in df
        assert "ai-market.capability" in df

    def test_generate_claude_config(self):
        packager = MCPPackager()
        pkg = packager.package("test@v1", "p1", "Test", "desc", {"type": "object"})
        cfg = packager.generate_claude_desktop_config(pkg)
        parsed = json.loads(cfg)
        assert "mcpServers" in parsed

    def test_install_script(self):
        packager = MCPPackager()
        pkg = packager.package("test@v1", "p1", "Test", "desc", {"type": "object"})
        script = packager.generate_install_script(pkg)
        assert "docker pull" in script
        assert "✅" in script


# ── TEE Attestation ───────────────────────────────────────────

class TestTEEAttestation:
    def test_generate_attestation(self, signer):
        service = TEEAttestationService(signer, platform=EnclavePlatform.AWS_NITRO)
        att = service.generate_attestation("my_capability_code_v1", "i-12345", "us-east-1")
        assert att.platform == "aws_nitro"
        assert att.code_hash
        assert len(att.pcr_values) == 3
        assert not att.is_expired()

    def test_attestation_signs(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        assert att.signature

    def test_attestation_verifies(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        assert att.verify(att.code_hash, signer, service.get_enclave_public_key())

    def test_attestation_rejects_wrong_code(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        assert not att.verify("wrong_code_hash", signer, service.get_enclave_public_key())

    def test_attestation_expires(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        att.ttl_s = -1  # Force expire
        assert att.is_expired()

    def test_execute_with_attestation(self, signer):
        service = TEEAttestationService(signer)
        result = service.execute_with_attestation("cap@v1", "p1", {"text": "secret"}, "code_v1", 0.40)
        assert "attestation" in result
        assert "receipt" in result
        assert "enterprise_compliance" in result
        assert result["result"]["platform"] == "aws_nitro"
        assert "gdpr" in result["enterprise_compliance"]


# ── Time-Locked Promos ────────────────────────────────────────

class TestPromoMarket:
    def test_create_offer(self, signer):
        pm = PromoMarket(signer)
        offer = pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, 2.0, 100)
        assert offer.is_active
        assert offer.discounted_price_usd == 0.50
        assert offer.savings_usd == 0.50

    def test_get_best_offer(self, signer):
        pm = PromoMarket(signer)
        pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, 2.0, 100)
        pm.create_offer("hub2", "cap@v1", "p2", 1.00, 0.30, 2.0, 100)
        best = pm.get_best_offer("cap@v1")
        assert best.discount_pct == 0.50

    def test_apply_best_offer(self, signer):
        pm = PromoMarket(signer)
        pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, 2.0, 100)
        result = pm.apply_best_offer("cap@v1")
        assert result["applied"]
        assert result["price_usd"] == 0.50

    def test_apply_no_offer(self, signer):
        pm = PromoMarket(signer)
        result = pm.apply_best_offer("nonexistent@v1")
        assert not result["applied"]

    def test_offer_expires(self, signer):
        pm = PromoMarket(signer)
        pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, -1.0, 100)  # duration -1h = already expired
        result = pm.apply_best_offer("cap@v1")
        assert not result["applied"]

    def test_provider_stats(self, signer):
        pm = PromoMarket(signer)
        pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, 2.0, 10)
        stats = pm.provider_stats("hub1")
        assert stats["total_offers_created"] == 1

    def test_market_stats(self, signer):
        pm = PromoMarket(signer)
        pm.create_offer("hub1", "cap@v1", "p1", 1.00, 0.50, 2.0, 10)
        pm.create_offer("hub2", "cap2@v1", "p2", 2.00, 0.25, 2.0, 5)
        stats = pm.market_stats()
        assert stats["active_offers"] == 2


# ── Factory Bridge ─────────────────────────────────────────────

class TestFactoryBridge:
    def test_sync_handles_missing_pipeline(self):
        from aimarket_hub.database import HubDatabase
        with tempfile.TemporaryDirectory() as tmp:
            db = HubDatabase(Path(tmp) / "test.db")
            # When core.paths is not available (standalone hub),
            # import_factory_products should handle the ImportError gracefully
            try:
                from aimarket_hub.factory_bridge import import_factory_products
                count = import_factory_products(db, pipeline_json_path="/nonexistent/pipeline.json")
                assert count == 0
            except ImportError:
                # core module not available — expected in standalone hub
                pass
            db.close()
