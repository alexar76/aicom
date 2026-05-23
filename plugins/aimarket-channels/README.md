# aimarket-channels

## Value in plain words

Pay once into a prepaid tab, make dozens of tiny AI calls, settle once on-chain. No credit-card fee on every micro-cent — fast sessions for agents and apps.

**Простыми словами:** Пополняете «вкладку» один раз, делаете десятки мелких вызовов AI, закрываете один раз on-chain. Без комиссии карты на каждую копейку — быстрые сессии для агентов и приложений.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**Pre-funded payment channels for off-chain capability invocation.**
Open a channel with one on-chain deposit, invoke multiple capabilities off-chain, settle once. Reduces per-call blockchain transactions from N to 1.

---

## When to Use

| Scenario | Why this plugin |
|----------|----------------|
| Multi-step AI workflows (translate → review → summarize) | One deposit, 3 invocations, 1 settlement — not 3 separate on-chain transactions |
| High-frequency invocation (100+ calls/hour) | Per-call on-chain TX would cost more in gas than the capability itself |
| Agent-to-agent orchestration | External AI agents open a channel and run autonomous multi-step plans |
| Consumer with fixed budget | Pre-fund $5.00, let the orchestrator spend up to that, get refund of remainder |
| Demo/staging without real on-chain TX | Accept `demo-*` tx hashes for development (configurable) |

---

## Installation

```bash
pip install aimarket-channels
```

No configuration required — channels work immediately. Verify:

```bash
curl -X POST http://localhost:9080/ai-market/v2/channel/open \
  -H "Content-Type: application/json" \
  -d '{"deposit_usd": 3.00}' | jq '.channel.channel_id'
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai-market/v2/channel/open` | Open a pre-funded payment channel |
| `POST` | `/ai-market/v2/channel/close` | Close channel, compute settlement, refund remainder |

### Open Channel

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/channel/open \
  -H "Content-Type: application/json" \
  -d '{
    "deposit_usd": 3.00,
    "token": "USDT",
    "chain": "base",
    "wallet": "0x...",
    "tx_hash": "0xabc123..."
  }'
```

Response:
```json
{
  "channel": {
    "channel_id": "ch_a8f3b2c1d4e5",
    "balance_usd": 3.00,
    "original_deposit_usd": 3.00,
    "used_usd": 0.00,
    "token": "USDT",
    "chain": "base",
    "status": "open",
    "opened_at": "2026-05-22T12:00:00Z",
    "expires_at": "2026-05-23T12:00:00Z"
  }
}
```

### Close Channel

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/channel/close \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "ch_a8f3b2c1d4e5",
    "settle_tx_hash": "0xsettle..."
  }'
```

Response:
```json
{
  "settlement": {
    "channel_id": "ch_a8f3b2c1d4e5",
    "used_usd": 1.60,
    "refund_usd": 1.40,
    "original_deposit_usd": 3.00,
    "status": "settled"
  }
}
```

---

## End-to-End Example

```python
import requests

HUB = "https://modelmarket.dev"

# 1. Open channel — one on-chain TX
ch = requests.post(f"{HUB}/ai-market/v2/channel/open", json={
    "deposit_usd": 3.00, "tx_hash": "0x_on_chain_deposit"
}).json()
ch_id = ch["channel"]["channel_id"]
print(f"Channel: {ch_id}, balance: $3.00")

# 2. Invoke multiple capabilities — all off-chain
headers = {"X-Payment-Channel": ch_id}
plan = [
    ("prod-translate", "translate.multi@v2", {"text": "Hello world", "locales": ["ru", "fr"]}),
    ("prod-legal", "legal.review@v1", {"documents": {"main": "..."}}),
    ("prod-summarize", "summarize@v1", {"text": "..."}),
]

total = 0.0
for pid, cid, inp in plan:
    r = requests.post(f"{HUB}/ai-market/v2/invoke", json={
        "product_id": pid, "capability_id": cid,
        "source_hub": "local", "input": inp
    }, headers=headers)
    result = r.json()
    total += result.get("price_usd", 0)
    print(f"  {cid}: ${result.get('price_usd', 0):.2f} {'OK' if result.get('success') else 'FAIL'}")

# 3. Close channel — one on-chain TX
settle = requests.post(f"{HUB}/ai-market/v2/channel/close", json={
    "channel_id": ch_id, "settle_tx_hash": "0x_on_chain_settlement"
}).json()

print(f"Used: ${settle['settlement']['used_usd']:.2f}")
print(f"Refund: ${settle['settlement']['refund_usd']:.2f}")
print(f"Saved {(len(plan) - 1)} on-chain transactions")
```

---

## Channel Lifecycle

```
OPEN (on-chain deposit)
  │
  ├── INVOKE (off-chain debit) ──┐
  ├── INVOKE (off-chain debit) ──┤  N invocations
  ├── INVOKE (off-chain debit) ──┘
  │
  ├── SAFETY ABORT → auto-refund to channel
  │
CLOSE (on-chain settlement)
  → used_usd sent to providers
  → refund_usd returned to consumer
```

**Properties:**
- **24h auto-expiry** — channels close automatically after 24 hours
- **Atomic safety refund** — blocked invocations refund to channel immediately
- **Single-writer ledger** — no double-spend possible (hub is sole writer)
- **Demo mode** — `demo-*` tx hashes accepted for development (configurable)

---

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `AIMARKET_CHANNEL_MAX_DEPOSIT` | `10000` | Maximum deposit in USD |
| `AIMARKET_CHANNEL_EXPIRY_HOURS` | `24` | Channel auto-expiry time |
| `AIFACTORY_PAYMENT_VERIFY_STUB` | `1` | Accept `demo-*` tx hashes (dev) |

---

## Recommended Deployment

| Environment | Recommendation |
|-------------|---------------|
| Development | Stub verification on, demo tx hashes accepted |
| Staging | Testnet RPC (Base Sepolia), real tx verification |
| Production | Mainnet RPC, real on-chain deposits required |

**Combine with:**
- `aimarket-safety` — safety blocks auto-refund to channel
- `aimarket-orchestrator` — orchestrator opens one channel per task, runs multi-step plan
- `aimarket-streaming` — per-chunk billing debits the channel incrementally

---

## Performance

| Metric | Value |
|--------|-------|
| Channel open latency | < 5ms (in-memory ledger) |
| Debit latency | < 1ms |
| Close + settlement computation | < 2ms |
| Concurrent channels | Unlimited (in-memory, single-process) |
| Production upgrade path | Replace `ChannelLedger` with PostgreSQL for multi-process |

---

## Security Considerations

- **No custody** — the protocol never holds funds. Channels are simulated constructs for the reference implementation. Production uses on-chain escrow contracts
- **Sequential ledger** — single-writer (hub process), no double-spend vector
- **Nonce replay protection** — each channel is bound to a single session
- **Demo tx hashes must be disabled in production** — set `AIFACTORY_PAYMENT_VERIFY_STUB=0`

---

## License

MIT · Maintained by AI-Factory · [GitHub](https://github.com/ai-factory/aimarket-channels)
