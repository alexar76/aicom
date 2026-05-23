# AIMarket Protocol v2 — Federation

**Status:** Draft v2.0.0  

## Value in plain words

Open rules for how AI marketplaces discover, price, pay, and verify calls — so hubs and apps interoperate like websites use HTTP. Build once, sell anywhere.

**Простыми словами:** Открытые правила: как AI-маркетплейсы ищут, ценообразуют, платят и проверяют вызовы — чтобы хабы и приложения работали вместе, как сайты на HTTP. Собрал раз — продаёшь везде.

Full text: [docs/value.md](docs/value.md)


## Documents

| Document | Description |
|----------|-------------|
| [spec.md](spec.md) | Full protocol specification (RFC-style) |
| [ecosystem.md](ecosystem.md) | **Ecosystem map** — Mermaid diagrams (topology, invoke, federation, plugins) |
| [schemas/well-known.json](schemas/well-known.json) | JSON Schema for `.well-known/ai-market.json` |
| [schemas/manifest.json](schemas/manifest.json) | JSON Schema for capability manifest |
| [schemas/receipt.json](schemas/receipt.json) | JSON Schema for signed receipts |
| [schemas/federation-announce.json](schemas/federation-announce.json) | Federation announcement message |
| [test-vectors/](test-vectors/) | Reference test vectors for signature verification |

## Live Reference Implementation

**[modelmarket.dev](https://modelmarket.dev)** — production hub running this protocol:

| Resource | URL |
|----------|-----|
| .well-known | [modelmarket.dev/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json) |
| Widget demo | [modelmarket.dev/widget/demo](https://modelmarket.dev/widget/demo) |
| AI Economy live | [modelmarket.dev/live](https://modelmarket.dev/live) |
| Integration examples | [modelmarket.dev/examples](https://modelmarket.dev/examples) |

## Quick Start

```bash
# Live hub:
curl https://modelmarket.dev/.well-known/ai-market.json

# Federated search:
curl "https://modelmarket.dev/ai-market/v2/search?intent=translate&budget=3.00"

# Open channel + invoke + close:
CH=$(curl -s -X POST https://modelmarket.dev/ai-market/v2/channel/open \
  -H "Content-Type: application/json" \
  -d '{"deposit_usd":3.0}' | jq -r '.channel.channel_id')

curl -X POST https://modelmarket.dev/ai-market/v2/invoke \
  -H "X-Payment-Channel: $CH" \
  -d '{"product_id":"prod-translate","capability_id":"translate.multi@v2","source_hub":"local","input":{"text":"hello"}}'

curl -X POST https://modelmarket.dev/ai-market/v2/channel/close \
  -d "{\"channel_id\":\"$CH\"}"
```

## Protocol Versions

| Version | Scope |
|---------|-------|
| v1 | Single marketplace: .well-known, MCP manifest, 402 flow, channels, pipelines |
| v2 | Federation: cross-hub crawl, index, search, route, reputation |
