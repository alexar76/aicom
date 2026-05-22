# AIMarket Hub v2.0.0

**License:** Apache-2.0  
**Status:** Reference implementation of [AIMarket Protocol v2](../aimarket-protocol/spec.md)

Federation hub for AI capability discovery, indexing, search, and routing.

## Quick Start

```bash
# Install
pip install -e .

# Start the hub server
aimarket serve

# Or with Docker
docker build -t aimarket-hub .
docker run -p 9080:9080 aimarket-hub
```

## Components

| Component | Description |
|-----------|-------------|
| **crawler** | BFS daemon reading `.well-known/ai-market.json` from seed list + discovered URLs |
| **indexer** | SQLite-backed storage for manifests, schemas, prices, reputation events |
| **search API** | `/ai-market/v2/search?intent=...&budget=...` with trust ranking |
| **routing proxy** | `/ai-market/v2/invoke` forwards to provider hub with opt-in commission |
| **schema validator** | JSON Schema validation rejects invalid manifests |
| **trust scorer** | Aggregates age, bond, success rate, and volume into trust score |
| **safety gate** | Pre-invoke safety classifier → atomic abort + refund if flagged |
| **CLI** | `aimarket search`, `aimarket invoke`, `aimarket crawl`, `aimarket peers` |

## CLI

```bash
aimarket serve                    # Start API server
aimarket crawl                    # Run federation crawl
aimarket search "translate"       # Search capabilities
aimarket invoke prod-xxx/translate.multi@v2 --input '{"text":"hello"}'
aimarket peers                    # List known peers
aimarket stats                    # Hub statistics
aimarket trust https://hub2.example.com  # Trust score
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/ai-market.json` | Root discovery |
| GET | `/ai-market/v2/manifest` | Federated catalog |
| GET | `/ai-market/v2/search` | NL search |
| POST | `/ai-market/v2/invoke` | Federated invoke |
| POST | `/ai-market/v2/federation/announce` | Peer announcement |
| GET | `/ai-market/v2/federation/peers` | Known peers |
| POST | `/ai-market/v2/federation/crawl` | Trigger crawl |
| GET | `/ai-market/v2/reputation/{hub_url}` | Trust score |
| POST | `/ai-market/v2/reputation/events` | Submit reputation |
| GET | `/ai-market/v2/stats/live` | Live invocation feed |

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `AIMARKET_HUB_NAME` | `AIMarket Hub` | Hub name |
| `AIMARKET_HUB_URL` | `http://localhost:9080` | Public URL |
| `AIMARKET_DB_PATH` | `data/hub.db` | SQLite path |
| `AIMARKET_SEED_LIST` | (empty) | Comma-separated seed URLs |
| `AIMARKET_CRAWL_INTERVAL_S` | `3600` | Crawl interval |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | Routing fee (1%) |
| `AIMARKET_MIN_TRUST_SCORE` | `0.3` | Minimum trust to list |
| `AIMARKET_MAX_CRAWL_DEPTH` | `3` | BFS crawl depth |
| `AIMARKET_SIGNING_KEY_PATH` | `data/hub_signing_key` | Ed25519 key |
