"""data-cap plugin for AIMarket Hub."""

from aimarket_hub.plugin import HubPlugin
from aimarket_data_cap.data_capability import *


class DataCapPlugin(HubPlugin):
    name = "aimarket-data-cap"
    version = "2.0.0"
    description = "data capability"
    homepage = "https://github.com/ai-factory/aimarket-data-cap"
    category = "monetization"

    def register_routes(self, router):
        from fastapi import APIRouter as _AR
        # Plugin-specific routes will be registered here
        pass
