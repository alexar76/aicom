# aimarket-promo

## Value in plain words

Time-limited signed discounts fill idle AI capacity — like happy hour for GPU slots. Providers move spare compute; buyers catch real deals.

**Простыми словами:** Подписанные скидки на время заполняют простаивающую мощность AI — «happy hour» для GPU. Продавцы загружают простой; покупатели ловят настоящие акции.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Time-locked discount offers signed by providers. Yield Management for AI.**
Provider signs "50% off for queries in the next 2 hours." Crawler agents auto-discover promos. Consumers auto-apply the best available discount at invoke time. Providers pop demand when they have spare capacity.

## When to Use
- Provider has spare GPU capacity → 50% off for 2 hours
- Launch promo → "80% off first 100 calls"
- Volume discount → "10% off for calls > $5"
- Trust-gated offers → "only consumers with trust_score > 0.7 get this discount"

## Installation
```bash
pip install aimarket-promo
```

## Example
```python
from aimarket_hub.signing import Signer
from aimarket_promo.time_locked_promo import PromoMarket

signer = Signer()
market = PromoMarket(signer)

# Provider creates a 50% off offer for 2 hours
offer = market.create_offer(
    provider_hub="https://translate.example.com",
    capability_id="translate.multi@v2",
    product_id="prod-001",
    original_price_usd=1.00,
    discount_pct=0.50,
    duration_hours=2.0,
    max_uses=100,
    reason="spare capacity — GPUs idle"
)
print(f"Offer: ${offer.discounted_price_usd} (was ${offer.original_price_usd})")

# Consumer invokes — auto-applies best promo
result = market.apply_best_offer("translate.multi@v2", consumer_trust_score=0.85)
if result["applied"]:
    print(f"Price: ${result['price_usd']}, Saved: ${result['saved_usd']}")

# Market stats
print(market.market_stats())
# {"active_offers": 1, "total_consumer_savings_usd": 0.50, ...}
```

## License
MIT · Maintained by AI-Factory
