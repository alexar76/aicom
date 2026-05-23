# aimarket-nft

## Value in plain words

Pre-paid AI credits as transferable tokens — gift them, resell unused balance, or run loyalty programs without building billing from scratch.

**Простыми словами:** Предоплаченные кредиты AI как передаваемые токены — подарить, перепродать остаток или сделать программу лояльности без биллинга с нуля.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Tokenized pre-paid capability credits. Transferable between owners.**
Pre-pay for 1000 calls → get an NFT. Sell on secondary market. Transfer to sub-agents. Gift to friends. Liquidity for unused credits. Something Stripe fundamentally cannot do.

## When to Use
- Bulk purchase discounts — "buy 1000 calls at $0.30 each instead of $0.40"
- Secondary market — sell unused credits when project ends
- Agent delegation — give sub-agents pre-paid access without sharing payment keys
- Gift cards — "gifted 100 Lyra calls" viral distribution
- DAO treasury — DAO holds NFTs for shared AI capability access

## Installation
```bash
pip install aimarket-nft
```

## Example
```python
from aimarket_nft.capability_nft import NFTRegistry

reg = NFTRegistry()

# Mint: 100 calls at $0.40 each = $40 total
nft = reg.mint("translate.multi@v2", "prod-001", 100, 0.40, "0xAlice")
print(f"NFT: {nft.token_id}, {nft.remaining_calls} calls remaining")

# Use 5 calls
for _ in range(5):
    reg.consume_call(nft.token_id)
print(f"Remaining: {nft.remaining_calls}")  # 95

# Transfer to Bob
reg.transfer(nft.token_id, "0xAlice", "0xBob")
print(f"Owner: {nft.owner_address}")  # 0xBob

# Gift 50 calls to a friend
gift = reg.gift("summarize@v1", "prod-002", 50, 0.25, "0xAlice", "0xCharlie")
print(f"Gifted: {gift.token_id} to {gift.owner_address}")

# Stats
print(reg.stats())
# {"total_nfts": 2, "active_nfts": 1, "total_transfers": 1, ...}
```

## ERC-721 Compatible
Each NFT includes standard metadata: name, description, attributes (capability, total calls, price per call, transfer count). Ready for OpenSea/Rarible listing.

## License
MIT · Maintained by AI-Factory
