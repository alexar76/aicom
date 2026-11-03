"""Tests for the plugin system — HubPlugin ABC, PluginRegistry, hooks."""

import tempfile
from pathlib import Path

import pytest

from aimarket_hub.database import HubDatabase
from aimarket_hub.plugin import HubPlugin, PluginRegistry
from aimarket_hub.signing import Signer


class TestHubPlugin:
    def test_plugin_info(self):
        class MyPlugin(HubPlugin):
            name = "test-plugin"
            version = "1.0"
            description = "Test"
            category = "testing"

        p = MyPlugin()
        info = p.plugin_info()
        assert info["name"] == "test-plugin"
        assert info["version"] == "1.0"
        assert info["hooks"] == []  # No overrides → no hooks listed

    def test_plugin_with_hooks(self):
        class HookPlugin(HubPlugin):
            name = "hook-test"
            version = "1.0"
            description = "Has hooks"
            category = "security"

            def on_invoke_pre_check(self, input_payload, context):
                return None

        p = HookPlugin()
        info = p.plugin_info()
        assert "on_invoke_pre_check" in info["hooks"]

    def test_plugin_with_routes(self):
        class RoutePlugin(HubPlugin):
            name = "route-test"
            version = "1.0"
            description = "Has routes"
            category = "tooling"

            def register_routes(self, router):
                pass

        p = RoutePlugin()
        info = p.plugin_info()
        assert "register_routes" in info["hooks"]

    def test_manifest_extension(self):
        class ExtPlugin(HubPlugin):
            name = "ext-test"
            version = "1.0"
            description = "Ext"
            category = "monetization"

            def get_manifest_extension(self):
                return {"custom_field": "value"}

        p = ExtPlugin()
        info = p.plugin_info()
        assert "get_manifest_extension" in info["hooks"]


class TestPluginRegistry:
    @pytest.fixture
    def db(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = HubDatabase(Path(tmp) / "test.db")
            yield database
            database.close()

    def test_empty_registry(self):
        reg = PluginRegistry()
        assert reg.count() == 0
        assert reg.list_plugins() == []
        assert reg.get_plugin("nope") is None

    def test_add_plugin_manually(self):
        reg = PluginRegistry()

        class TestPlugin(HubPlugin):
            name = "manual-test"
            version = "1.0"
            description = "Manually added"
            category = "testing"

            def on_invoke_pre_check(self, input_payload, context):
                if "bad" in str(input_payload):
                    return {"blocked": True, "category": "test:bad", "reason": "contains bad word"}
                return None

        reg.plugins.append(TestPlugin())
        assert reg.count() == 1
        assert reg.get_plugin("manual-test") is not None

        # Test pre-check
        block = reg.run_pre_checks({"text": "this is bad content"}, {})
        assert block is not None
        assert block["blocked"]
        assert block["plugin"] == "manual-test"

        # Test clean input passes
        block = reg.run_pre_checks({"text": "clean content"}, {})
        assert block is None

    def test_run_post_checks(self):
        reg = PluginRegistry()

        class PostPlugin(HubPlugin):
            name = "post-test"
            version = "1.0"
            description = "Post check"
            category = "security"

            def on_invoke_post_check(self, output, context):
                if "PII" in str(output):
                    return {"blocked": True, "category": "class:PII", "reason": "PII leak"}
                return None

        reg.plugins.append(PostPlugin())
        block = reg.run_post_checks({"result": "email: user@example.com PII here"}, {})
        assert block is not None
        assert block["blocked"]

    def test_run_receipt_hooks_collects_final_artifacts(self):
        reg = PluginRegistry()
        calls = []

        class ReceiptPlugin(HubPlugin):
            name = "receipt-test"

            def on_invoke_receipt(self, output, context):
                calls.append((output, context))
                return {"receipt_id": "urn:uuid:test", "receipt_url": "https://hub/r/test"}

        reg.plugins.append(ReceiptPlugin())
        artifacts = reg.run_receipt_hooks(
            {"reading": 23},
            {"input": {"device_id": "wx-1"}, "settlement_status": "captured"},
        )
        assert artifacts == {
            "receipt-test": {
                "receipt_id": "urn:uuid:test",
                "receipt_url": "https://hub/r/test",
            }
        }
        assert calls[0][0] == {"reading": 23}
        assert calls[0][1]["input"] == {"device_id": "wx-1"}
        assert "on_invoke_receipt" in reg.list_plugins()[0]["hooks"]

    def test_manifest_extensions_collected(self):
        reg = PluginRegistry()

        class Ext1(HubPlugin):
            name = "ext1"
            version = "1.0"
            description = "Ext 1"
            category = "testing"

            def get_manifest_extension(self):
                return {"safety": True}

        class Ext2(HubPlugin):
            name = "ext2"
            version = "1.0"
            description = "Ext 2"
            category = "testing"

            def get_manifest_extension(self):
                return {"reputation": True}

        reg.plugins.append(Ext1())
        reg.plugins.append(Ext2())

        ext = reg.get_manifest_extensions()
        assert "ext1" in ext
        assert "ext2" in ext
        assert ext["ext1"] == {"safety": True}

    def test_startup_all(self, db):
        reg = PluginRegistry()
        startup_called = []

        class StartupPlugin(HubPlugin):
            name = "startup-test"
            version = "1.0"
            description = "Startup"
            category = "testing"

            def on_startup(self, database):
                startup_called.append(True)

        reg.plugins.append(StartupPlugin())
        reg.startup_all(db)
        assert len(startup_called) == 1

    def test_register_all_routes(self):
        reg = PluginRegistry()
        routes_registered = []

        class RoutePlugin(HubPlugin):
            name = "route-reg-test"
            version = "1.0"
            description = "Routes"
            category = "testing"

            def register_routes(self, router):
                routes_registered.append(router)

        reg.plugins.append(RoutePlugin())
        mock_router = object()
        reg.register_all_routes(mock_router)
        assert len(routes_registered) == 1
        assert routes_registered[0] is mock_router
