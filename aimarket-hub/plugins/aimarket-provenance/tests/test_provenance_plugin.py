"""Tests for ProvenancePlugin — lifecycle, hooks, manifest."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_provenance.plugin import ProvenancePlugin


@pytest.fixture
def plugin() -> ProvenancePlugin:
    return ProvenancePlugin()


@pytest.fixture
def db() -> HubDatabase:
    with tempfile.TemporaryDirectory() as tmp:
        d = HubDatabase(db_path=str(Path(tmp) / "test_hub.db"))
        yield d


class TestPluginMetadata:
    def test_name(self, plugin):
        assert plugin.name == "provenance"

    def test_version(self, plugin):
        assert plugin.version == "1.1.0"

    def test_category(self, plugin):
        assert plugin.category == "compliance"


class TestPluginLifecycle:
    def test_on_startup(self, plugin, db):
        plugin.on_startup(db)
        assert plugin._storage is not None

    def test_register_routes(self, plugin, db):
        plugin.on_startup(db)
        # register_routes requires an APIRouter, which we can't easily test
        # without a FastAPI app. We just verify the method exists.
        assert hasattr(plugin, "register_routes")


class TestPluginHooks:
    def test_on_invoke_post_check_exists(self, plugin):
        assert hasattr(plugin, "on_invoke_post_check")

    def test_get_manifest_extension(self, plugin):
        ext = plugin.get_manifest_extension()
        assert "provenance" in ext
        assert ext["provenance"]["version"] == "1.1.0"
        assert ext["provenance"]["receipt_format"] == "W3C Verifiable Credential"
        assert ext["provenance"]["signing_algorithm"] == "Ed25519"
        assert "endpoints" in ext["provenance"]
        assert "features" in ext["provenance"]
        assert ext["provenance"]["features"]["auto_receipt"] is True
        assert ext["provenance"]["features"]["tee_attestation"] is True

    def test_auto_receipt_generation(self, plugin, db):
        """Simulate an invoke post-check — it should generate and store a receipt."""
        plugin.on_startup(db)
        output = {"text": "Generated AI response"}
        context = {
            "product_id": "prod-test",
            "capability_id": "text-gen",
            "input": {"prompt": "Hello"},
            "provider_hub": "local",
            "latency_ms": 1500,
            "price_usd": 0.05,
        }
        # The post_check hook should not block (returns None)
        block = plugin.on_invoke_post_check(output, context)
        assert block is None

        # The output dict should have provenance receipt metadata
        pr = output.get("_provenance_receipt")
        assert pr is not None
        assert "receipt_id" in pr
        assert "verify_url" in pr
        assert pr["receipt_id"].startswith("urn:uuid:")
        assert "/r/" in pr["verify_url"]
