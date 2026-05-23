# aimarket-reputation

## Value in plain words

Shows who you can trust on the marketplace. Providers put money at stake; cheaters lose it. Buyers compare scores before paying — reputation becomes real, not fake stars.

**Простыми словами:** Показывает, кому на маркетплейсе можно доверять. Продавцы ставят залог; мошенники его теряют. Покупатели сравнивают баллы до оплаты — репутация настоящая, не накрученные звёзды.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Stake-bond + signed outcomes + dispute resolution. On-chain reputation aggregation.**
Providers lock USDT bond against quality. Every invoke generates a signed outcome. Disputes slash bonds. Reputation is a cryptographically verifiable aggregate — not website reviews.

---

## When to Use

| Scenario | Why this plugin |
|----------|----------------|
| Marketplace where providers compete on quality | Consumers see trust scores before choosing a capability — providers with higher bonds and success rates rank higher |
| High-stakes invocations ($10+/call) | Provider has economic stake. If they deliver garbage, bond gets slashed and paid to consumer |
| Sybil-resistant provider onboarding | Bond requirement ($100 testnet, $1000 mainnet) makes fake provider farms economically unviable |
| Consumer dispute resolution | Signed dispute → auditor reviews → bond slashed → consumer compensated. All on-chain verifiable |
| Compliance audit of provider performance | `compute_reputation_score()` returns auditable breakdown: age, bond, success_rate, dispute_count, slash_ratio |

---

## Installation

```bash
pip install aimarket-reputation
```

---

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `AIMARKET_REPUTATION_MIN_BOND_USD` | `100` | Minimum bond for testnet listing |
| `AIMARKET_REPUTATION_MAINNET_MIN_BOND_USD` | `1000` | Minimum bond for mainnet listing |
| `AIMARKET_REPUTATION_WINDOW_DAYS` | `30` | Rolling window for success rate calculation |
| `AIMARKET_REPUTATION_DEFAULT_WEIGHTS` | `0.2,0.3,0.35,0.15` | age, bond, success_rate, volume |

---

## API Endpoints Added

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai-market/v2/reputation/{hub_url}` | Full trust score breakdown for a provider |
| `POST` | `/ai-market/v2/reputation/events` | Submit signed reputation attestations |

### Get Reputation

```bash
curl https://modelmarket.dev/ai-market/v2/reputation/https://provider.example.com | jq .
```

```json
{
  "hub_url": "https://provider.example.com",
  "trust_score": 0.872,
  "details": {
    "provider_hub": "https://provider.example.com",
    "score": 0.872,
    "bond_usd": 2500.0,
    "success_rate_30d": 0.967,
    "avg_quality_score_30d": 0.94,
    "dispute_count": 1,
    "slash_ratio": 0.05,
    "total_outcomes": 3412
  }
}
```

### Submit Reputation Events

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/reputation/events \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "invocation_success",
      "provider_hub": "https://provider.example.com",
      "capability_id": "translate.multi@v2",
      "price_usd": 0.40,
      "latency_ms": 8100,
      "consumer_hub": "https://consumer.example.com"
    }]
  }'
```

---

## Trust Score Formula

```
trust_score = w1 × age_factor + w2 × bond_factor + w3 × success_rate + w4 × volume_factor
             - 0.3 × slash_ratio - 0.05 × min(disputes/10, 1.0)

age_factor     = min(days_since_first_seen / 365, 1.0)
bond_factor    = min(log10(bond_usd) / 4, 1.0)     # 0 at $1, 1 at $10k
success_rate   = successful / total (30-day rolling window)
volume_factor  = min(log10(volume_usd_30d) / 5, 1.0)

Default weights: 0.20, 0.30, 0.35, 0.15
```

---

## End-to-End Example

```python
from aimarket_hub.signing import Signer
from aimarket_reputation.reputation_oracle import (
    ReputationOracle, OutcomeStatus
)

signer = Signer()
oracle = ReputationOracle(signer)

# 1. Provider stakes bond
bond = oracle.stake_bond(
    provider_hub="https://translate-pro.example.com",
    amount_usd=2000.0,
    token="USDT", chain="base",
    tx_hash="0x_on_chain_bond_deposit"
)
print(f"Bond: ${bond.amount_usd}")

# 2. Consumers invoke and sign outcomes
for i in range(100):
    oracle.record_outcome(
        invocation_id=f"inv_{i}",
        capability_id="translate.multi@v2",
        product_id="prod-001",
        provider_hub="https://translate-pro.example.com",
        consumer_hub=f"consumer_{i % 5}",
        status=OutcomeStatus.SUCCESS,
        price_usd=0.40,
        latency_ms=8000 + (i % 20) * 100,
        quality_score=0.90 + (i % 10) * 0.01
    )

# 3. Some consumer files dispute for one bad invocation
dispute = oracle.file_dispute(
    invocation_id="inv_42",
    provider_hub="https://translate-pro.example.com",
    consumer_hub="consumer_2",
    reason="Returned wrong language — asked for French, got German",
    requested_slash_pct=0.10,
    evidence={"expected_lang": "fr", "received_lang": "de",
              "screenshot_url": "https://..."}
)
print(f"Dispute filed: {dispute.dispute_id}")

# 4. Auditor resolves dispute — 5% bond slash
resolution = oracle.resolve_dispute(dispute.dispute_id, slash_pct=0.05)
print(f"Slashed: ${resolution['slashed_usd']:.2f}")
print(f"Bond remaining: ${resolution['bond_remaining_usd']:.2f}")

# 5. Compute reputation score
score = oracle.compute_reputation_score("https://translate-pro.example.com")
print(f"Trust Score: {score['score']:.3f}")
print(f"  Success Rate: {score['success_rate_30d']:.1%}")
print(f"  Quality Avg:  {score['avg_quality_score_30d']:.2f}")
print(f"  Disputes:     {score['dispute_count']}")
print(f"  Slash Ratio:  {score['slash_ratio']:.1%}")
```

---

## Manifest Extension

```json
{
  "plugin_extensions": {
    "aimarket-reputation": {
      "reputation": {
        "bond_required": true,
        "slashing_enabled": true,
        "min_bond_testnet_usd": 100,
        "min_bond_mainnet_usd": 1000,
        "weights": {"age": 0.20, "bond": 0.30, "success_rate": 0.35, "volume": 0.15}
      }
    }
  }
}
```

---

## Recommended Deployment

| Environment | Recommendation |
|-------------|---------------|
| Development | Use in-memory ledger, no real bonds |
| Staging | Testnet bonds on Base Sepolia ($100 minimum) |
| Production | Mainnet bonds on Base ($1000 minimum). Multi-sig dispute resolution |
| Enterprise | DAO-governed dispute resolution with multi-sig auditor committee |

**Combine with:**
- `aimarket-safety` — safety blocks don't count as failures (consumer isn't penalized)
- `aimarket-zk` — ZK proofs of invocation quality without revealing consumer identity
- `aimarket-nft` — stake bond as NFT for transferable provider reputation

---

## Performance

| Metric | Value |
|--------|-------|
| Outcome recording | < 1ms |
| Dispute filing + signing | < 2ms |
| Trust score computation (1000 outcomes) | < 5ms |
| Storage per outcome | ~200 bytes |
| Scalability | 1M outcomes = ~200 MB (fits in memory) |

---

## Security Considerations

- **Outcomes are Ed25519-signed** by consumer — providers can't forge good reviews
- **Disputes are Ed25519-signed** — consumers can't file disputes for invocations that didn't happen
- **Bond slashing requires auditor resolution** — not automatic. Prevents griefing attacks
- **Reputation is a protocol-level aggregate** — not a website review. Sybil-resistant via bond requirement

---

## License

MIT · Maintained by AI-Factory · [GitHub](https://github.com/ai-factory/aimarket-reputation)
