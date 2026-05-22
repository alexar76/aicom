"""Time-Locked Offers / Promo (#12)

Provider-signed offer: "50% off for queries in the next 2 hours."
Crawler agents auto-catch promos; providers pop demand when they have spare capacity.

Yield Management for AI.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.signing import Signer


@dataclass
class PromoOffer:
    """A time-limited, provider-signed discount offer."""

    offer_id: str = field(default_factory=lambda: f"promo_{uuid.uuid4().hex[:12]}")
    provider_hub: str = ""
    capability_id: str = ""
    product_id: str = ""
    discount_pct: float = 0.50  # 0.50 = 50% off
    original_price_usd: float = 1.00
    discounted_price_usd: float = 0.50
    starts_at: str = ""  # ISO 8601
    expires_at: str = ""  # ISO 8601
    max_uses: int = 100  # Total uses allowed
    uses_remaining: int = 100
    min_trust_score: float = 0.0  # Minimum consumer trust to qualify
    reason: str = ""  # "spare capacity", "launch promo", "volume discount"
    signature: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @property
    def is_active(self) -> bool:
        from calendar import timegm
        now = time.time()
        try:
            expires = timegm(time.strptime(self.expires_at, "%Y-%m-%dT%H:%M:%SZ"))
            starts = timegm(time.strptime(self.starts_at, "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OSError):
            return False
        return starts <= now <= expires and self.uses_remaining > 0

    @property
    def savings_usd(self) -> float:
        return round(self.original_price_usd - self.discounted_price_usd, 4)

    def canonical(self) -> str:
        return (
            f"offer_id:{self.offer_id}"
            f"|provider:{self.provider_hub}"
            f"|capability:{self.capability_id}"
            f"|discount_pct:{self.discount_pct}"
            f"|price:{self.discounted_price_usd}"
            f"|expires:{self.expires_at}"
            f"|max_uses:{self.max_uses}"
        )

    def sign(self, signer: Signer) -> "PromoOffer":
        self.signature = signer.sign_canonical(self.canonical())
        return self

    def verify(self, signer: Signer, public_key_b64: str) -> bool:
        return signer.verify(public_key_b64, self.signature, self.canonical())

    def consume(self) -> dict[str, Any]:
        """Consume one use of the promo."""
        if not self.is_active:
            return {"error": "promo expired or exhausted", "offer_id": self.offer_id}
        self.uses_remaining -= 1
        return {
            "offer_id": self.offer_id,
            "consumed": True,
            "price_usd": self.discounted_price_usd,
            "saved_usd": self.savings_usd,
            "uses_remaining": self.uses_remaining,
        }


class PromoMarket:
    """Market for time-locked promotional offers.

    Providers create signed offers. Crawlers discover and index them.
    Consumers apply promos at invoke time for automatic discounts.
    """

    def __init__(self, signer: Signer | None = None):
        self.signer = signer or Signer()
        self._offers: dict[str, PromoOffer] = {}

    def create_offer(
        self,
        provider_hub: str,
        capability_id: str,
        product_id: str,
        original_price_usd: float,
        discount_pct: float = 0.50,
        duration_hours: float = 2.0,
        max_uses: int = 100,
        reason: str = "spare capacity",
        min_trust_score: float = 0.0,
    ) -> PromoOffer:
        """Create a signed time-locked promo offer."""
        now = time.time()
        offer = PromoOffer(
            provider_hub=provider_hub,
            capability_id=capability_id,
            product_id=product_id,
            discount_pct=discount_pct,
            original_price_usd=original_price_usd,
            discounted_price_usd=round(original_price_usd * (1 - discount_pct), 4),
            starts_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            expires_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + duration_hours * 3600)),
            max_uses=max_uses,
            uses_remaining=max_uses,
            reason=reason,
            min_trust_score=min_trust_score,
        ).sign(self.signer)

        self._offers[offer.offer_id] = offer
        return offer

    def get_active_offers(self, capability_id: str | None = None) -> list[PromoOffer]:
        """Get all active offers, optionally filtered by capability."""
        active = [o for o in self._offers.values() if o.is_active]
        if capability_id:
            active = [o for o in active if o.capability_id == capability_id]
        return sorted(active, key=lambda o: o.discount_pct, reverse=True)

    def get_best_offer(self, capability_id: str, consumer_trust_score: float = 0.0) -> PromoOffer | None:
        """Get the best active offer for a capability (highest discount)."""
        active = [
            o for o in self._offers.values()
            if o.is_active
            and o.capability_id == capability_id
            and consumer_trust_score >= o.min_trust_score
        ]
        if not active:
            return None
        return max(active, key=lambda o: o.discount_pct)

    def apply_best_offer(
        self, capability_id: str, consumer_trust_score: float = 0.0
    ) -> dict[str, Any]:
        """Apply the best available promo to an invocation."""
        offer = self.get_best_offer(capability_id, consumer_trust_score)
        if not offer:
            return {"applied": False, "reason": "no active offers"}

        result = offer.consume()
        result["applied"] = True
        result["capability_id"] = capability_id
        result["provider"] = offer.provider_hub
        result["reason"] = offer.reason
        return result

    def expire_offers(self) -> int:
        """Clean up expired offers. Returns count of newly expired."""
        count = sum(1 for o in self._offers.values() if not o.is_active)
        # Remove fully used or expired offers
        self._offers = {
            k: v for k, v in self._offers.items()
            if v.is_active or v.uses_remaining > 0
        }
        return count

    def provider_stats(self, provider_hub: str) -> dict[str, Any]:
        """Stats for a provider's offers."""
        offers = [o for o in self._offers.values() if o.provider_hub == provider_hub]
        active = [o for o in offers if o.is_active]
        total_uses = sum(o.max_uses - o.uses_remaining for o in offers)
        total_savings = sum(o.savings_usd * (o.max_uses - o.uses_remaining) for o in offers)

        return {
            "total_offers_created": len(offers),
            "active_offers": len(active),
            "total_uses_claimed": total_uses,
            "total_consumer_savings_usd": round(total_savings, 4),
            "avg_discount_pct": round(sum(o.discount_pct for o in offers) / max(len(offers), 1), 4),
        }

    def market_stats(self) -> dict[str, Any]:
        """Global promo market statistics."""
        active = [o for o in self._offers.values() if o.is_active]
        total_uses = sum(o.max_uses - o.uses_remaining for o in self._offers.values())
        total_savings = sum(
            o.savings_usd * (o.max_uses - o.uses_remaining)
            for o in self._offers.values()
        )

        return {
            "total_offers": len(self._offers),
            "active_offers": len(active),
            "total_uses_claimed": total_uses,
            "total_consumer_savings_usd": round(total_savings, 4),
            "providers_with_active_offers": len(set(o.provider_hub for o in active)),
            "most_discounted_capability": max(
                active, key=lambda o: o.discount_pct
            ).capability_id if active else None,
        }
