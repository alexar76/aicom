"""aimarket-promo plugin — Signed time-locked discount offers — Yield Management for AI."""

from aimarket_hub.plugin import HubPlugin
from aimarket_promo.time_locked_promo import PromoMarket


class PromoPlugin(HubPlugin):
    name = "aimarket-promo"
    version = "2.0.0"
    description = "Signed time-locked discount offers — Yield Management for AI"
    homepage = "https://github.com/ai-factory/aimarket-promo"
    category = "monetization"

    def __init__(self):
        super().__init__()
        self._market = PromoMarket()

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field
        from fastapi.responses import JSONResponse

        class CreateOfferRequest(BaseModel):
            provider_hub: str = Field(..., min_length=4)
            capability_id: str = Field(..., min_length=2)
            product_id: str = Field(..., min_length=2)
            original_price_usd: float = Field(..., gt=0)
            discount_pct: float = Field(0.5, gt=0, le=1.0)
            duration_hours: float = Field(2.0, gt=0, le=168)

        @router.post("/promo/create")
        async def create_offer(body: CreateOfferRequest):
            offer = self._market.create_offer(body.provider_hub, body.capability_id,
                                               body.product_id, body.original_price_usd,
                                               body.discount_pct, body.duration_hours)
            return {"offer_id": offer.offer_id, "discounted_price": offer.discounted_price_usd,
                    "expires_at": offer.expires_at, "active": offer.is_active}

        @router.get("/promo/active")
        async def active_offers(capability_id: str = None):
            offers = self._market.get_active_offers(capability_id)
            return {"offers": [{"id": o.offer_id, "price": o.discounted_price_usd,
                    "discount": f"{o.discount_pct*100:.0f}%", "provider": o.provider_hub,
                    "expires": o.expires_at} for o in offers]}

        @router.get("/promo/stats")
        async def promo_stats():
            return self._market.market_stats()

    def get_manifest_extension(self):
        return {"promo": {"enabled": True, "max_discount_pct": 100}}
