# AIMarket Hub — User Guide

## What is AIMarket Hub?

AIMarket Hub is a **federation server** for AI capabilities. It discovers, indexes, and routes AI capability invocations across a network of hubs. Think "Google for AI marketplaces" — any hub can crawl any other hub's catalog, and users can invoke capabilities from any hub transparently.

## Quick Start

### 1. Install

```bash
cd aimarket-hub
pip install -e .
```

### 2. Start the hub

```bash
aimarket serve
# → Hub running on http://localhost:9080
```

Verify:
```bash
curl http://localhost:9080/.well-known/ai-market.json
```

### 3. Crawl other hubs

Set seed URLs in `.env`:
```bash
AIMARKET_SEED_LIST=https://hub2.example.com/.well-known/ai-market.json,https://hub3.example.com/.well-known/ai-market.json
```

Run a crawl:
```bash
aimarket crawl
# → Discovers and indexes capabilities from all seed hubs
```

### 4. Search the federated catalog

```bash
aimarket search "translate to 5 languages"
aimarket search "legal review" --limit 5 --json
```

### 5. Invoke a capability

```bash
aimarket invoke prod-xxx/translate.multi@v2 --input '{"text":"hello"}'
```

## Docker Deployment

```bash
docker build -t aimarket-hub .
docker run -p 9080:9080 \
  -e AIMARKET_HUB_NAME="My Hub" \
  -e AIMARKET_HUB_URL="https://my-hub.example.com" \
  -e AIMARKET_SEED_LIST="https://hub.modelmarket.dev/.well-known/ai-market.json" \
  -v hub_data:/app/data \
  aimarket-hub
```

Or with docker-compose:
```bash
docker-compose up -d
```

## Embedding the Widget

Add this to any HTML page:

```html
<script src="https://cdn.modelmarket.dev/widget.js"
        data-theme="cyber"
        data-intent="translate to 5 languages"
        data-budget="3.00"
        data-hub-url="https://hub.modelmarket.dev"
        data-affiliate-id="my_blog"></script>
```

**Themes:** `cyber`, `neon`, `light`, `paper`, `midnight`, `ocean`

**Affiliate:** Set `data-affiliate-id` to earn 30% of spend from widget invocations on your site.

## API Overview

### Discovery
```bash
GET /.well-known/ai-market.json           # Root manifest
GET /ai-market/v2/manifest                # Federated catalog
```

### Search & Invoke
```bash
GET /ai-market/v2/search?intent=...&budget=3.00
POST /ai-market/v2/invoke                # Federated invocation
```

### Federation
```bash
POST /ai-market/v2/federation/announce   # Peer announcement
GET /ai-market/v2/federation/peers        # Known peers
POST /ai-market/v2/federation/crawl       # Trigger crawl
```

### Reputation & Safety
```bash
GET /ai-market/v2/reputation/{hub_url}    # Trust score
POST /ai-market/v2/reputation/events      # Submit attestations
```

### Live Feed
```bash
GET /ai-market/v2/stats/live              # Real-time invocation stream
```

## Safety Gate

Every invocation passes through the safety gate:
1. **Pre-invoke**: checks for injection, PII, medical data, harassment
2. **Post-response**: checks output for PII leakage, harmful content
3. **On block**: atomic abort + channel refund + signed rejection receipt

The rejection receipt proves the invocation was blocked for safety reasons — liability shield for both provider and consumer.

### Configuring Safety Categories

```python
from aimarket_hub.safety_gate import make_constitutional_contract, SafetyGate

gate = SafetyGate(constitutional_contract=make_constitutional_contract(
    block_pii=True,
    block_medical=True,
    block_children=True,
    block_illegal=True,
    max_input_length=50_000,
))
```

## Federation Architecture

```
AI-Factory (local)                    Hub 2 (remote)
┌──────────────────────┐             ┌──────────────────┐
│ pipeline.json        │             │ .well-known      │
│   ↓                  │    crawl    │   ↓              │
│ hub (embedded) ◄─────┼─────────────┼── capabilities   │
│   ↓                  │    index    │                  │
│ federated catalog ───┼─────────────┼──► search        │
│   ↓                  │    route    │                  │
│ storefront ◄─────────┼─────────────┼── invoke         │
└──────────────────────┘             └──────────────────┘
```

## Anonymized Dataset Export

Weekly export of invocation data for research:

```bash
python -c "
from aimarket_hub.database import HubDatabase
from aimarket_hub.dataset_exporter import export_dataset
db = HubDatabase()
export_dataset(db)
"
# → data/datasets/ai-market-corpus-week-21.jsonl
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `AIMARKET_HUB_NAME` | AIMarket Hub | Display name |
| `AIMARKET_HUB_URL` | http://localhost:9080 | Public URL |
| `AIMARKET_DB_PATH` | data/hub.db | SQLite database |
| `AIMARKET_SEED_LIST` | (empty) | Comma-separated seed URLs |
| `AIMARKET_CRAWL_INTERVAL_S` | 3600 | Crawl interval (seconds) |
| `AIMARKET_ROUTING_FEE_BPS` | 100 | Routing fee (basis points) |
| `AIMARKET_MIN_TRUST_SCORE` | 0.3 | Minimum trust threshold |
| `AIMARKET_MAX_CRAWL_DEPTH` | 3 | Maximum BFS crawl depth |
| `AIMARKET_SIGNING_KEY_PATH` | data/hub_signing_key | Ed25519 key file |
| `AIMARKET_REQUEST_TIMEOUT_S` | 30 | HTTP request timeout |
