"""The plugin list, the plugin registry and each plugin's own routes under /p/<name>."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException

from aimarket_hub.config import HubConfig
from aimarket_hub.plugin import PluginRegistry


# The paths below were written relative to aimarket_hub/api.py, where this code lived.
_API_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api.py")


def register(
    *,
    config: HubConfig,
    plugins: PluginRegistry,
    router: APIRouter,
) -> None:
    """Attach the /plugins routes and every plugin's router to ``router``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        logger,
    )

    # ── Plugin Catalog (the marketplace) ───────────────────────

    @router.get("/plugins")
    async def list_plugins():
        """List all loaded plugins."""
        return {
            "plugins": plugins.list_plugins(),
            "count": plugins.count(),
            "discovery": "Plugins are auto-discovered via setuptools entry_points (group: aimarket.plugins)",
            "registry_url": f"{config.hub_url}/ai-market/v2/plugins/registry",
        }

    @router.get("/plugins/registry")
    def plugin_registry():
        """Serve the static curated plugin registry.

        Deliberately a SYNC handler: it does blocking stat()+read()+json.load() on a
        file up to 5MB. As `async def` that ran on the event loop and stalled every
        concurrent /invoke for the duration of the read; FastAPI runs a sync handler in
        its threadpool instead, which is exactly the semantics this needs.
        """
        import os as _os
        registry_path = _os.path.join(_os.path.dirname(_API_FILE), "..", "plugins.json")
        if _os.path.isfile(registry_path):
            if _os.path.getsize(registry_path) > 5_000_000:
                logger.warning("plugins.json exceeds 5MB — rejecting")
                return {"registry_version": "1.0", "plugins": [], "error": "registry file too large"}
            with open(registry_path) as f:
                return json.load(f)
        return {"registry_version": "1.0", "plugins": [], "note": "No plugins.json found. Add plugins via PR to the curated registry."}

    @router.get("/plugins/{plugin_name}")
    async def plugin_detail(plugin_name: str):
        """Get details about a specific loaded plugin."""
        plugin = plugins.get_plugin(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not loaded")
        return plugin.plugin_info()

    # ── Register routes ─────────────────────────────────────────

    # Register plugin routes under /ai-market/v2/p/{name}/...
    for p in plugins.plugins:
        if "register_routes" not in p._list_hooks():
            continue
        plugin_router = APIRouter(prefix=f"/p/{p.name}", tags=[f"plugin-{p.name}"])
        try:
            p.register_routes(plugin_router)
            router.include_router(plugin_router)
        except Exception as exc:
            logger.error("Plugin %s route registration failed: %s", p.name, exc)
