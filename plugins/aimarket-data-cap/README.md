# aimarket-data-cap

## Value in plain words

Monetize private documents: others pay per search query, you never hand over raw files. Law firms, labs, and enterprises turn knowledge into revenue safely.

**Простыми словами:** Монетизируете закрытые документы: другие платят за поиск, сырые файлы вы не отдаёте. Юрфирмы, лаборатории и компании превращают знания в доход безопасно.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Data-as-capability. Private corpus → paid RAG-capability.**
Upload your private data corpus. It becomes a paid search capability. You earn 70% of every query. Doubles TAM — sell compute AND data. Snowflake-level monetization for AI marketplaces.

## When to Use
- Law firm uploads 50k court decisions → `legal.us-cases.search@v1`, $0.05/query
- Medical publisher uploads research papers → `medical.papers.search@v1`, $0.10/query
- SaaS company uploads internal docs → `company.kb.search@v1`, $0.03/query
- Any data owner who wants to monetize their private corpus without giving it away

## Installation
```bash
pip install aimarket-data-cap
```

## Example
```python
from aimarket_data_cap.data_capability import DataCapabilityRegistry

reg = DataCapabilityRegistry(platform_fee_pct=0.30)

# Law firm registers their corpus
dc = reg.register(
    owner_address="0xLawFirm",
    description="US court decisions 2020-2025, federal circuit",
    data_size_bytes=50_000_000, document_count=50000,
    query_price_usd=0.05,
    tags=["legal", "us-courts", "precedents"]
)

# Consumer queries — pays $0.05
result = reg.query(dc.capability_id, "precedent for breach of contract damages")
print(f"Price: ${result['price_usd']}")
print(f"Owner earns: ${result['revenue_split']['owner_usd']} (70%)")
print(f"Platform earns: ${result['revenue_split']['platform_usd']} (30%)")

# Data owner checks earnings
rev = reg.get_owner_revenue("0xLawFirm")
print(f"Total earned: ${rev['total_earned_usd']:.2f}")
```

## Revenue Split
Default 70/30 — data owner gets 70%, platform gets 30%. Configurable per capability.

## License
MIT · Maintained by AI-Factory
