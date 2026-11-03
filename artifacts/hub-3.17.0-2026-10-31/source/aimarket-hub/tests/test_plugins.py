"""Tests for orchestrator, data-capability, MCP packager, TEE, promos, factory bridge."""

import json
import tempfile
from pathlib import Path

import pytest

from aimarket_hub.orchestrator_capability import Orchestrator, OrchestrationPlan
from aimarket_hub import data_capability
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

class TestDataCapabilityManifest:
    """The module builds a listing for a corpus the PUBLISHER serves; it does not search.

    It used to claim otherwise: `query()` returned an f-string of the caller's own words with
    a hard-coded relevance score, `data_hash` was `owner_address + time.time()` presented as
    "SHA-256 of the corpus", and the 70/30 split was arithmetic on a dict that no money ever
    passed through. The split is now enforced by the hub itself
    (`AIMARKET_PUBLISHER_SHARE_BPS`, paid into the publisher's credit balance), so what is
    left here is manifest construction.
    """

    def test_manifest_is_registerable_shape(self):
        m = data_capability.data_capability_manifest(
            name="US court decisions",
            description="50k decisions, 2020-2025",
            invoke_url="https://notary.example.com/search",
            query_price_usd=0.05,
            publisher_id="acct_1234",
        )
        assert m["product_id"] == "data-us-court-decisions"
        assert m["capability_id"] == "us-court-decisions.search@v1"
        assert m["price_per_call_usd"] == pytest.approx(0.05)
        assert m["invoke_url"].startswith("https://")
        assert m["publisher_id"] == "acct_1234"
        assert "query" in m["input_schema"]["properties"]

    def test_document_count_is_labelled_as_the_publishers_claim(self):
        m = data_capability.data_capability_manifest(
            name="corpus", description="d", invoke_url="https://x.example/y",
            query_price_usd=0.01, document_count=50_000,
        )
        assert m["claimed_document_count"] == 50_000
        assert "document_count" not in m, "the hub counted nothing and must not say it did"

    def test_the_fingerprint_commits_to_the_documents(self):
        a = data_capability.corpus_fingerprint(["one", "two"])
        assert a == data_capability.corpus_fingerprint(["two", "one"]), "order must not matter"
        assert a != data_capability.corpus_fingerprint(["one", "three"])
        assert len(a) == 64

    def test_earnings_are_stated_as_arithmetic(self):
        split = data_capability.expected_owner_earnings(0.05, 100)
        assert split["gross_usd"] == pytest.approx(5.0)
        assert split["owner_usd"] == pytest.approx(3.5)
        assert split["operator_usd"] == pytest.approx(1.5)


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
    @pytest.fixture(autouse=True)
    def _allow_software_tee(self, monkeypatch):
        # Software-TEE path is guarded in prod mode; CI sets this globally
        # (ci.yml). Set it here too so the suite is hermetic when run locally.
        monkeypatch.setenv("AIMARKET_TEE_SOFTWARE_OK", "1")

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
        # Attestations no longer carry a bare `.signature`; they produce a stable
        # canonical payload bound to the code hash that verify() checks.
        assert att.code_hash
        assert att.canonical()

    def test_attestation_verifies(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        assert att.verify(att.code_hash, service.enclave_public_key_b64)

    def test_attestation_rejects_wrong_code(self, signer):
        service = TEEAttestationService(signer)
        att = service.generate_attestation("code_v1")
        assert not att.verify("wrong_code_hash", service.enclave_public_key_b64)

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
        # Compliance guarantees are asserted ONLY for a real hardware enclave. In
        # software mode (no enclave) the block must instead carry an explicit
        # SIMULATED warning rather than claiming GDPR/HIPAA/etc.
        compliance = result["enterprise_compliance"]
        if result["result"]["security"] == "hardware":
            assert "gdpr" in compliance
        else:
            assert compliance.get("mode", "").startswith("SOFTWARE")
            assert "do NOT apply" in compliance.get("warning", "")


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
