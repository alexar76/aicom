# AIMarket Protocol v2 — Federation Specification

**Version:** 2.0.0-draft  
**License:** MIT  
**Last Updated:** 2026-05-21

---

## Abstract

The AIMarket Protocol defines a standard for AI capability marketplaces to federate. Any hub implementing this spec can discover capabilities from other hubs, index them in a unified catalog, route invocations with transparent commission, and aggregate reputation across the network. The protocol extends HTTP 402-based AI payments (v1) with cross-hub discovery and routing.

## Status of This Memo

This document is an MIT-licensed open standard. It is NOT an IETF RFC, but follows RFC style for clarity. Implementation experience is sought. Comments to the AIMarket Protocol repository.

---

## 1. Introduction

### 1.1. Motivation

AI-Factory Protocol v1 defined a single-marketplace model: one server exposes capabilities via `.well-known/ai-market.json`, handles HTTP 402 payments, and executes invocations. This works for a single operator but creates silos.

Protocol v2 adds **federation**: multiple hubs form a network where:
- Any hub can crawl any other hub's `.well-known`
- Capabilities are indexed across the network
- Invocations route transparently with opt-in commission
- Reputation aggregates across hubs
- Users see a unified catalog regardless of which hub they connect to

### 1.2. Design Principles

1. **Decentralized discovery** — No central registry. Hubs discover each other via `.well-known` + seed lists.
2. **Transparent routing** — Client pays provider; hub may add opt-in commission.
3. **Verifiable reputation** — Signed reputation events verified independently.
4. **Compatible with v1** — A v2 hub also implements v1 endpoints for backward compatibility.
5. **No custody** — The protocol never holds funds; payment channels are on-chain constructs.

### 1.3. Terminology

| Term | Definition |
|------|-----------|
| **Hub** | An instance implementing this protocol |
| **Provider** | A hub that hosts capabilities (can execute them) |
| **Consumer** | A hub or agent that invokes capabilities |
| **Seed list** | Initial set of `.well-known` URLs for a hub to crawl |
| **Federated catalog** | Union of all capabilities discovered across all crawled hubs |
| **Routing fee** | Opt-in percentage a hub takes for forwarding an invocation |
| **Reputation event** | Signed attestation about a provider or capability |

### 1.4. Ecosystem architecture (visual)

For a single map of how Factory, Hub, Mesh, clients, plugins, and on-chain settlement connect under this protocol, see **[ecosystem.md](ecosystem.md)** (Mermaid diagrams: topology, invoke paths, federation mesh, plugin pipeline, persistence).

---

## 2. Discovery

### 2.1. Root Well-Known (v2 extended)

```
GET /.well-known/ai-market.json
```

Response (v2 adds `hub_version`, `federation` and `peers`):

```json
{
  "name": "AI-Factory Hub",
  "protocol_versions": ["v1", "v2"],
  "hub_version": "2.0.0",
  "mcp_endpoint": "https://hub.example.com/ai-market/mcp",
  "manifest_url": "https://hub.example.com/ai-market/manifest",
  "products_count": 12,
  "capabilities_count": 47,
  "federated_capabilities_count": 234,
  "supported_chains": ["base", "ethereum", "solana"],
  "supported_tokens": ["USDT", "USDC"],
  "signer_public_key": "AbCdEf1234...",
  "federation": {
    "crawl_interval_s": 3600,
    "routing_fee_bps": 100,
    "min_trust_score": 0.3,
    "seed_list": [
      "https://hub2.example.com/.well-known/ai-market.json",
      "https://hub3.example.com/.well-known/ai-market.json"
    ]
  },
  "peers": [
    {
      "url": "https://hub2.example.com",
      "name": "Legal AI Hub",
      "capabilities_count": 34,
      "last_crawl": "2026-05-21T10:00:00Z",
      "trust_score": 0.85
    }
  ]
}
```

**New v2 fields:**

| Field | Type | Description |
|-------|------|-------------|
| `hub_version` | string | Semver of hub software |
| `federated_capabilities_count` | int | Total capabilities including federated |
| `federation` | object | Federation configuration |
| `federation.crawl_interval_s` | int | How often this hub crawls peers |
| `federation.routing_fee_bps` | int | Fee in basis points (100 = 1%) |
| `federation.min_trust_score` | float | Minimum trust to list a peer |
| `federation.seed_list` | string[] | Initial peer URLs |
| `peers` | object[] | Known peer hubs (discovered + seeded) |

### 2.2. Crawl Protocol

A hub crawler follows this algorithm:

```
1. Load seed_list from config
2. For each seed URL:
   a. GET {seed_url}  (/.well-known/ai-market.json)
   b. Verify response structure
   c. Extract manifest_url
   d. GET {manifest_url}  (full capability catalog)
   e. Verify Ed25519 manifest signature
   f. Validate each capability against JSON Schema
   g. Store in local index
   h. Discover new peer URLs from response.peers
   i. Add new peers to crawl queue (BFS, max depth 3)
3. Repeat on crawl_interval_s
```

**Crawl headers:**

| Header | Value | Purpose |
|--------|-------|---------|
| `User-Agent` | `AIMarketHub/2.0.0` | Identifies crawler |
| `X-AIMarket-Crawler` | `{hub_url}` | Source hub URL |
| `If-None-Match` | `{etag}` | Conditional GET (304 support) |

### 2.3. Federation Announce Endpoint

When a hub starts up or discovers a new peer, it MAY announce itself:

```
POST /ai-market/v2/federation/announce
Content-Type: application/json

{
  "hub_url": "https://newhub.example.com",
  "well_known_url": "https://newhub.example.com/.well-known/ai-market.json",
  "capabilities_count": 23,
  "signer_public_key": "...",
  "signature": "..."
}
```

Response: `200 OK` with `{"acknowledged": true, "peer_added": true}`

---

## 3. Federated Catalog

### 3.1. Federated Manifest

```
GET /ai-market/v2/manifest
```

Returns the manifest with ALL capabilities from ALL crawled hubs:

```json
{
  "protocol_version": "v2",
  "generated_at": "2026-05-21T12:00:00Z",
  "total_capabilities": 234,
  "local_capabilities": 47,
  "federated_capabilities": 187,
  "hubs_indexed": 4,
  "tools": [...],
  "by_hub": {
    "https://hub.example.com": {"capabilities_count": 47, "trust_score": 0.95},
    "https://hub2.example.com": {"capabilities_count": 34, "trust_score": 0.85}
  }
}
```

### 3.2. Federated Search

```
GET /ai-market/v2/search
  ?intent=translate+to+5+languages
  &budget=3.00
  &max_latency_ms=15000
  &min_trust=0.5
  &hub=any
  &limit=20
```

Response includes `source_hub` for each result:

```json
{
  "query": "translate to 5 languages",
  "matches": [
    {
      "product_id": "prod-xxx",
      "capability_id": "translate.multi@v2",
      "source_hub": "https://hub2.example.com",
      "source_hub_name": "Legal AI Hub",
      "score": 0.92,
      "price_per_call_usd": 0.40,
      "routed_price_usd": 0.404,
      "routing_fee_bps": 100,
      "trust_score": 0.85
    }
  ],
  "total_hubs_searched": 4,
  "protocol_version": "v2"
}
```

---

## 4. Federated Invocation (Routing)

### 4.1. Transparent Proxy

```
POST /ai-market/v2/invoke
Content-Type: application/json
X-Payment-Channel: ch_abc123...
X-AIMarket-Route-Ok: true

{
  "product_id": "prod-xxx",
  "capability_id": "translate.multi@v2",
  "source_hub": "https://hub2.example.com",
  "input": {"text": "hello", "locales": ["ru", "en"]}
}
```

The routing hub:
1. Looks up `source_hub` in its index
2. Verifies the provider hub is reachable
3. Adds `X-AIMarket-Routing-Fee: {bps}` and `X-AIMarket-Routing-Hub: {url}` headers
4. Forwards the request to the provider hub
5. Provider hub returns 200 or 402
6. If 402, routing hub forwards `X-Payment-Required` to client
7. If 200, routing hub passes through result + receipt

**Routing flow:**

```
Client → Routing Hub → Provider Hub
   ← 402 (if unpaid)
   → X-Payment: {tx_hash}
   → Provider Hub executes
   ← 200 {result, receipt}
   ← 200 {result, receipt} (pass-through)
```

### 4.2. Routing Commission

The routing hub declares its fee in the `.well-known` response (`federation.routing_fee_bps`). The client sees `routed_price_usd = price * (1 + routing_fee_bps / 10000)` in search results.

Commission settlement happens out-of-band between hubs (on-chain, monthly settlement). The protocol does not prescribe the settlement mechanism — only declares the fee schedule.

---

## 5. Reputation

### 5.1. Trust Score Calculation

Each hub computes a trust score for every peer:

```
trust_score = w1 * age_factor + w2 * bond_factor + w3 * success_rate + w4 * volume_factor

where:
  age_factor        = min(hub_age_days / 365, 1.0)
  bond_factor       = min(log10(bond_usd) / 4, 1.0)  # 0 at $1, 1 at $10k
  success_rate      = successful_invocations / total_invocations (30d window)
  volume_factor     = min(log10(volume_usd_30d) / 5, 1.0)

Default weights: w1=0.2, w2=0.3, w3=0.35, w4=0.15
```

### 5.2. Reputation Events

```
POST /ai-market/v2/reputation/events
Content-Type: application/json

{
  "events": [
    {
      "type": "invocation_success",
      "provider_hub": "https://hub2.example.com",
      "capability_id": "translate.multi@v2",
      "timestamp": "2026-05-21T12:00:00Z",
      "price_usd": 0.40,
      "latency_ms": 8100,
      "consumer_hub": "https://hub.example.com",
      "signature": "..."
    }
  ]
}
```

Reputation events are Ed25519-signed by the reporting hub. Multiple reports from different consumers create a Sybil-resistant reputation graph.

### 5.3. Bond Requirement

To appear in the default seed list of the reference implementation, a hub MUST post a bond in USDT/USDC on a supported chain. The bond proves economic stake and can be slashed for malicious behavior (future governance).

Minimum bond: $100 USDT (testnet), $1,000 USDT (mainnet).

---

## 6. Channels & Receipts

### 6.1. Cross-Hub Channels

Payment channels opened on one hub are NOT automatically valid on another hub. For cross-hub invocations:

1. Client opens a channel on the routing hub
2. Routing hub opens its own channel on the provider hub (pre-funded)
3. Client pays routing hub; routing hub pays provider hub
4. Settlement happens atomically on each respective hub

This avoids cross-hub trust requirements for payment.

### 6.2. Federated Receipts

A federated invocation produces two receipts:
1. **Client receipt** — from routing hub, includes routing fee
2. **Provider receipt** — from provider hub, for the actual execution

Both are Ed25519-signed and independently verifiable.

---

## 7. Security Model

### 7.1. Threat Model

| Threat | Mitigation |
|--------|------------|
| Malicious manifest from fake hub | Ed25519 signature; trust score threshold |
| Man-in-the-middle on routed invoke | HTTPS + manifest signature verification |
| Sybil reputation | Bond requirement + stake age weighting |
| Spam capabilities | Schema validation + trust score gating |
| Free-riding hub (no capabilities, only routes) | Routing fee makes this a viable business model (not a threat) |
| Routing hub steals payment | Client pays provider directly via 402; routing hub only facilitates discovery |

### 7.2. Liability

The protocol is a directory and routing standard, NOT a party to transactions. The receipt is signed by the provider hub, not the routing hub. EULA for hub operators MUST state: "This hub is a directory and routing service, not a party to capability invocations."

---

## 8. API Reference

| Method | Path | Description | Version |
|--------|------|-------------|---------|
| GET | `/.well-known/ai-market.json` | Root discovery manifest | v1+v2 |
| GET | `/ai-market/v2/manifest` | Federated catalog | v2 |
| GET | `/ai-market/v2/search` | Federated NL search | v2 |
| POST | `/ai-market/v2/invoke` | Federated invocation | v2 |
| POST | `/ai-market/v2/federation/announce` | Peer announcement | v2 |
| GET | `/ai-market/v2/federation/peers` | List known peers | v2 |
| POST | `/ai-market/v2/federation/crawl` | Trigger manual crawl | v2 |
| GET | `/ai-market/v2/reputation/{hub_url}` | Trust score for a hub | v2 |
| POST | `/ai-market/v2/reputation/events` | Submit reputation events | v2 |
| GET | `/ai-market/v2/stats/live` | Live invocation stream | v2 |

### 8.1. HTTP Status Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request |
| 402 | Payment required |
| 404 | Not found |
| 502 | Provider hub unreachable |

---

## 9. Reference Implementation

The reference implementation lives at [aimarket-hub](../aimarket-hub/). It is Apache-2.0 licensed and includes:

- **crawler** — Daemon that reads `.well-known` from seed list + discovered URLs
- **indexer** — SQLite/Postgres storage for manifests, schemas, prices, reputation
- **search API** — Federated search with intent matching and trust ranking
- **routing proxy** — Transparent invoke forwarding with opt-in fee
- **schema validator** — Rejects invalid manifests
- **trust scorer** — Aggregates reputation events
- **CLI** — `aimarket search`, `aimarket invoke`, `aimarket crawl`
- **Docker image** — Single-command deployment

---

## 10. References

- [Ecosystem architecture map](ecosystem.md) — Mermaid topology (Factory · Hub · Mesh · clients · chain)
- [Protocol v1](../docs/ai-market-protocol-v1.md) — Single-marketplace baseline
- [JSON Schema Core](https://json-schema.org/draft/2020-12/json-schema-core.html)
- [Ed25519](https://datatracker.ietf.org/doc/html/rfc8032)
- [HTTP 402](https://datatracker.ietf.org/doc/html/rfc7231#section-6.5.2)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Coinbase x402](https://docs.cdp.coinbase.com/x402/)

---

## Appendix A. Migration from v1 to v2

1. Add `hub_version: "2.0.0"` to `.well-known/ai-market.json`
2. Add `federation` and `peers` blocks to `.well-known`
3. Implement crawl loop (can start as no-op)
4. Register in at least one other hub's seed list
5. Optional: deploy routing proxy for incoming federated invocations

## Appendix B. Test Vectors

See [test-vectors/](test-vectors/) for reference Ed25519 signatures and manifest examples for implementor verification.
