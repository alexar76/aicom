# AIMarket Protocol v2 — Federation

**Status:** Draft v2.0.0  
**License:** MIT  
**Maintainer:** AI-Factory

The AIMarket Protocol defines how AI capability marketplaces discover, index, and transact with each other. It extends Protocol v1 (single-instance HTTP 402 marketplace) with **federation**: any hub can crawl `.well-known/ai-market.json` from any other hub, index their capabilities, and route invocations with transparent commission.

## Documents

| Document | Description |
|----------|-------------|
| [spec.md](spec.md) | Full protocol specification (RFC-style) |
| [schemas/well-known.json](schemas/well-known.json) | JSON Schema for `.well-known/ai-market.json` |
| [schemas/manifest.json](schemas/manifest.json) | JSON Schema for capability manifest |
| [schemas/receipt.json](schemas/receipt.json) | JSON Schema for signed receipts |
| [schemas/federation-announce.json](schemas/federation-announce.json) | Federation announcement message |
| [test-vectors/](test-vectors/) | Reference test vectors for signature verification |

## Quick Start

```bash
# Any hub exposes:
curl https://<hub>/.well-known/ai-market.json

# Federated search across all crawled hubs:
curl https://<hub>/ai-market/v2/search?intent=translate&budget=3.00

# Invoke with transparent routing (hub takes opt-in fee):
curl -X POST https://<hub>/ai-market/v2/invoke \
  -H "X-Payment-Channel: ch_..." \
  -d '{"product_id":"...", "capability_id":"...", "input":{...}}'
```

## Protocol Versions

| Version | Scope |
|---------|-------|
| v1 | Single marketplace: .well-known, MCP manifest, 402 flow, channels, pipelines |
| v2 | Federation: cross-hub crawl, index, search, route, reputation |
