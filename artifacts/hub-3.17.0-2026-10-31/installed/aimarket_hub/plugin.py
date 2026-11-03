"""Plugin system for AIMarket Hub.

Plugins are independent pip packages that register via setuptools entry points.
Hub auto-discovers installed plugins at startup through importlib.metadata.

Architecture:
    pip install aimarket-safety    # Someone's plugin
    aimarket serve                  # Hub starts, scans entry_points
    → safety plugin loaded          # Routes registered, hooks active

Plugin authors implement HubPlugin and add to pyproject.toml:
    [project.entry-points."aimarket.plugins"]
    myplugin = "my_package.plugin:MyPlugin"

This is the extension point that keeps the core lean (~1500 LOC)
while the ecosystem grows unbounded.
"""

from __future__ import annotations

import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Plugin Interface ───────────────────────────────────────────


class HubPlugin(ABC):
    """Every AIMarket plugin implements this interface.

    Plugins can:
    - Register API routes
    - Hook into invoke pre/post checks (safety, compliance, audit)
    - Issue immutable artifacts after a successful invoke is finalized
    - Extend .well-known manifest
    - Run startup logic with DB access
    """

    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    homepage: str = ""
    category: str = "uncategorized"  # security, reputation, monetization, tooling, compliance

    # ── Route registration ─────────────────────────────────

    def register_routes(self, router: Any) -> None:
        """Add plugin-specific API routes to the hub's APIRouter.

        Routes are mounted under /ai-market/v2/p/{plugin_name}/...
        """

    # ── Invoke hooks (return None = pass, dict = block) ──────

    def on_invoke_pre_check(self, input_payload: dict, context: dict) -> dict | None:
        """Check input before invocation. Return blocking dict or None.

        Blocking dict format:
            {"blocked": True, "category": "class:injection",
             "reason": "...", "refund": True}
        """
        return None

    def on_invoke_post_check(self, output: dict, context: dict) -> dict | None:
        """Check output before returning to consumer."""
        return None

    def on_invoke_receipt(self, output: dict, context: dict) -> dict | None:
        """Issue a receipt after checks and settlement have reached a stable state.

        Unlike ``on_invoke_post_check`` this hook is not a gate and cannot block the
        response.  It runs only after an invoke has produced an accepted output.  A
        plugin returns the compact public envelope that the hub should attach under
        its plugin name; the immutable document itself may live on plugin routes.

        ``context`` includes the exact input, provider hub, observed latency, charged
        price, invocation nonce and settlement status.  Keeping receipt issuance out
        of the safety hook prevents an output that is subsequently rejected from
        leaving behind a successful work receipt.
        """
        return None

    # ── Lifecycle ───────────────────────────────────────────

    def on_startup(self, db: Any) -> None:
        """Called when hub starts. DB is HubDatabase instance."""

    def on_shutdown(self) -> None:
        """Called when the hub stops: stop threads and timers the plugin started."""

    # ── Manifest extension ──────────────────────────────────

    def get_manifest_extension(self) -> dict:
        """Return extra fields to merge into .well-known/ai-market.json."""
        return {}

    # ── Metadata ────────────────────────────────────────────

    def plugin_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "homepage": self.homepage,
            "category": self.category,
            "hooks": self._list_hooks(),
        }

    def _list_hooks(self) -> list[str]:
        hooks = []
        cls = type(self)
        if cls.register_routes is not HubPlugin.register_routes:
            hooks.append("register_routes")
        if cls.on_invoke_pre_check is not HubPlugin.on_invoke_pre_check:
            hooks.append("on_invoke_pre_check")
        if cls.on_invoke_post_check is not HubPlugin.on_invoke_post_check:
            hooks.append("on_invoke_post_check")
        if cls.on_invoke_receipt is not HubPlugin.on_invoke_receipt:
            hooks.append("on_invoke_receipt")
        if cls.on_startup is not HubPlugin.on_startup:
            hooks.append("on_startup")
        if cls.get_manifest_extension is not HubPlugin.get_manifest_extension:
            hooks.append("get_manifest_extension")
        return hooks


# ── Plugin Registry ────────────────────────────────────────────


@dataclass
class PluginRegistry:
    """Holds all loaded plugins and provides discovery."""

    plugins: list[HubPlugin] = field(default_factory=list)

    def discover(self, db: Any = None) -> int:
        """Discover installed plugins via setuptools entry points.

        If AIMARKET_PLUGIN_WHITELIST is set (comma-separated plugin names),
        only plugins on the whitelist are loaded. This prevents supply-chain
        attacks via PyPI squatting on the aimarket.plugins entry point group.
        """
        import os

        try:
            from importlib.metadata import entry_points
        except ImportError:
            logger.warning("importlib.metadata not available — plugins disabled")
            return 0

        # Plugin whitelist — prevents arbitrary plugins from loading
        whitelist_raw = os.environ.get("AIMARKET_PLUGIN_WHITELIST", "")
        whitelist = (
            {n.strip() for n in whitelist_raw.split(",") if n.strip()}
            if whitelist_raw else None
        )

        # entry_points(group=...) is Python 3.10+; fall back to the 3.9 dict API.
        try:
            eps = entry_points(group="aimarket.plugins")
        except TypeError:
            eps = entry_points().get("aimarket.plugins", [])

        count = 0
        for ep in eps:
            if whitelist and ep.name not in whitelist:
                logger.warning(
                    "Plugin %s is not in AIMARKET_PLUGIN_WHITELIST — skipped", ep.name
                )
                continue
            try:
                plugin_cls = ep.load()
                plugin = plugin_cls()
                self.plugins.append(plugin)
                if db:
                    plugin.on_startup(db)
                logger.info(
                    "Plugin loaded: %s v%s (%s)",
                    plugin.name, plugin.version, plugin.category,
                )
                count += 1
            except Exception as exc:
                logger.error("Failed to load plugin %s: %s", ep.name, exc)

        # When a whitelist is active it silently disables everything not on it.
        # Log the loaded set at INFO so an operator can see exactly what the
        # whitelist permitted (the per-skip warnings above only show denials).
        if whitelist is not None:
            loaded = [p.name for p in self.plugins]
            logger.info(
                "AIMARKET_PLUGIN_WHITELIST active — %d plugin(s) loaded: %s",
                len(loaded),
                ", ".join(loaded) if loaded else "(none)",
            )

        return count

    def register_all_routes(self, router: Any) -> None:
        """Register routes from all plugins that implement register_routes."""
        for plugin in self.plugins:
            try:
                plugin.register_routes(router)
            except Exception as exc:
                logger.error("Plugin %s route registration failed: %s", plugin.name, exc)

    def run_pre_checks(self, input_payload: dict, context: dict) -> dict | None:
        """Run all pre-invoke hooks. First to block wins."""
        for plugin in self.plugins:
            try:
                result = plugin.on_invoke_pre_check(input_payload, context)
                if result and result.get("blocked"):
                    result["plugin"] = plugin.name
                    return result
            except Exception as exc:
                logger.error("Plugin %s pre_check error: %s", plugin.name, exc)
        return None

    def run_post_checks(self, output: dict, context: dict) -> dict | None:
        """Run all post-response hooks."""
        for plugin in self.plugins:
            try:
                result = plugin.on_invoke_post_check(output, context)
                if result and result.get("blocked"):
                    result["plugin"] = plugin.name
                    return result
            except Exception as exc:
                logger.error("Plugin %s post_check error: %s", plugin.name, exc)
        return None

    def run_receipt_hooks(self, output: dict, context: dict) -> dict[str, dict]:
        """Run final artifact issuers without letting one plugin break delivery.

        Receipt plugins are side effects by design: the core invoke remains usable if
        an optional issuer is unavailable.  A product that *requires* a portable proof
        (such as the public USE demo) can fail closed by requiring its named envelope.
        """
        issued: dict[str, dict] = {}
        for plugin in self.plugins:
            try:
                result = plugin.on_invoke_receipt(output, context)
                if isinstance(result, dict):
                    issued[plugin.name] = result
            except Exception as exc:
                logger.error("Plugin %s receipt hook error: %s", plugin.name, exc)
        return issued

    def get_manifest_extensions(self) -> dict:
        """Collect manifest extensions from all plugins."""
        ext = {}
        for plugin in self.plugins:
            try:
                plugin_ext = plugin.get_manifest_extension()
                if plugin_ext:
                    ext[plugin.name] = plugin_ext
            except Exception:
                pass
        return ext

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return plugin info for API."""
        return [p.plugin_info() for p in self.plugins]

    def get_plugin(self, name: str) -> HubPlugin | None:
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    def count(self) -> int:
        return len(self.plugins)

    def routed_count(self) -> int:
        """How many loaded plugins actually add an HTTP surface.

        `count()` is what `.well-known` published as `plugins_loaded`, and it counts entry
        points — including the ones whose `register_routes` body is `pass`. Eight of the
        fifteen shipped plugins are in that state, so the advertised number overstated what
        a caller can reach by more than half, and the docs for at least one of them
        (aimarket-data-cap) describe endpoints that were never written. A plugin with no
        routes may still be doing real work through hooks, which is why both numbers are
        published rather than the smaller one replacing the larger.
        """
        routed = 0
        for plugin in self.plugins:
            fn = getattr(type(plugin), "register_routes", None)
            if fn is None:
                continue
            code = getattr(fn, "__code__", None)
            # A body of `pass` (or a bare docstring) compiles to a constant load + return.
            if code is not None and code.co_code and len(code.co_code) <= 6:
                continue
            routed += 1
        return routed

    def startup_all(self, db: Any) -> None:
        for plugin in self.plugins:
            try:
                plugin.on_startup(db)
            except Exception as exc:
                logger.error("Plugin %s startup failed: %s", plugin.name, exc)

    def shutdown_all(self) -> None:
        for plugin in self.plugins:
            try:
                plugin.on_shutdown()
            except Exception as exc:  # noqa: BLE001 - one plugin must not keep the rest running
                logger.error("Plugin %s shutdown failed: %s", plugin.name, exc)
