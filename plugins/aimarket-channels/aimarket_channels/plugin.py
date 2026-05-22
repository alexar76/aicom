"""channels plugin — payment channel infrastructure."""

from aimarket_hub.plugin import HubPlugin


class ChannelsPlugin(HubPlugin):
    name = "aimarket-channels"
    version = "2.0.0"
    description = "Pre-funded payment channels — off-chain ledger, on-chain settlement"
    homepage = "https://github.com/ai-factory/aimarket-channels"
    category = "infrastructure"

    def get_manifest_extension(self):
        return {
            "channels": {
                "enabled": True,
                "endpoints": {
                    "open": "/ai-market/v2/channel/open",
                    "close": "/ai-market/v2/channel/close",
                },
                "max_deposit_usd": 10_000,
                "expiry_hours": 24,
                "demo_mode": True,
            }
        }
