"""tee plugin for AIMarket Hub."""

from aimarket_hub.plugin import HubPlugin
from aimarket_tee.tee_attestation import *


class TEEPlugin(HubPlugin):
    name = "aimarket-tee"
    version = "2.0.0"
    description = "tee attestation"
    homepage = "https://github.com/ai-factory/aimarket-tee"
    category = "security"

    def register_routes(self, router):
        from fastapi import APIRouter as _AR
        # Plugin-specific routes will be registered here
        pass
