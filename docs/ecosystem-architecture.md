# AICOM Monorepo — Ecosystem Architecture

> **Killer features:** [killer-features.md](killer-features.md) — Auto-Mesh Pipeline · Zero-Trust Discovery · TEE Escrow · 1-Click Embed

Industry-style reference for how **AI-Factory**, **AIMarket Protocol v2**, **AIMarket Hub**, **desktop SKUs**, and **on-chain settlement** fit together in this repository.

Normative protocol: [`aimarket-protocol/spec.md`](../aimarket-protocol/spec.md) · **Full ecosystem diagram:** [`aimarket-protocol/ecosystem.md`](../aimarket-protocol/ecosystem.md) · Hub implementation: [`aimarket-hub/README.md`](../aimarket-hub/README.md)

---

## 1. System context (C4 — Level 1)

```mermaid
C4Context
  title AICOM ecosystem — system context

  Person(operator, "Factory operator", "Runs pipeline, ships products")
  Person(builder, "Capability builder", "Lists AI functions on a hub")
  Person(enduser, "End user", "Uses desktop apps or storefront")

  System(aicom, "AICOM monorepo", "Factory pipeline + hub + SDKs + desktop apps")
  System_Ext(llm, "LLM providers", "OpenAI-compatible APIs, Ollama")
  System_Ext(chain, "Base / EVM", "USDT channels & settlement")

  Rel(operator, aicom, "Admin, CLI, deploy")
  Rel(builder, aicom, "Publish capabilities")
  Rel(enduser, aicom, "Discover, invoke, review")
  Rel(aicom, llm, "Agent prompts & codegen")
  Rel(aicom, chain, "Payment channels")
```

---

## 2. Monorepo map

| Path | Role | Split-repo target |
|------|------|-------------------|
| [`web/`](../web/) | AI-Factory UI (Next.js) + API (FastAPI) | `aicom` core |
| [`agents/`](../agents/) · [`orchestrator/`](../orchestrator/) · [`pipeline_worker.py`](../pipeline_worker.py) | Multi-agent product pipeline | `aicom` |
| [`aimarket-hub/`](../aimarket-hub/) | Federation hub (search, invoke, plugins) | `aimarket-hub` |
| [`aimarket-protocol/`](../aimarket-protocol/) | Protocol v2 spec + schemas | `aimarket-protocol` |
| [`plugins/`](../plugins/) | 14 pip-installable hub plugins | one repo per plugin |
| [`aimarket-sdks/`](../aimarket-sdks/) | Dart / TS / Rust client SDKs | per language |
| [`aimarket-widget/`](../aimarket-widget/) | Embeddable search + invoke widget | `aimarket-widget` |
| [`desktop-integrations/`](../desktop-integrations/) | 8 Flutter desktop SKUs + shared packages | one repo per app |
| [`contracts/`](../contracts/) | EVM + Solana payment contracts | `aicom-contracts` |

---

## 3. End-to-end data flow

**Ship on factory → list on hub → consume from desktop/widget.**

```mermaid
flowchart TB
  subgraph factory["AI-Factory (magic-ai-factory.com)"]
    IDEA["Idea / Discovery"]
    PIPE["Pipeline worker + 13 agents"]
    ART["data/code · specs · pipeline.db"]
    WELL["/.well-known/ai-market.json"]
    IDEA --> PIPE --> ART
    ART --> WELL
  end

  subgraph hub["AIMarket Hub (modelmarket.dev)"]
    BRIDGE["factory_bridge · auto_listing"]
    IDX["database.py indexer"]
    SRCH["/ai-market/v2/search"]
    INV["/ai-market/v2/invoke"]
    PLG["PluginRegistry hooks"]
    WELL2["/.well-known/ai-market.json"]
    BRIDGE --> IDX
    SRCH --> IDX
    INV --> PLG
    IDX --> WELL2
  end

  subgraph clients["Consumers"]
    DESK["8× Flutter desktop apps"]
    WIDGET["aimarket-widget"]
    AGENT["aimarket_agent SDK"]
  end

  subgraph chain["Settlement"]
    CH["channel/open → invoke → channel/close"]
  end

  WELL -->|"federation seed + import"| BRIDGE
  ART -->|"sync_pipeline_mirror_and_hub.py"| BRIDGE
  DESK --> AGENT
  WIDGET --> SRCH
  AGENT --> SRCH
  AGENT --> INV
  INV --> CH
  PLG --> INV
```

Ops script: [`scripts/sync_pipeline_mirror_and_hub.py`](../scripts/sync_pipeline_mirror_and_hub.py) · Loader: [`aimarket_hub/factory_bridge.py`](../aimarket-hub/aimarket_hub/factory_bridge.py)

---

## 4. Production deployment topology

Typical split-host layout (see [`production-modelmarket-dev.md`](./production-modelmarket-dev.md)):

```mermaid
flowchart LR
  subgraph internet["Public internet"]
    U["Users"]
  end

  subgraph host["Single VPS or k8s cluster"]
    NGINX["nginx / TLS"]
    FAC["AI-Factory :9080/:9081"]
    HUB["AIMarket Hub :9083→9080"]
    DATA[("bind mount ./data")]
  end

  U --> NGINX
  NGINX -->|"magic-ai-factory.com"| FAC
  NGINX -->|"modelmarket.dev"| HUB
  FAC --> DATA
  HUB --> DATA
  HUB -->|"crawl peers"| PEERS["Other hubs"]
```

| Surface | Default host port | Purpose |
|---------|-------------------|---------|
| Factory frontend | 9080 | Admin + storefront |
| Factory API | 9081 | REST, metrics |
| AIMarket Hub | 9083 (→ 9080 in container) | Federation API + widget |

---

## 5. AIMarket invoke lifecycle (protocol v2)

Five phases implemented by [`aimarket_agent`](../aimarket-sdks/dart/) and hub [`api.py`](../aimarket-hub/aimarket_hub/api.py):

```mermaid
sequenceDiagram
  autonumber
  participant App as Client app / SDK
  participant Hub as AIMarket Hub
  participant Plugins as Plugin hooks
  participant Provider as Provider hub or factory invoke
  participant Chain as Payment channel

  App->>Hub: GET /search?intent=…&budget=…
  Hub-->>App: Plan (ranked capabilities)

  App->>Hub: POST /channel/open {deposit_usd}
  Hub->>Chain: Open channel
  Chain-->>Hub: channel_id, balance
  Hub-->>App: Channel

  App->>Hub: POST /invoke {capability_id, input, channel_id}
  Hub->>Plugins: on_invoke_pre_check
  alt blocked
    Plugins-->>Hub: rejection receipt
    Hub-->>App: 403 + refund
  else allowed
    Hub->>Provider: Route invoke
    Provider-->>Hub: output + price_usd
    Hub->>Plugins: on_invoke_post_check
    Plugins-->>Hub: provenance / TEE metadata
    Hub-->>App: result + BOM fields
  end

  App->>Hub: POST /channel/close {channel_id}
  Hub->>Chain: Settle + refund remainder
  Hub-->>App: settlement receipt
```

---

## 6. Desktop product layer

Eight first-party SKUs share [`aicom_desktop_core`](../desktop-integrations/packages/aicom_desktop_core/):

```mermaid
flowchart TB
  CORE["aicom_desktop_core<br/>themes · l10n · wallet bar · backup"]
  SDK["aimarket_agent Dart SDK"]

  subgraph apps["Desktop SKUs"]
    A1["interview-prep-coach"]
    A2["personal-finance-coach"]
    A3["capability-composer"]
    A4["cold-outreach-coach"]
    A5["creator-algorithm-coach"]
    A6["discovery-prospector"]
    A7["freelance-contract-reviewer"]
    A8["reputation-dashboard"]
  end

  HUB["AIMarket Hub"]

  CORE --> apps
  SDK --> apps
  apps -->|"discover · channel · invoke"| HUB
```

Each app: `README.md` + `docs/{value,user-guide,sdk-integration,user-cases}.md`

---

## 7. Plugin composition model

Hub loads plugins via setuptools entry point `aimarket.plugins` ([`plugin.py`](../aimarket-hub/aimarket_hub/plugin.py)):

```mermaid
flowchart LR
  REQ["POST /invoke"] --> PRE["pre-check hooks"]
  PRE --> SAFETY["aimarket-safety"]
  PRE --> ZK["aimarket-zk"]
  PRE --> PROMO["aimarket-promo"]
  PRE --> EXEC["Execute capability"]
  EXEC --> POST["post-check hooks"]
  POST --> PROV["aimarket-provenance"]
  POST --> TEE["aimarket-tee"]
  POST --> REP["aimarket-reputation"]
  POST --> RESP["Response + receipts"]
```

Catalog: [`aimarket-hub/README.md`](../aimarket-hub/README.md#plugin-ecosystem)

---

## 8. Documentation index

| Topic | Document |
|-------|----------|
| Factory pipeline diagrams | [architecture-diagrams.md](./architecture-diagrams.md) |
| Module boundaries | [architecture/module-boundaries.md](./architecture/module-boundaries.md) |
| Protocol v2 (normative) | [aimarket-protocol/spec.md](../aimarket-protocol/spec.md) |
| Factory protocol gateway | [ai-market-protocol-v1.md](./ai-market-protocol-v1.md) |
| Hub production | [production-modelmarket-dev.md](./production-modelmarket-dev.md) |
| Federation report | [FEDERATION_HUB_REPORT.md](./FEDERATION_HUB_REPORT.md) |
| Product value (plain language) | `docs/value.md` in each package |

---

*Regenerate value blurbs: `python3 scripts/bootstrap_product_value.py`*
