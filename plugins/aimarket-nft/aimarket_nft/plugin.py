"""aimarket-nft plugin — Tokenized pre-paid credits — transferable, giftable, sellable."""

from aimarket_hub.plugin import HubPlugin
from aimarket_nft.capability_nft import NFTRegistry


class NFTPlugin(HubPlugin):
    name = "aimarket-nft"
    version = "2.0.0"
    description = "Tokenized pre-paid credits — transferable, giftable, sellable"
    homepage = "https://github.com/ai-factory/aimarket-nft"
    category = "monetization"

    def __init__(self):
        super().__init__()
        self._registry = NFTRegistry()

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field

        class MintRequest(BaseModel):
            capability_id: str = Field(..., min_length=2)
            product_id: str = Field(..., min_length=2)
            total_calls: int = Field(..., gt=0, le=100000)
            price_per_call_usd: float = Field(..., gt=0)
            owner_address: str = Field(..., min_length=4)

        class TransferRequest(BaseModel):
            token_id: str = Field(..., min_length=4)
            from_address: str = Field(..., min_length=4)
            to_address: str = Field(..., min_length=4)

        @router.post("/nft/mint")
        async def mint_nft(body: MintRequest):
            nft = self._registry.mint(body.capability_id, body.product_id,
                                       body.total_calls, body.price_per_call_usd, body.owner_address)
            return {"token_id": nft.token_id, "total_calls": nft.total_calls,
                    "owner": nft.owner_address[:8] + "..."}

        @router.post("/nft/transfer")
        async def transfer_nft(body: TransferRequest):
            return self._registry.transfer(body.token_id, body.from_address, body.to_address)

        @router.get("/nft/stats")
        async def nft_stats():
            return self._registry.stats()

    def get_manifest_extension(self):
        return {"nft": {"standard": "ERC-721", "transferable": True}}
