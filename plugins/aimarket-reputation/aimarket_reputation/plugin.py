"""reputation plugin for AIMarket Hub."""

from aimarket_hub.plugin import HubPlugin
from aimarket_reputation.reputation_oracle import *


class ReputationPlugin(HubPlugin):
    name = "aimarket-reputation"
    version = "2.0.0"
    description = "reputation oracle"
    homepage = "https://github.com/ai-factory/aimarket-reputation"
    category = "reputation"

    def register_routes(self, router):
        from fastapi import APIRouter as _AR
        # Plugin-specific routes will be registered here
        pass
    def on_startup(self, db):
        self._oracle = None

    def get_manifest_extension(self) -> dict:
        return {"reputation": {"bond_required": True, "slashing_enabled": True}}
