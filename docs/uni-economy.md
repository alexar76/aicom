# UNI Mode: Self-Evolving Universe Economy

## Overview

**UNI** (Universe) mode is a self-evolving economic simulation that runs on **real infrastructure**. Unlike TEST mode (pure fake metrics), UNI mode:

- Deploys a local Anvil EVM chain with real smart contracts (FakeUSDT, Escrow, NFT)
- Polls live Hub, Mesh, Factory, and Prometheus endpoints
- Executes real API calls for purchases, channel operations, and federation
- Only the **external funding source** is synthetic

**From inside the system, entities cannot tell it's a simulation.** Transactions are real on-chain events, payment channels use the real ChannelLedger, and purchases go through the real Hub API. The only hint of external origin is the periodic funding injection — visualized as cosmic energy streams in the 3D monitor.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 VirtualUniverse                     │
│  ┌───────────────┐  ┌─────────────────────────────┐ │
│  │ Anvil Chain   │  │   UniverseScenarioEngine     │ │
│  │ (port 8545)   │  │                              │ │
│  │               │  │  ┌───────────────────────┐   │ │
│  │ FakeUSDT      │  │  │  ExternalAIBuyer      │   │ │
│  │ Escrow        │──┤  │  (real Hub API calls) │   │ │
│  │ NFT           │  │  └───────────────────────┘   │ │
│  └───────────────┘  │                              │ │
│                     │  ┌───────────────────────┐   │ │
│  ┌───────────────┐  │  │  UniverseFunding      │   │ │
│  │ Layer Polling  │  │  │  Stream (synthetic)   │   │ │
│  │ Hub  :9083    │──┤  └───────────────────────┘   │ │
│  │ Mesh :8090    │  │                              │ │
│  │ App  :9081    │  │  ┌───────────────────────┐   │ │
│  │ Prom :9090    │  │  │  HubSpawner            │   │ │
│  └───────────────┘  │  │  (federation announce) │   │ │
│                     │  └───────────────────────┘   │ │
│                     └─────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
                          │
                          ▼ WebSocket (1.5s ticks)
┌─────────────────────────────────────────────────────┐
│              Alien Monitor Frontend                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ PhaseRing│ │ Funding  │ │ Scenario Metrics │    │
│  │ (3D)     │ │ Stream   │ │ Panel            │    │
│  └──────────┘ └──────────┘ └──────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## Evolution Phases

### BOOTSTRAP
**Duration**: ~40 ticks (~60 seconds at 1.5s/tick)
**Conditions to advance**: >= 40 ticks, >= 3 products created

The universe is born. Hub is seeded with initial capabilities. First factory products begin materializing as planets in the 3D view. No external activity yet — the ecosystem is being established.

### EXPANSION
**Duration**: ~110 ticks (~165 seconds)
**Conditions to advance**: >= 150 ticks total, >= 20 buyer invocations, >= $200 total funding

The economy activates. External AI buyer begins purchasing capabilities every 8 ticks. Funding stream injects 100-200 USDT every 200 ticks. Products accumulate purchase history and revenue. ACEX pricing begins to reflect invocation stats.

**Buyer behavior in EXPANSION**:
- Budget: $80–200 per round
- 3–6 purchases per round
- Diversity-aware: prefers categories not yet purchased
- Scoring: `(1/price) × trust_score × diversity_bonus`

### FEDERATION
**Duration**: ~200 ticks (~300 seconds)
**Conditions to advance**: >= 350 ticks total, >= 3 federated hubs, >= $1,000 total funding

New hubs spawn every 300 ticks via the federation announce endpoint. Each hub brings 3+ capabilities with distinct themes (security, infrastructure, finance, etc.). Inter-hub commerce begins. Federation BFS crawler discovers peers.

### MATURITY
Steady-state. Funding, purchasing, and hub spawning continue on stable intervals. The economy self-regulates: successful products accumulate value through ACEX CapShares, underperforming products are naturally selected out by buyer preferences.

---

## Components

### External AI Buyer (`universe_external_buyer.py`)

Autonomous agent that creates real demand by purchasing from the Hub API:

1. **Search**: `GET /ai-market/v2/search?intent=...&budget=...&limit=12`
2. **Select**: Score-based ranking with category diversity preference
3. **Channel**: `POST /ai-market/v2/channel/open` with deposit
4. **Invoke**: `POST /ai-market/v2/invoke` with `X-Payment-Channel` header
5. **Close**: `POST /ai-market/v2/channel/close` for settlement

**Selection categories**: translate, code, data, content, security, marketing, legal, finance, agent, infra

**Diversity mechanism**: After purchasing from a category, subsequent rounds get a 1.5× bonus for unexplored categories. This ensures demand spreads across the entire capability catalog.

### Universe Funding Stream (`universe_funding.py`)

The ONLY synthetic element. Periodic capital injection:

| Parameter | EXPANSION | FEDERATION+ |
|-----------|-----------|-------------|
| Interval | 200 ticks (~5min) | 150 ticks (~3.75min) |
| Amount | $100–200 | $100–200 × multiplier |
| On-chain | FakeUSDT transfer to escrow | Same |

Funding grows with the universe — the multiplier increases as hubs and products accumulate. Visualized as golden particle beams flowing from outside the visible scene toward the hub.

#### Hub liquidity (must stay true in UNI)

External funding is the **only** synthetic capital. It must keep the **Hub usable**, not only fill escrow:

| Layer | Mechanism | Config |
|-------|-----------|--------|
| On-chain | FakeUSDT `transfer` → escrow (default) or Hub payment address | `ALIEN_UNIVERSE_FUNDING_TARGET=escrow\|hub` |
| Factory UNI bus | `POST /api/uni/grant` — ecosystem float | `AIFACTORY_UNI_GRANT_SECRET` **required** |
| Hub treasury wallet | `universe:hub-treasury` bootstrap grant | `ALIEN_UNIVERSE_HUB_LIQUIDITY_GRANT_USD` (default 500) |
| External buyer wallet | `universe:external-buyer` bootstrap grant | `ALIEN_UNIVERSE_BUYER_LIQUIDITY_GRANT_USD` (default 300) |
| Periodic injections | Same rules as table above; interval/amount from env | `ALIEN_UNIVERSE_FUNDING_*` |
| Growth multiplier | Rises with product + federated hub count | `update_growth_multiplier()` each EXPANSION+ tick |

**Phase gates still require external funding totals** (e.g. ≥ $200 to leave EXPANSION). Buyer rounds use **real** Hub `channel/open` → `invoke` → `close`; bootstrap grants prevent empty ledger at first EXPANSION tick.

Initial EXPANSION injection: `ALIEN_UNIVERSE_INITIAL_FUNDING_USD` (optional, default off) fires once when phase becomes EXPANSION.

### Hub Spawner (`universe_hub_spawner.py`)

Creates new federated hubs:

1. Selects unused name from pool (Hydra Node, Nexus Prime, Quantum Bridge, etc.)
2. Assigns 3+ themed capabilities
3. Registers via `POST /ai-market/v2/federation/announce`
4. Creates `EcosystemEntity` node in 3D graph

**Hub themes**:
| Hub | Theme | Example Capabilities |
|-----|-------|---------------------|
| Hydra Node | Infrastructure | GPU rendering, ML inference, ETL |
| Nexus Prime | Finance | Market analysis, sentiment, trends |
| Quantum Bridge | Crypto | ZK verifier, quantum sim, entropy |
| Stellar Gate | Web3 | NFT mint, DAO proposals, swaps |
| Void Forge | Security | Contract audit, vuln scanner, gas opt |

---

## Economy Rules

1. **All prices in test USDT** — FakeUSDT contract on local Anvil (chain ID 31337)
2. **External buyer uses real Hub API** — no simulation of purchase flow
3. **Funding enters only via external source** — marked in transaction log with `source: "external"`
4. **Value accumulates through purchase history** — invocation stats drive ACEX pricing
5. **Hub federation uses real BFS crawl** — new hubs appear in peer list
6. **Products auto-list when pipeline completes** — `auto_listing.py` registers them as hub capabilities
7. **Plugin economy activates** — safety gate, reputation, channels, streaming all process real invocations
8. **NO mocks in UNI mode** — the `EcosystemSimulator` class (TEST mode only) is never used

---

## 3D Visualization

| Element | Represents |
|---------|-----------|
| Golden particle beams → hub | External funding stream |
| Rotating phase ring (colored) | Current evolution phase + progress |
| New globe nodes appearing | Federated hub spawn |
| Phase color in mode indicator | BOOTSTRAP=blue, EXPANSION=green, FEDERATION=magenta, MATURITY=gold |
| Transaction stream "EXTERNAL" entries | Funding events (golden highlight) |
| Metrics panel phase/funding/hubs | Scenario state |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/universe/start` | Start UNI: chain, contracts, entities, scenario engine |
| `GET /api/universe/status` | Runtime status + scenario phase/meta |
| `GET /api/universe/scenario` | Full scenario engine state |
| `GET /api/universe/funding/history` | All funding rounds |
| `GET /api/universe/state` | Full ecosystem snapshot (nodes, links, events, scenario) |
| `POST /api/universe/materialize` | Factory webhook — product → planet |
| `POST /api/universe/stop` | Stop UNI runtime |

---

## Verification

### Automated checks
1. `POST /api/universe/start` → verify `blockchain_ready: true`, `entities > 0`
2. After ~45 ticks → verify phase transitions to `EXPANSION`
3. `GET /api/universe/scenario` → check `buyer_rounds > 0`, `funding_total > 0`
4. `GET /api/universe/funding/history` → verify funding rounds exist
5. After ~350 ticks → verify `hub_count >= 3`

### Manual verification
1. Start the stack: `./alien-monitor/start.sh --universe`
2. Open `http://localhost:5173`
3. Observe 3D view:
   - Phase ring around hub (colored, animated)
   - Funding stream particles (golden, flowing toward hub)
   - New hub nodes appearing after ~5 minutes
4. Check Activity Stream for:
   - ExternalAI purchase entries
   - "EXTERNAL → ecosystem funding" golden entries
5. Metrics panel shows:
   - PHASE: EXPANSION/FEDERATION
   - FUNDING: $NNN
   - BUYER RND: N
   - HUBS: N
   - Phase progress bar (%)

### TEST mode regression
Switch to TEST mode — verify `EcosystemSimulator` produces same fake data as before, no scenario data visible.

---

## Production Docker (UNI with real deploy)

Alien Monitor prod image (`alien-monitor/docker-compose.prod.yml`) defaults to `ALIEN_MODE=universe` and auto-bootstraps Anvil + contract deploy on startup. State persists under `data/alien-monitor/universe/`.

**Troubleshooting:** [uni-troubleshooting.md](./uni-troubleshooting.md) — typical problems (`blockchain_ready: false`, forge failures, Hub not wired, Ganache vs Anvil, etc.).
