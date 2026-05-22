"""auction plugin for AIMarket Hub."""

from aimarket_hub.plugin import HubPlugin
from aimarket_auction.spot_auction import *


class AuctionPlugin(HubPlugin):
    name = "aimarket-auction"
    version = "2.0.0"
    description = "spot auction"
    homepage = "https://github.com/ai-factory/aimarket-auction"
    category = "monetization"

    def register_routes(self, router):
        from fastapi import APIRouter as _AR
        # Plugin-specific routes will be registered here
        pass
