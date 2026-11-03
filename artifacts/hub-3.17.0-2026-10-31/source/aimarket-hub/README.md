# AIMarket Hub

<!-- aicom-readme-badges -->
<p align="center">
  <a href="https://github.com/alexar76/aimarket-hub/actions/workflows/ci.yml"><img src="https://github.com/alexar76/aimarket-hub/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/alexar76/aimarket-hub/releases"><img src="https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/badges/release.svg" alt="Release" /></a>
  <a href="https://github.com/alexar76/aimarket-protocol"><img src="https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/badges/aimarket.svg" alt="Protocol" /></a>
  <a href="https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/badges/coverage.svg"><img src="https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/badges/coverage.svg" alt="Test coverage" /></a>
  <a href="https://github.com/alexar76/aimarket-hub/blob/main/LICENSE"><img src="https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/badges/license.svg" alt="License: Apache-2.0" /></a>
</p>
<!-- /aicom-readme-badges -->

> 🌐 **English** · [Русский](docs/README.ru.md) · [Español](docs/README.es.md) · [Français](docs/README.fr.md) · [中文](docs/README.zh.md) · [Glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

**Connect an agent through MCP or A2A, find a capability, pay for execution, and verify its signed receipt.**

AIMarket Hub integrates MCP tool calls and A2A agent requests with federated discovery, payment controls, and signed receipts. Oracle capabilities use the same marketplace. Receipt verification authenticates the signed record; it does not establish the truth or quality of the answer.

| Start here | Connect | First call |
|---|---|---|
| MCP client | `https://modelmarket.dev/mcp` | `market_search` → `market_invoke`, preserving `source_hub`. |
| A2A agent | `/.well-known/agent-card.json` → `/a2a` | Search → invoke with a price cap → inspect the Task → verify the receipt. |

**[Step-by-step guide and runnable example](docs/agent-first-call.md)**

Both routes use the hub’s invoke and payment controls. Use an available free trial, or pay through credits, a mandate, or the supported x402 flow.

<!-- pay-on-verified-notice -->
> **Agents can already pay each other. We make it possible for them to trust each other.**
>
> ⚠️ **Pay-on-Verified — read before relying on it.** A buyer can make payment conditional on an independent verdict: the hub holds the price and pays the seller only if the delivery passes; a failing delivery is refunded. The verdict comes from an LLM jury (Metis) judging the delivery against the intent the buyer wrote — evidence, not proof. It works only on escrow-backed payment channels, for capabilities the hub executes itself, from $0.05.
> → [What it does not promise](https://github.com/alexar76/aicom/blob/main/docs/pay-on-verified-enable.md#disclaimer) · [How to enable it](https://github.com/alexar76/aicom/blob/main/docs/pay-on-verified-enable.md#enable) · [A run on real money](https://github.com/alexar76/aicom/blob/main/docs/pay-on-verified-demo.md)
<!-- /pay-on-verified-notice -->










> ### 🟢 Just want to try the marketplace? Install nothing.
> Paste **`https://modelmarket.dev/mcp`** into Cursor, Claude, or any Streamable-HTTP MCP client.
> Start with two tools, **`market_search`** + **`market_invoke`** (the endpoint's `tools/list` has more: status, receipts, channels). A few trial invokes per caller, then **429 `trial_quota_exhausted`** until the window renews; each invoke returns a signed receipt.
> Pass **`source_hub`** from search back into invoke — most of the catalogue is federated, and omitting it 404s.
> Live trial size: `free_trial.max_invokes_per_visitor` in [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).
> → [`docs/hosted-mcp-endpoint.md`](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md)

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp"
    }
  }
}
```

Cursor: `.cursor/mcp.json`. Claude Desktop: `claude_desktop_config.json`. Same shape. Agent skill (no clone): [`docs/agent-install`](https://github.com/alexar76/aicom/blob/main/docs/agent-install/README.md).

> ### 🛠 Run your own hub
> ```bash
> pip install "aimarket-hub[pqc]"     # Python 3.11+, or: uvx --from "aimarket-hub[pqc]" aimarket …
> aimarket quickstart --name "My hub" && aimarket serve
> ```
> Then `aimarket add` lists your own API (buyers pay your wallet directly), `aimarket doctor` runs the
> admission check other hubs will run on you, and one `curl` knocks on the federation. Docker:
> `docker compose run --rm hub quickstart` then `docker compose up -d`; Railway, Render and Fly files are included.
> Paid computation through an oracle: [configure per-oracle paid-tier credentials](docs/oracle-paid-tier.md).
> → [Run your own hub](docs/operator-quickstart.md) · [on a platform](docs/run-on-a-platform.md)
> Already run an API? `aimarket node` makes it a node without a hub → [run a node](docs/run-a-node.md).
> No server at all? Sell a Python function on HESTIA → [sell without a server](https://github.com/alexar76/hestia/blob/main/docs/sell-without-a-server.md).

> **Ecosystem:** [AICOM overview & live demos](https://ecosystem.modelmarket.dev/) · **Package:** [aimarket-hub on PyPI](https://pypi.org/project/aimarket-hub/) · **Community:** [Discord · Pollux](https://discord.gg/JjWxGhW9pP) · [Telegram · Castor](https://t.me/just_for_agents)

**Federation hub for AI capability discovery, micropayment routing, and plugin-extensible invoke.**

Reference implementation of [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md). One HTTP surface to **search** a federated catalog, **open payment channels**, **invoke** capabilities with safety and compliance hooks, and **settle** on-chain — with custody depending on the selected payment rail.

| | |
|---|---|
| **Live hub** | [modelmarket.dev](https://modelmarket.dev) |
| **MCP** | [`https://modelmarket.dev/mcp`](https://modelmarket.dev/mcp) |
| **A2A** | [Agent Card and A2A guide](docs/a2a.md) · [Agent Card](https://modelmarket.dev/.well-known/agent-card.json) |
| **Agent skill** | [docs/agent-install](https://github.com/alexar76/aicom/blob/main/docs/agent-install/README.md) |
| **Well-known** | [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json) |
| **Plugin demo** | [/plugins/demo](https://modelmarket.dev/plugins/demo) |
| **Widget demo** | [/widget/demo](https://modelmarket.dev/widget/demo) |
| **Plain-language value** | [docs/value.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/value.md) |

> **[Codex subcontracting case study](docs/case-study-codex-subcontract.md)** — A real order from Codex: two GAIA calls, 0.002 USDC on Base, signed receipts and ≈ $0.00477 total including gas.

> **[One-call pipelines](docs/one-call-pipelines.md)** · **[New live test from Codex](docs/case-study-codex-one-call.md)** — 2026-09-30.

## Demo

- **Live:** https://modelmarket.dev/
- **Docs:** https://github.com/alexar76/aimarket-hub/blob/main/README.md

---

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Core API](#core-api)
- [Invoke lifecycle](#invoke-lifecycle)
- [Plugin ecosystem](#plugin-ecosystem)
- [Federation](#federation)
- [Payments](#payments)
- [Pay-on-Verified](#pay-on-verified)
- [Agent mandates and subcontracting](#agent-mandates-and-subcontracting)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Development](#development)
- [Security](#security)
- [Related projects](#related-projects)
- [License](#license)

---

## Overview

AIMarket Hub sits between **capability providers** (factory-shipped products, [**oracles**](https://github.com/alexar76/oracles), peer hubs, data-cap publishers) and **consumers** (Flutter desktop apps, agents, embeddable widgets, MCP clients).

**Problems it solves**

| Problem | Hub answer |
|---------|------------|
| Fragmented AI APIs | Federated search over `.well-known/ai-market.json` peers |
| Per-call payment friction | Pre-funded **channels** — one deposit, N micro-invokes, one settlement |
| Trust in anonymous sellers | **Reputation** scores + stake bonds (plugin) |
| Compliance & audit | **Provenance** receipts on every invoke (Ed25519 + W3C VC) |
| Unsafe prompts | **Safety** pre-check with signed rejection + refund |


### Zero-Trust Agent Discovery

**No human app-store reviewer.** Agents **find peers over federation, pass safety + attestation gates, and invoke only verified capabilities** — cryptographic trust replaces marketing trust.

| | |
|---|---|
| **What** | Federated `discover` → safety / reputation / TEE plugins → routed invoke |
| **Why** | Scales to millions of micro-capabilities; malicious listings can’t drain channels |
| **Deep dive** | [docs/killer-feature-zero-trust-discovery.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/killer-feature-zero-trust-discovery.md) · [Ecosystem capabilities](https://github.com/alexar76/aicom/blob/main/docs/killer-features.md) |

---

## Architecture

### System context

```mermaid
C4Context
  title AIMarket Hub — system context

  Person(consumer, "Consumer", "App, agent, or widget user")
  Person(provider, "Provider", "Lists capabilities on a hub")

  System(hub, "AIMarket Hub", "Search, route, invoke, settle")
  System_Ext(peers, "Peer hubs", "Federated catalogs")
  System_Ext(factory, "AI-Factory", "Shipped products → capabilities")
  System_Ext(chain, "Base L2", "USDT channels")

  Rel(consumer, hub, "discover · channel · invoke")
  Rel(provider, hub, "manifest · capabilities")
  Rel(hub, peers, "crawl · route")
  Rel(hub, factory, "import shipped products")
  Rel(hub, chain, "open/close channel")
```

### Container diagram (this repository)

```mermaid
flowchart TB
  subgraph hub_process["aimarket_hub (FastAPI)"]
    API["api.py — REST /ai-market/v2/*"]
    CRW["crawler.py — BFS federation"]
    DB["database.py — capability index"]
    CH["channels.py — ledger + settle"]
    SG["safety_gate.py"]
    PR["plugin.py — PluginRegistry"]
    FB["factory_bridge.py"]
    SIG["signing.py — Ed25519 manifests"]
  end

  subgraph plugins["plugins/ (entry_points)"]
    P1["safety · provenance · channels …"]
  end

  subgraph storage["Persistence"]
    SQL[("SQLite / PostgreSQL")]
  end

  API --> CRW
  API --> DB
  API --> CH
  API --> SG
  API --> PR
  API --> FB
  CRW --> DB
  FB --> DB
  DB --> SQL
  PR --> P1
  P1 -.->|"pre/post hooks"| API
```

### Factory import path

Shipped AI-Factory products are indexed as local capabilities on hub startup:

```mermaid
sequenceDiagram
  participant Factory as AI-Factory pipeline.db
  participant Loader as factory_products_loader
  participant Bridge as factory_bridge
  participant Index as database (SQLite)

  Note over Factory,Index: On hub startup or sync script
  Factory->>Loader: COMPLETED / DEPLOYED products
  Loader->>Bridge: normalize capabilities
  Bridge->>Index: upsert source_hub=local
  Index-->>Bridge: indexed count
```

Sync ops: [`../scripts/sync_pipeline_mirror_and_hub.py`](https://github.com/alexar76/aicom/blob/main/scripts/sync_pipeline_mirror_and_hub.py)

---

## Repository layout

```
aimarket-hub/
├── aimarket_hub/           # Core package
│   ├── api.py              # HTTP routes (search, invoke, federation, plugins)
│   ├── crawler.py          # Peer discovery (SSRF-hardened BFS)
│   ├── database.py         # Capability + peer index
│   ├── channels.py         # Payment channel ledger
│   ├── plugin.py           # setuptools aimarket.plugins loader
│   ├── factory_bridge.py   # AI-Factory product import
│   ├── safety_gate.py      # Built-in safety fallback
│   └── …
├── plugins/                # Hub-local plugins (e.g. aimarket-provenance)
├── tests/                  # pytest suite
├── Dockerfile
├── LICENSE                 # Apache-2.0
├── CONTRIBUTORS.md
├── SECURITY.md
└── docs/
    └── value.md
```

**Sibling packages** (monorepo root [`plugins/`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/)): 15 plugins — **top-5 on PyPI** ([install guide](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/docs/install.md)); full set bundled in Docker.

---

## Quick start

### Prerequisites

- Python **3.11+**
- Optional: Docker for container deploy

### Install & run

```bash
# the post-quantum verifier is a core dependency since 3.15.18 (without it the Hub cannot index
# peers that sign hybrid); [pqc] stays valid and keeps older versions right
pip install "aimarket-hub[pqc]"
# optional core plugins (TEE, channels, reputation, safety, MCP packager):
pip install "aimarket-hub[plugins]"
# production Hub with PostgreSQL, payer-proof/escrow crypto and ML-DSA-65:
pip install "aimarket-hub[postgres,escrow,pqc]"
# sign hybrid (Ed25519 + ML-DSA-65); back up <key>_mldsa together with the Ed25519 key
export AIMARKET_PQC=1
aimarket serve
# → http://localhost:9083
```

Taking money from the first day: [Running this hub for yourself](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md)

For a local MCP client or Glama, use `python -m aimarket_hub mcp --init`.
This serves the local hub's tools over stdio without opening an HTTP port; logs go to
stderr. The usual hub settings apply. See [Glama build settings](docs/GLAMA.md) for the
exact build and launch commands.
(`python -m aimarket_hub quickstart` also reports how the Hub signs and where its keys are).

Verify discovery and search:

```bash
curl -s http://localhost:9083/.well-known/ai-market.json | jq .
curl -s "http://localhost:9083/ai-market/v2/search?intent=translate&budget=1" | jq .
curl -s http://localhost:9083/ai-market/v2/plugins | jq '.plugins | length'
```

### Publish a capability (community providers)

Third-party developers list an HTTP endpoint in the catalog and earn USDC when agents invoke it. **Production hubs** require stake, LUMEN trust scoring, and Ed25519-signed provider responses — see [`docs/supply-security.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/supply-security.md).

```bash
cd examples/hello-capability && python3 server.py   # terminal 1 — prints provider_pubkey
export AIMARKET_ALLOW_LOCAL_PUBLISH=1               # dev only
# production: POST /ai-market/v2/supply/stake first, with your own credential and a
# tx_hash for EVERY positive amount — the deposit is verified on-chain and single-use,
# whatever its size, so sub-minimum drip-feeding cannot reach the stake gate.
aimarket publish capability.json --hub http://127.0.0.1:9083
aimarket invoke demo-hello/greet@v1 --input '{"name":"dev"}'
```

Full walkthrough (20 languages): [ARGUS developer guide](https://github.com/alexar76/argus/tree/main/docs/developer-guide/) · [supply security](https://github.com/alexar76/aimarket-hub/blob/main/docs/supply-security.md) · example in [`examples/hello-capability/`](https://github.com/alexar76/aimarket-hub/tree/main/examples/hello-capability).

### Docker

**Production (this monorepo):** always redeploy Hub from repo root:

```bash
./scripts/deploy_hub.sh
# or full fleet: ./scripts/deploy_ecosystem.sh
```

See [`docs/deploy-ecosystem.md`](https://github.com/alexar76/aicom/blob/main/docs/deploy-ecosystem.md). Do **not** use `cd aimarket-hub && docker compose up` for production redeploy (wrong build context).

**Recovery** (factory hold, backup/restore, fleet redeploy): [`docs/recovery-mechanisms.md`](https://github.com/alexar76/aicom/blob/main/docs/recovery-mechanisms.md) in the factory monorepo.

Manual build (same as deploy script):

```bash
docker build -f aimarket-hub/Dockerfile -t modelmarket-hub .
docker run -p 9083:9083 \
  -e AIMARKET_HUB_NAME="My Hub" \
  -e AIMARKET_HUB_URL="https://my-hub.example.com" \
  -e AIMARKET_PAYMENT_RECIPIENT="0xYourWallet" \
  modelmarket-hub
```

---

## Core API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/.well-known/ai-market.json` | Root discovery — chain, token, peers, signer key |
| `GET` | `/.well-known/mcp/server-card.json` | MCP server card (SEP-1649 / Smithery fallback) |
| `GET` | `/llms.txt` | Short agent-readable Hub + MCP door |
| `GET` / `POST` | `/mcp` | Hosted MCP — GET info; POST Streamable-HTTP (`market_search`, `market_invoke`) |
| `GET` | `/.well-known/agent-card.json` | A2A 1.0 Agent Card (cacheable + ETag) |
| `POST` | `/a2a` | A2A 1.0 JSON-RPC: marketplace search, paid invoke as Tasks, `GetTask`/`ListTasks`/`CancelTask` ([docs/a2a.md](docs/a2a.md)) |
| `GET` | `/ai-market/v2/manifest` | Hybrid Ed25519 + ML-DSA-65 capability catalog when PQC is enabled |
| `GET` | `/ai-market/v2/search` | NL federated search (`intent`, `budget`, `category`) |
| `POST` | `/ai-market/v2/supply/stake` | Deposit publisher stake (unlock community publish) |
| `POST` | `/ai-market/v2/supply/register` | Publish community capability + `invoke_url` |
| `POST` | `/ai-market/v2/invoke` | Invoke capability (plugin hooks, safety gate) |
| `POST` | `/ai-market/v2/receipts/verify` | Verify a receipt against this Hub's pinned live Ed25519 + ML-DSA-65 identities |
| `POST` | `/ai-market/v2/channel/open` | Open pre-funded payment channel |
| `POST` | `/ai-market/v2/channel/close` | Close channel — record settlement and refund owed |
| `POST` | `/ai-market/v2/federation/announce` | Peer hub announcement |
| `GET` | `/ai-market/v2/federation/peers` | Known peers + trust scores + pin status (`key_mismatch`) |
| `GET` | `/ai-market/v2/federation/assay` | Last sandbox scorecard (`pass` auto-admits by default) |
| `POST` | `/ai-market/v2/federation/assay` | Admin: re-run SSRF / signature / sandbox assay |
| `POST` | `/ai-market/v2/federation/crawl` | Trigger BFS crawl of seed peers |
| `POST` | `/ai-market/v2/federation/peers/approve` | Admin: toggle peer `trusted` (anti-TOFU) |
| `POST` | `/ai-market/v2/federation/peers/repin` | Admin: rotate a sticky peer pin after legitimate key change |
| `GET` | `/ai-market/v2/plugins` | Loaded plugin catalog |
| `GET` | `/ai-market/v2/reputation/{hub_url}` | Trust score breakdown |
| `GET` | `/ai-market/v2/stats/live` | Real-time invocation feed |

**Authorization.** Self-service publishers use their own `X-API-Key` on
`/ai-market/v2/supply/stake` and `/ai-market/v2/supply/register`, with `publisher_id`
equal to the `account_id` returned by `GET /ai-market/v2/account`. The credits flow moves
existing account funds into locked collateral; it does not mint free stake. An operator's
mandate policy may require additional authorization. Confirm the live policy before funding.
The non-credits flow requires the caller's own credential from `AIMARKET_PUBLISHER_TOKENS`
(or operator-only `AIMARKET_ADMIN_TOKEN`), plus verified settlement and payer proof for
production stake. A shared publish token cannot prove publisher identity and is not a
production onboarding credential. `/self-bond/slash` and settlement/federation routes are
admin-only. See [publication steps](https://play.modelmarket.dev/publish) and
[supply security](docs/supply-security.md).

OpenAPI: `/docs` (FastAPI's default — there is no `AIMARKET_OPENAPI` switch; put the hub behind
your proxy if the schema should not be public). Full spec: [`../aimarket-protocol/spec.md`](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md)

---

## Invoke lifecycle

Standard consumer flow (implemented by [`aimarket_agent`](https://github.com/alexar76/aimarket-sdks/tree/main/dart/)):

```mermaid
sequenceDiagram
  autonumber
  participant Client
  participant Hub as AIMarket Hub
  participant Plugins
  participant Target as Provider / local invoke

  Client->>Hub: search(intent, budget)
  Hub-->>Client: plan[]

  Client->>Hub: channel/open(deposit_usd)
  Hub-->>Client: channel_id

  Client->>Hub: invoke(capability_id, input, channel_id)
  Hub->>Plugins: on_invoke_pre_check
  alt rejected
    Plugins-->>Hub: signed rejection
    Hub-->>Client: 403 + channel refund
  else ok
    Hub->>Target: forward or local execute
    Target-->>Hub: output, price_usd
    Hub->>Plugins: on_invoke_post_check
    Hub-->>Client: result + provenance_receipt
  end

  Client->>Hub: channel/close(channel_id)
  Hub-->>Client: settlement + refund_owed_usd (no payout)
```

A call that arrives without the fields the capability needs is **incomplete input**, not a
provider miss and not a refusal. The tape keeps the row (`outcome=incomplete`, HTTP 400
`incomplete_input` naming the missing fields). `refused` is a policy decision (quota, plan,
block). Only `ok` and `fail` move `success_rate` on `/ai-market/v2/stats/live`, the SSR
ticker, and trust.

---

## Plugin ecosystem

Plugins register via **`aimarket.plugins`** entry points ([`plugin.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/plugin.py)). Each ships **README + docs/** (`value.md`, `user-guide.md`, `sdk-integration.md`, `user-cases.md`).

Regenerate docs: `python3 scripts/bootstrap_hub_plugin_docs.py` · value text: `python3 scripts/bootstrap_product_value.py`

```mermaid
flowchart LR
  INV["POST /invoke"] --> PRE["pre-check"]
  PRE --> S["aimarket-safety"]
  PRE --> Z["aimarket-zk"]
  PRE --> PR["aimarket-promo"]
  PRE --> RUN["Execute"]
  RUN --> POST["post-check"]
  POST --> PV["aimarket-provenance"]
  POST --> T["aimarket-tee"]
  POST --> R["aimarket-reputation"]
  POST --> OUT["Response"]
```

| Plugin | Category | One-line value |
|--------|----------|----------------|
| [`aimarket-provenance`](https://github.com/alexar76/aimarket-hub/tree/main/plugins/aimarket-provenance) | compliance | Cryptographic receipt per AI output |
| [`aimarket-safety`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-safety/) | security | Block jailbreak / injection before billing |
| [`aimarket-reputation`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-reputation/) | reputation | Stake-backed trust scores |
| [`aimarket-channels`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-channels/) | infrastructure | Off-chain ledger, on-chain settlement |
| [`aimarket-tee`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-tee/) | security | Hardware attestation (Nitro / TDX) |
| [`aimarket-auction`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-auction/) | monetization | Spot bidding for scarce slots |
| [`aimarket-personas`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-personas/) | tooling | Buyer-friendly agent personas |
| [`aimarket-streaming`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-streaming/) | monetization | SSE + per-token micro-billing |
| [`aimarket-nft`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-nft/) | monetization | Transferable prepaid credit NFTs |
| [`aimarket-mcp-packager`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-mcp-packager/) | tooling | MCP bundle for Claude Desktop |
| [`aimarket-orchestrator`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-orchestrator/) | monetization | NL task → capability chain planner |
| [`aimarket-data-cap`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-data-cap/) | monetization | Private corpus → paid search |
| [`aimarket-promo`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-promo/) | monetization | Signed time-locked discounts |
| [`aimarket-dataset`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-dataset/) | tooling | Weekly anonymized demand corpus |
| [`aimarket-zk`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/aimarket-zk/) | security | ZK proofs without revealing input |

---

## Federation

Hubs discover each other without a central registry:

```mermaid
flowchart TB
  SEED["AIMARKET_SEED_LIST<br/>.well-known URLs"] --> CRAWL["crawler.py BFS"]
  CRAWL --> MANIFEST["Fetch signed manifests"]
  MANIFEST --> INDEX["database.py"]
  INDEX --> SEARCH["Unified federated search"]

  HUB_A["Hub A"] <-->|announce / peers| HUB_B["Hub B"]
  CRAWL --> HUB_A
  CRAWL --> HUB_B

  INV["invoke to remote capability"] --> ROUTE["Route to peer hub"]
  ROUTE --> FEE["Optional routing_fee_bps"]
```

### Observation gossip — seeing every new Hub

Hub addresses are always accepted through two public observation doors, and both lead to
**quarantine**:

- `POST /federation/announce` accepts an unauthenticated announcement;
- a hub that crawls this one identifies itself with `X-AIMarket-Crawler` and is recorded
  from that alone — so an operator can finally see who reads them.

In both cases the peer lands `status=pending`, `trusted=false`. Its manifest is **not**
indexed and its capabilities are **not** searchable or routable. Its address is republished
in the signed `observed_hubs` section of this hub's `.well-known`, so trusted peers learn it
on later crawl cycles and Alien Monitor renders it as unapproved. With
`AIMARKET_FEDERATION_PREVIEW_CAPS=1` its manifest is
fetched and signature-verified into a separate preview table so the operator can see what
it offers before deciding — a table no search, routing or invoke path reads.

Observation changes who is visible. Trust is not granted on the knock: the peer
lands `pending`. A **sandbox assay** then runs in the background (and again on
crawl cycles). A `pass` auto-admits (`trusted` + crawl) so an operator is not
clicking Approve for every capability. Fail and review stay at `/operator`.

The assay scores the **live invoke**, never brochure text. Names and descriptions
are stripped before any model sees evidence. An optional LLM judge is **veto-only**
(`AIMARKET_FEDERATION_JUDGE_URL`) — it cannot mint a pass from marketing copy.
`AIMARKET_FEDERATION_ASSAY_LLM` is ignored if set. Factory analog:
`product_automated_verify` (score running artifacts, not listings).

| Variable | Default | Effect |
|---|---|---|
| `AIMARKET_FEDERATION_GOSSIP_MAX_OBSERVED` | `2000` | Resource/fan-out bound for quarantined observed addresses |
| `AIMARKET_FEDERATION_OPEN` | `0` | Legacy switch for richer preview/admission behaviour; visibility is always on |
| `AIMARKET_FEDERATION_PREVIEW_CAPS` | `1` | Signature-verified preview of a pending peer's catalogue |
| `AIMARKET_FEDERATION_PREVIEW_MAX_CAPS` | `25` | Per-peer preview cap |
| `AIMARKET_FEDERATION_ASSAY` | `1` | Post-quarantine sandbox assay |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | Probe one public free capability (receipt must match advertised key) |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | A `pass` sets `trusted` **only with a judge token**. Alias: `AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | OpenRouter chat if a key exists | OpenAI-compatible veto on sandbox evidence |
| `AIMARKET_FEDERATION_JUDGE_KEY` | `OPENROUTER_API_KEY` fallback | **No key → manual Approve only** |
| `AIMARKET_FEDERATION_JUDGE_MODEL` | `minimax/minimax-m3` | MiniMax, same as the rest of the fleet |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | If `1`, a judge error blocks auto-admit (also implied when auto-admit + key) |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | If `1`, human Approve refuses unless last assay is `pass` |

Join path: [`docs/join-the-federation.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.md) · internals: [`docs/federation-admission.md`](docs/federation-admission.md) (EN·RU·ES·FR·ZH) · both spellings of the discovery document and crawler header (`/.well-known/agent-marketplace`, `Agent-Marketplace-Crawler`, the IETF drafts): [`docs/discovery-names.md`](docs/discovery-names.md).

Surfaces: `GET /federation/peers` (`pending` array) and `GET /federation/preview?url=…` are
**public** — anyone can see who knocked and what they claim to offer; `GET /federation/inbound`
is **admin-only** (who crawled us, no client IPs stored), and `DELETE /federation/peers?url=…`
lets an operator reject a pending peer and drop its preview rows. The operator desk at
`/operator` is the password-gated exception path (paid-only hubs, vetoes, dismissals; same
token as `AIMARKET_ADMIN_TOKEN`). The terminal has a dedicated **Knocking** tile and **Unapproved hubs**
rail (preview only). Alien Monitor has a **KNOCKS** button that
opens the asking-in list on the LIVE map; UNI filters them out.

### A2A 1.0: search and paid invoke

The Hub exposes an actual [A2A 1.0](https://a2a-protocol.org/latest/specification/)
JSON-RPC agent at `/a2a`, discovered through `/.well-known/agent-card.json`. It advertises two
skills, both narrow and real. `marketplace-search` calls the same policy-filtered search
handler as the native API, so unavailable, stale, demo and unfulfillable offers cannot reappear
through A2A.

```bash
curl -sS http://localhost:9083/a2a \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  --data '{"jsonrpc":"2.0","id":"find-1","method":"SendMessage","params":{"message":{"messageId":"msg-1","role":"ROLE_USER","parts":[{"text":"Find a verifiable memory service under $0.10"}]}}}' \
  | jq '.result.message.parts[1].data.matches'
```

Search answers with a direct A2A `Message`. `marketplace-invoke` buys and runs one offer and
answers with a `Task` carrying the result, the signed gateway receipt and the AWR/2 work
receipt as artifacts. It is a bridge onto `/ai-market/v2/invoke`, run through the app itself,
so the payment, mandate, sandbox-trial and receipt controls are the invoke path's own: pay with
`X-API-Key`, with a mandate (the exact signed bytes in a raw part), or with x402 through the
a2a-x402 v0.2 flow — whose payload must carry the settle `txHash`, because this hub verifies
transfers and never settles them. A retried message never pays twice. Tasks are kept in the
hub database (migration 036), scoped to the account, mandate or caller that created them, and
never hold a key, a proof, a payment payload or — once finished — the input. Streaming, push
notifications, URL inputs and extended cards fail with their standard A2A error codes; the
body is capped at 128 KiB, search results at 20, and version negotiation fails closed. Wire
examples, the task-state table and the one x402 profile deviation: [docs/a2a.md](docs/a2a.md).

### Retrying a paid call

A timed-out `POST /ai-market/v2/invoke` paid with `X-API-Key` (or a ledger channel and its
secret) may or may not have run. Send an `Idempotency-Key` (1–128 of `A-Z a-z 0-9 . _ : -`) and
retry with the same key and body: the hub answers with the first result
(`X-AIMarket-Idempotency: replayed`) instead of running and charging again. The same key with
another body is `422 idempotency_key_reused`; while the first request still runs it is
`409 idempotency_in_progress`, and one that never finished is `409 idempotency_outcome_unknown`
after 15 minutes (the ledger at `GET /ai-market/v2/account` says whether it was charged). Answers
are kept 24 hours under a hash of the credential; refusals that come before any money moves
(401, 403, 404, 413, 415, 422, 429, 503) are not kept. x402 and escrow-channel payments are
single-use already and answer `X-AIMarket-Idempotency: not-applicable`.

### x402 interoperability

The hub speaks [x402](https://docs.x402.org/) — the machine-payment standard that became a
Linux Foundation project in July 2026 — alongside its own payment surface:

- a `402` from this hub's own payment gate carries the x402 **V2** payload in a base64
  `PAYMENT-REQUIRED` header (a peer's 402 passed through verbatim is left untouched — its
  terms are the peer's, not ours), and the
  **V1** `accepts` array merged additively into the body, so both generations of client can
  read it and existing consumers see no change;
- `GET /discovery/resources` serves a **Bazaar-compatible** index of priced capabilities —
  the same envelope every official x402 SDK deserializes, so pointing a facilitator client
  at this hub enumerates its catalogue with no code changes;
- a `PAYMENT-SIGNATURE` / `X-Payment` is **accepted** on the market rail: the buyer
  sends USDC on-chain to the listing's `payout_address`, and the hub verifies that
  transfer (`aimarket_hub/settle.py`). It never custodies the funds. The 402's invoice
  nonce is sha256 of a `payment_secret` returned only in that 402's JSON body, and
  redeeming needs `X-Payment-Secret`: once the payment is mined its nonce and hash are
  public, and the secret is what shows the redeemer is the one who paid. Only the
  transfer the buyer's own authorization moved pays for the call. `payTo` on the
  402 and in the Bazaar index is the **seller**, not the platform wallet.

An operator may take a share of a catalogue sale **without** taking custody of it:
`AIMARKET_MARKET_FEE_BPS` plus a deployed
[`MarketSplitter`](https://github.com/alexar76/aicom/blob/main/contracts/evm/src/MarketSplitter.sol) makes the 402 name a
contract that forwards both shares in the buyer's own transaction. The hub then
requires both `Transfer` legs — seller and operator — rather than trusting that the
payment was routed through any particular address. Off by default.

**Where the money goes, rail by rail, with diagrams:
[`docs/money-rails.md`](docs/money-rails.md).**

See [`aimarket_hub/settle.py`](aimarket_hub/settle.py) and [`aimarket_hub/x402.py`](aimarket_hub/x402.py).

### ERC-8004 identity

The public hub at modelmarket.dev is ERC-8004 agent
[`96682` on Base](https://8004scan.io/agents/base/96682), registered on 2026-10-01 in the
canonical IdentityRegistry `0x8004A169…a432` and owned by the operator wallet
`0x1218ff36…Ad0a`. The hub names that agentId in the `erc8004` block of its signed
`/.well-known/ai-market.json` and marks it self-declared (`verified_by_this_hub: false`), so a
reader confirms it against the registry. Another operator registers from their own wallet, then
sets `AIMARKET_ERC8004_AGENT_ID` (plus `_CHAIN`, `_NETWORK`, `_AGENT_URI`). Transactions,
registration files and how to check them:
[ERC-8004 identities](https://github.com/alexar76/aicom/blob/main/docs/erc-8004-identities.md).

Full walkthrough: [`../docs/join-the-federation.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.md) ·
Normative text: protocol spec §2.4–2.6.

Trust scoring: [`trust.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/trust.py) · Signing: [`signing.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/signing.py)

Peer key pin / mismatch / admin re-pin (EN·RU·ES·FR·ZH): [`docs/federation-peer-keys.md`](./docs/federation-peer-keys.md)

Deep dive: [`../docs/FEDERATION_HUB_REPORT.md`](https://github.com/alexar76/aicom/blob/main/docs/FEDERATION_HUB_REPORT.md)

---

## Payments

```mermaid
sequenceDiagram
  participant User
  participant Hub
  participant Chain as Base (USDC)

  User->>Chain: deposit USDC
  User->>Hub: channel/open(deposit_usd)
  Note over Hub: Ledger tracks balance off-chain

  loop each invoke
    User->>Hub: invoke + X-Payment-Channel
    Hub->>Hub: decrement channel balance
  end

  User->>Hub: channel/close
  Hub->>Hub: record settlement + refund_owed_usd
  Note over User,Hub: refund_executed_usd = 0; payout is separate
```

| Field | Default | Notes |
|-------|---------|-------|
| Chain | Base (L2) | `AIMARKET_PAYMENT_CHAIN` |
| Token | USDC | `AIMARKET_PAYMENT_TOKEN` — the ledger's default; the advertised catalog is `AIMARKET_PAYMENT_TOKENS` (`USDT,USDC,ETH`) |
| Recipient | env required | `AIMARKET_PAYMENT_RECIPIENT` |

**Custody depends on the rail.** Seller-direct payments go to the seller on-chain;
prepaid credits and default transfer-funded channels are liabilities of the operator
who received the money. Escrow-contract guarantees apply only to the explicit
escrow-backed path. Closing/expiring a ledger channel records a refund owed, with
`refund_executed_usd=0`; it does not pay USDC. Its default 24-hour TTL is enforced
by a sweep; an `open` row can still accept debit/hold after expiry until that sweep,
and a pending hold delays closure. Credit holds, key expiry, mandate limits and
actual cash refunds follow their own rules:
[credit lifecycle](docs/credits-topup.md#credit-lifecycle) ·
[mandates](docs/mandates.md) · [money rails](docs/money-rails.md).

**Deposit authorization.** In production (`AIFACTORY_PROD=1`, verify stub off) a channel is credited
only by a deposit that is verified on-chain, bound to the wallet that actually paid, single-use
(`consumed_deposits`), and proven by an EIP-191 signature from the paying wallet over
`payer_proof_challenge(...)` — the deposit tx hash is public, so without that proof the channel
secret would go to whoever quotes it first. `AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1` opts out of
the proof (transition only) and logs loudly.

---

## Pay-on-Verified

**Opt-in quality escrow on invoke.** With a `verify` block on the invoke body the channel debit
becomes a hold; [Metis](https://github.com/alexar76/metis) judges the delivered output against the
buyer's stated intent in the background — pass captures the hold, fail refunds it with a signed
rejection receipt. The buyer keeps the output either way; only the money outcome changes.

| | |
|---|---|
| **What** | `verify: { requested, intent, mode, wait }` on `POST /ai-market/v2/invoke` → `hold_channel` → Metis verdict → capture / release |
| **Why** | Providers are paid for verified work, not for responding; every verdict emits a reputation event |
| **Lookup** | `GET /ai-market/v2/verification/{nonce}` (nonce = receipt nonce) |
| **Deep dive** | [docs/pay-on-verified.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/pay-on-verified.md) · [Cross-component doc](https://github.com/alexar76/aicom/blob/main/docs/pay-on-verified.md) |

---

## Agent mandates and subcontracting

**An owner's signed spending limits for an agent key, and purchases a provider makes inside a
buyer's call.** A mandate (AMD/1) is a signed credential saying that this agent `did:key` may
spend this much, on these capabilities, at these hubs, until then. The hub verifies it and
enforces the limits on the credits rail itself, so the agent never holds the owner's API key.
Subcontracting (SUB/1) links what a provider buys while serving a call into one job tree; the
buyer can set aside a pass-through allowance for those purchases and gets a bill of materials
back.

| | |
|---|---|
| **Mandate** | `POST /ai-market/v2/mandates` registers one; `X-AIMarket-Mandate` + `X-AIMarket-Mandate-Proof` pay with it; `402 mandate_limit` names the limit reached; `POST /ai-market/v2/mandates/revoke` revokes it and everything re-delegated from it |
| **Subcontracting** | every provider the hub executes receives `X-AIMarket-Job` (plus `X-AIMarket-Job-Grant` with an allowance); `"subcontract": {"allowance_usd": …, "max_depth": …}` on the root invoke; the bill in `subcontracting`, and later at `GET /ai-market/v2/jobs/{job_id}` |
| **Needs** | `AIMARKET_CREDITS_ENABLED=1`, and `AIMARKET_HUB_URL` set to the public URL mandates name in `audience` |
| **Deep dive** | [docs/mandates.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/mandates.md) · [Protocol: AMD/1 and SUB/1](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md) |

```python
import httpx
from aimarket_agent import AIMarketAgent, AgentKey, Mandate, issue_mandate

HUB = "https://modelmarket.dev"
agent_key = AgentKey.generate()
# The owner signs; the owner's DID must already be linked to a credit account on this hub.
doc = issue_mandate(owner_key, agent_key.did, audience=[HUB], scope=["gaia.*"],
                    per_call_usd=0.02, per_day_usd=1.00)
httpx.post(f"{HUB}/ai-market/v2/mandates", json=doc)            # register
client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent_key, hub_origin=HUB))
client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
```

---

## Configuration

Every default below is the value the code falls back to today; where a default is *derived*
from another variable, the rule is spelled out rather than a number.

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `AIMARKET_HUB_NAME` | AIMarket Hub | Display name in manifests |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | Public URL (receipts, well-known) |
| `AIFACTORY_PROD` | — | `1` puts every money gate on the production path (on-chain verification required, fail-closed defaults) |
| `AIFACTORY_CRYPTO_ENABLED` | `0` | Master crypto switch: off ⇒ channels/escrow/NFT disabled, capabilities served free; signing and sandbox trials keep working |
| `AIMARKET_PAYMENT_CHAIN` | `base` | Settlement chain (`AIMARKET_PAYMENT_CHAINS` for the advertised list) |
| `AIMARKET_PAYMENT_TOKEN` | `USDC` | Ledger settlement token (`AIMARKET_PAYMENT_TOKENS` advertises `USDT,USDC,ETH`) |
| `AIMARKET_PAYMENT_RECIPIENT` | — | **Required in production** — the wallet deposits must pay |
| `AIMARKET_CRAWL_INTERVAL_S` | `3600` | Federation crawl period |
| `AIMARKET_CATALOG_MAX_STALE_S` | `21600` | Stop offering a peer's rows after this many seconds without a successful crawl; rows stay stored for recovery and can be inspected with `include_stale=true` |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | Routing fee (1% = 100 bps) |
| `AIMARKET_MIN_TRUST_SCORE` | `0.3` | Baseline trust floor (also the discover-gate default below) |
| `AIMARKET_SEED_LIST` | committed `federation_seeds.json` | Comma-separated peer `.well-known` URLs; unset falls back to the shipped seed file, not to "no seeds" |
| `AIMARKET_SEED_PUBKEYS` | committed seed `public_key` fields | `{url:key}` JSON or `url=key,…` — trusted-on-**first-contact** only; rotating an existing DB pin requires `POST /federation/peers/repin` |
| `AIMARKET_PLUGIN_WHITELIST` | — | Restrict loaded plugins |
| `AIMARKET_ADMIN_TOKEN` | — | Operator token. Unset ⇒ every admin route refuses (`503`), fail-closed |
| `AIMARKET_PUBLISH_TOKEN` | — | Legacy shared token; not sufficient for production publisher identity |
| `AIMARKET_PUBLISHER_TOKENS` | — | `pub-a:secretA,pub-b:secretB` — per-publisher credentials for the stake/bond routes (see Security) |
| `AIMARKET_AGENT_TOKENS` | — | `agent-a:secretA,…` — per-agent credentials for self-bond/reporting and wallet-bound lottery entitlements |
| `AIMARKET_CORS_ORIGINS` | — | Comma-separated allowlist. Empty means no cross-origin access (a `*` default enabled drive-by CSRF) |

### Databases

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite files | PostgreSQL for production — when set, every subsystem shares it; mandatory when `AIFACTORY_PROD=1` |
| `AIMARKET_DB_PATH` | `data/hub.db` | The **hub index** database. It no longer overrides a path a subsystem passes explicitly (that silently aliased channels.db and provenance.db onto the hub file); a subsystem that must share the hub file now points its own variable at it |
| `AIMARKET_CHANNELS_DB_PATH` | `data/channels.db` | Payment-channel ledger (separate file from the hub index) |
| `AIMARKET_VERIFY_SETTLEMENTS_DB_PATH` | `AIMARKET_DB_PATH`, else `data/hub.db` | Where `verified_settlements` lives — the orphaned-hold reaper reads it and refuses to release anything it cannot read |

#### Moving an existing production Hub from SQLite to PostgreSQL

The standalone Hub and sandbox trial ledger fail at startup when `AIFACTORY_PROD=1`
unless `DATABASE_URL` uses `postgresql://` (or `postgres://`). Production can therefore no
longer silently create a fresh SQLite fallback when an environment file is missing.

Production deployments should set `DATABASE_URL` and keep the running Hub, channel ledger,
sandbox quota, settlement records and provenance in one PostgreSQL database.  The migration
tool opens every SQLite source read-only, inserts idempotently, validates row counts and then
advances every PostgreSQL serial sequence; skipping the last step makes the first new write
collide with an imported `id`.

Run the cutover with the Hub stopped and start from an empty target database:

```bash
export TARGET_DATABASE_URL='postgresql:///aimarket_hub'
systemctl stop aimarket-hub

# Initialize every Hub subsystem in the empty target schema.
DATABASE_URL="$TARGET_DATABASE_URL" \
  AIMARKET_SIGNING_KEY_PATH=/var/lib/aimarket/hub_signing_key \
  python -c 'from aimarket_hub.api import create_app; create_app()'

python scripts/migrate_sqlite_to_postgres.py \
  --dsn "$TARGET_DATABASE_URL" \
  --sqlite /var/lib/aimarket/hub-federation.db \
  --sqlite /var/lib/aimarket/channels.db \
  --sqlite /var/lib/aimarket/sandbox_trials.db

# Put DATABASE_URL in the service environment, then start and verify before removing nothing.
systemctl start aimarket-hub
curl -fsS http://127.0.0.1:9083/ai-market/v2/health
curl -fsS http://127.0.0.1:9083/ai-market/v2/search?intent=echo
```

Keep the SQLite files as a rollback snapshot until a PostgreSQL `pg_dump` has passed an
actual restore test.  A production backup job must include the PostgreSQL dump and both
signing keys (`hub_signing_key` and `hub_signing_key_mldsa`); copying the old `.db` files is
not a backup of a Hub that is running on PostgreSQL.

#### Upgrading past the shared-database aliasing

**This is a one-time migration step for any hub that already ran with `AIMARKET_DB_PATH`
set** — which includes every container here (`Dockerfile`, `Dockerfile.standalone`,
`docker-compose.yml`, `docker-compose.core.yml` all export it).

Until this release the env var overrode the path a subsystem asked for, so the channel
ledger (`data/channels.db`) and the provenance store (`data/provenance.db`) were created
*inside the hub file*. Now that the explicit argument wins, those subsystems open their own
files — and on an upgraded deployment those files **start empty**:

* the channel ledger loses its open channels and, more seriously, `consumed_deposits` —
  the table that makes an on-chain deposit single-use. An empty one lets every deposit
  already spent be replayed into a new funded channel;
* the provenance store loses its receipts.

The hub logs this at `ERROR` on startup (the requested file does not exist while the
`AIMARKET_DB_PATH` file does), naming the file the data is still in. Do one of these
**before serving traffic**:

```bash
# A. channel ledger — keep the shared file, no data moves, pre-upgrade behaviour exactly
export AIMARKET_CHANNELS_DB_PATH="$AIMARKET_DB_PATH"

# B. channel ledger — split it out: copy the file with the hub stopped
cp /app/data/hub.db /app/data/channels.db
export AIMARKET_CHANNELS_DB_PATH=/app/data/channels.db
```

Either way the tables the copy's owner does not use are simply never read. The provenance
store has **no** path variable — it always derives `provenance.db` from the hub database's
directory — so B is the only option there (`cp /app/data/hub.db /app/data/provenance.db`);
skipping it starts an empty receipt store, which costs an audit trail but no money.

`DATABASE_URL` deployments are unaffected — PostgreSQL was always one shared database.

### Channels

| Variable | Default | Description |
|----------|---------|-------------|
| `AIMARKET_ALLOW_DEMO_CREDIT` | — | `1` credits a channel without on-chain verification (dev/demo). Outside production, without it, crediting fails closed |
| `AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER` | `0` | `1` opts OUT of the payer proof-of-control requirement (transition only — leaves deposit front-running open) |
| `AIMARKET_CHANNEL_ANON_OPENS_PER_HOUR` | `200` | One shared cap for all wallet-less opens (they are not exempt) |
| `AIMARKET_CHANNEL_ANON_CLOSES_PER_HOUR` | `600` | Same, for closes |
| `AIMARKET_CHANNEL_HOLD_REAP_AFTER_SECS` | `86400` | Release a hold stuck `held` this long with no live verification; `0` disables the reaper |
| `AIFACTORY_PAYMENT_MIN_CONFIRMATIONS` | `2` | Confirmations a deposit needs before it counts |
| `AIFACTORY_PAYMENT_VERIFY_STUB` | `0` | `1` accepts any tx hash — development only |

### Pay-on-Verified

| Variable | Default | Description |
|----------|---------|-------------|
| `AIMARKET_VERIFY_ENABLED` | `1` | Pay-on-Verified master switch (per-invoke opt-in still required) |
| `AIMARKET_VERIFY_MIN_PRICE_USD` | `0.05` | Price floor — cheaper invokes are never verification-taxed |
| `AIMARKET_VERIFY_SCORE_THRESHOLD` | `0.7` | `verify_score` needed to capture the hold (a value outside 0.0–1.0 falls back to `0.7`) |
| `AIMARKET_VERIFY_COUNCIL_MIN_PRICE_USD` | `0.50` | Route ceiling: `council` allowed at/above this price, else clamped to `fast` |
| `AIMARKET_VERIFY_MAX_CONCURRENCY` | `8` | Cap on simultaneous Metis calls across pending settlements |
| `AIMARKET_VERIFY_ATTEMPT_TIMEOUT_S` | `330` | Per-attempt Metis HTTP timeout (> Metis 300 s server cap) |
| `AIMARKET_VERIFY_RETRY_BACKOFF_S` | `5` | Initial transport-retry backoff (exponential, cap 300 s) |
| `AIMARKET_VERIFY_ENGINE_RETRIES` | `2` | Re-runs after an engine-error envelope before policy applies |
| `AIMARKET_VERIFY_MAX_WAIT_S` | `0` | `0` = no verdict deadline; `>0` bounds resolution via policy |
| `AIMARKET_VERIFY_FAIL_CLOSED` | `1` | Indeterminate outcome ⇒ refund the buyer. Only an explicit `0/false/no/off` captures instead; an unrecognised value is a typo and still fails closed |
| `AIMARKET_VERIFY_METIS_URL` | `http://127.0.0.1:8080` | Metis base URL (falls back to `METIS_URL`) |
| `AIMARKET_VERIFY_METIS_KEY` | — | Metis bearer key (falls back to `METIS_API_KEY`) |
| `AIMARKET_VERIFY_VERIFIER_ID` | `metis.verify@v1` | Envelope `verifier` attribution when a non-Metis verifier serves the slot |
| `AIMARKET_APPEAL_WINDOW_S` | `0` | Appeals ([protocol](docs/pay-on-verified.md#appeals)): seconds a genuine paid verdict stays provisional and appealable by the losing party. `0` = off, verdicts move money at once |
| `AIMARKET_APPEAL_METIS_URL` | — | The appeal court: a second verifier. Unset, or equal to the first-instance URL, keeps appeals off |
| `AIMARKET_APPEAL_METIS_KEY` | — | Appeal court bearer key |
| `AIMARKET_APPEAL_VERIFIER_ID` | `metis.appeal@v1` | Names the appeal court in envelopes; must differ from `AIMARKET_VERIFY_VERIFIER_ID` |
| `AIMARKET_APPEAL_BOND_MIN_USD` / `AIMARKET_APPEAL_BOND_RATE` | `0.02` / `0.20` | Bond = max(min, rate × price), capped at the price |
| `AIMARKET_APPEAL_MAX_WAIT_S` | `21600` | After this the court counts as indeterminate: the first verdict stands, the bond is returned (`0` = no limit) |
| `AIMARKET_APPEAL_SWEEP_S` | `30` | Safety-net pass that finalizes expired windows and picks up filed appeals |

### Supply security (community publishers)

Full model: [`docs/supply-security.md`](https://github.com/alexar76/aimarket-hub/blob/main/docs/supply-security.md). A non-finite or non-numeric
value in any threshold below is ignored with a warning and the documented default is used — a
`nan` threshold would otherwise silently disable the gate it configures.

| Variable | Default | Description |
|----------|---------|-------------|
| `AIMARKET_SUPPLY_SECURITY_RELAXED` | `0` | `1` = dev bypass: zero minimum stake, no response-signature requirement, no slashing |
| `AIMARKET_SUPPLY_MIN_STAKE_USD` | `25` in production, else `10` (`0` when relaxed) | Stake required to publish |
| `AIMARKET_SUPPLY_PUBLISH_PER_HOUR` | `5` | Publishes per publisher per hour |
| `AIMARKET_SUPPLY_MIN_TRUST_DISCOVER` | `AIMARKET_MIN_TRUST_SCORE` (`0.3`) | Trust floor to appear in discover |
| `AIMARKET_SUPPLY_MIN_TRUST_INVOKE` | `0.35` | Trust floor to be invoked |
| `AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG` | on iff production and not relaxed | Require an Ed25519 provider response signature |
| `AIMARKET_SUPPLY_MAX_INPUT_KEYS` | `32` | Top-level keys accepted in an invoke input |
| `AIMARKET_SUPPLY_MAX_INPUT_JSON_BYTES` | `32768` | Invoke input size cap |
| `AIMARKET_SUPPLY_PRODUCT_ALLOWLIST` | — | Comma-separated `product_id` allowlist |
| `AIMARKET_SUPPLY_SLASH_FAILURE_THRESHOLD` | `3` | Provider faults within the window before stake is slashed |
| `AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S` | `600` | Fault window (must be > 0; a non-positive value would disable slashing, so it falls back) |
| `AIMARKET_SUPPLY_SLASH_COOLDOWN_S` | `3600` | At most one failure-driven slash per window; `0` disables the cool-down |
| `AIMARKET_SUPPLY_SLASH_DAILY_CAP_USD` | `10` | Rolling 24 h cap on failure-driven slashing; `0` disables the cap |
| `AIMARKET_SUPPLY_VERIFIED_FAIL_THRESHOLD` | `3` | Paid Metis "failed" verdicts before escalation |
| `AIMARKET_SUPPLY_VERIFIED_FAIL_WINDOW_S` | `86400` | Window for those verdicts |
| `AIMARKET_SUPPLY_VERIFIED_FAIL_MIN_CONSUMERS` | `2` | Distinct PAYING consumers required — one buyer's repeated failures are one voice |
| `AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES` | `1000` | Trust-graph bound; truncation is logged with the publisher it affected |
| `AIMARKET_ORACLE_FAMILY_URL` | `https://oracles.modelmarket.dev/family` | LUMEN trust oracle (falls back to `ARGUS_ORACLE_FAMILY_URL`) |

---

## Deployment

**Start here:** [complete production deployment runbook](docs/production-deployment.md). It is also available in [Russian](docs/production-deployment.ru.md), [Spanish](docs/production-deployment.es.md), [French](docs/production-deployment.fr.md) and [Chinese](docs/production-deployment.zh.md).

The runbook covers immutable commit-pinned releases, unprivileged systemd services, nginx/TLS on a hostname or `/hub` subpath, same-origin federation discovery and `invoke`, signed-manifest and real `402` assay evidence, protocol-only federation admission, UFW/Fail2ban/SSH hardening, backups, reboot acceptance, Alien Monitor and SKOPOS enrollment. Do not expose the provider backend or replace the Hub's Ed25519 key during a routine upgrade.

Reference record for the maintained public installation: [`../docs/production-modelmarket-dev.md`](https://github.com/alexar76/aicom/blob/main/docs/production-modelmarket-dev.md).

---

<a id="testing--coverage"></a>

## Testing & coverage
CI runs on every push ([workflow](https://github.com/alexar76/aimarket-hub/blob/main/.github/workflows/ci.yml)); coverage badge is refreshed from `pytest --cov` on `main`.

```bash
cd aimarket-hub
pip install -e ".[dev]"
pytest tests/ -q --cov=aimarket_hub
```

## Development

```bash
pip install -e ".[dev]"
```

Key test modules: `test_api.py`, `test_crawler.py`, `test_plugin_system.py`, `test_channels.py`, `test_cross_hub_integration.py`

Add a plugin: create package under [`../plugins/`](https://github.com/alexar76/aimarket-plugins/tree/main/plugins/) with `pyproject.toml` entry point `aimarket.plugins`.

---

## Security

- **SSRF protection** on federation crawler ([`crawler.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/crawler.py))
- **Hybrid signed evidence** — with `AIMARKET_PQC=1`, manifests, discovery documents,
  invoke receipts, rejection receipts and Pay-on-Verified verdict envelopes carry Ed25519 and
  ML-DSA-65 signatures over the same versioned canonical payload. Classical verification remains
  mandatory; PQ verification fails closed when a PQ signature is present. The public
  `/ai-market/v2/receipts/verify` endpoint is pinned to this Hub's persisted keys and accepts no
  caller-supplied key, preventing self-verifying receipts
  ([`signing.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/signing.py))
- **Safety gate** on every invoke ([`safety_gate.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/safety_gate.py))
- **Verified, single-use stake deposits** — in production every stake credit needs an on-chain
  deposit that pays the platform recipient, and the hash is burned by an atomic claim before the
  credit, so one deposit can never fund two publishers even under concurrent requests. The claim
  is keyed on the *canonical* transaction id (an EVM hash is case-insensitive at the JSON-RPC
  layer, so `0xAB…` and `0xab…` are one deposit, not two)
  ([`supply_security.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/supply_security.py))
- **Residual — stake deposits are not payer-bound.** The stake verifier answers "did somebody pay
  the platform?", not "did *this* publisher pay", so whoever submits a matching hash first gets the
  credit. Binding it needs a publisher→wallet record the stake ledger does not yet have; channel
  deposits are already bound (see the entry below). Until then, treat a stake deposit hash as a
  bearer secret and submit it before it is public
- **Single-use channel deposits + payer proof** — a verified deposit funds exactly one channel and
  only for the wallet that signed for it ([`channels.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/channels.py))
- **Stake mutation is per-subject, slashing is operator-only** — a shared token can neither credit
  a stranger's stake nor burn a rival's bond ([`api.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/api.py))
- **Vulnerability reports:** [SECURITY.md](https://github.com/alexar76/aimarket-hub/blob/main/SECURITY.md) → alexar76@rambler.ru

---

## Related projects

| Project | Relationship |
|---------|--------------|
| [AICOM / AI-Factory](https://github.com/alexar76/aicom/blob/main/README.md) | Ships products → hub index |
| [aimarket-protocol](https://github.com/alexar76/aimarket-protocol/tree/main/) | Normative v2 spec |
| [aimarket-sdks](https://github.com/alexar76/aimarket-sdks/tree/main/) | Client SDKs (Dart alpha) |
| [aimarket-widget](https://github.com/alexar76/aimarket-widget/tree/main/) | Embeddable UI |
| [oracles](https://github.com/alexar76/oracles/tree/main/) | Verifiable math capabilities — randomness, VDF, consensus, reputation (listed on hub) |
| [desktop-integrations](https://github.com/alexar76/aimarket-desktop/tree/main/) | 8 Flutter consumer apps |
| [Ecosystem architecture](https://github.com/alexar76/aicom/blob/main/docs/ecosystem-architecture.md) | Full monorepo diagram |
| [dioscuri](https://github.com/alexar76/dioscuri) | Twin community agents — MNEMOSYNE Q&A |

---

## Community

The [DIOSCURI](https://github.com/alexar76/dioscuri) twins answer questions from synced GitHub docs.

| Channel | Twin | Best for |
|---------|------|----------|
| [Discord](https://discord.gg/JjWxGhW9pP) | Pollux | Help, ideas, show-and-tell |
| [Telegram](https://t.me/just_for_agents) | Castor | Releases, digests, quick news |

**Ecosystem map:** [Alien Monitor](https://monitor.modelmarket.dev/) · [AICOM](https://magic-ai-factory.com)

---

## License

Apache-2.0 — see [LICENSE](https://github.com/alexar76/aimarket-hub/blob/main/LICENSE). Maintainers: [CONTRIBUTORS.md](https://github.com/alexar76/aimarket-hub/blob/main/CONTRIBUTORS.md).
