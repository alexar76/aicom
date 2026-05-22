"""streaming plugin for AIMarket Hub."""

from aimarket_hub.plugin import HubPlugin
from aimarket_streaming.streaming import *


class StreamingPlugin(HubPlugin):
    name = "aimarket-streaming"
    version = "2.0.0"
    description = "streaming"
    homepage = "https://github.com/ai-factory/aimarket-streaming"
    category = "monetization"

    def register_routes(self, router):
        from fastapi import APIRouter as _AR
        # Plugin-specific routes will be registered here
        pass
    def on_startup(self, db):
        self._biller = None  # Lazy init on first stream
