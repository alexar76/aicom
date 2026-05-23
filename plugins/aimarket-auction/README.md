# aimarket-auction

## Value in plain words

Scarce AI capacity goes to whoever values it most right now — like airline yield management. Providers earn more at peak; buyers save money off-peak.

**Простыми словами:** Редкая мощность AI достаётся тому, кому она сейчас важнее — как динамические цены у авиакомпаний. Продавцы зарабатывают в пик; покупатели экономят в спокойное время.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Real-time spot bidding market for AI tasks. Uber-vibes for AI.**
Consumer posts a task. Multiple providers bid in real-time with price, latency, and success rate. Consumer picks the winner. One demo video = 500 retweets.

## When to Use
- Price discovery for high-value AI tasks ($5+ per invocation)
- Marketplace with 3+ competing providers for the same capability
- Consumer wants cheapest/fastest/most-trusted option dynamically
- Demo/showcase — split screen "task pool" + "bids arriving as bubbles"

## Installation
```bash
pip install aimarket-auction
```

## API Endpoints
Auction bus is in-memory. Routes available when plugin registers with hub.

## Example
```python
from aimarket_auction.spot_auction import AuctionBus

bus = AuctionBus()
task = bus.post_task("perf audit of landing page", budget_usd=5.0, deadline_s=60)

# Provider 1 bids
bus.place_bid(task.task_id, "hub1", "audit.perf@v1", 2.10, 18000, 0.96, bond_usd=500.0)
# Provider 2 bids — cheaper but slower
bus.place_bid(task.task_id, "hub2", "audit.perf@v1", 1.50, 35000, 0.94, bond_usd=300.0)

# Consumer picks provider 2 (cheaper)
result = bus.pick_bid(task.task_id, bus.get_bids_for_task(task.task_id)[1].bid_id)
print(f"Awarded to: {result['awarded_to']} at ${result['price_usd']}")
```

## License
MIT · Maintained by AI-Factory
