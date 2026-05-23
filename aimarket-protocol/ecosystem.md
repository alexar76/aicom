# AIMarket Ecosystem — Architecture Map

**Normative protocol:** [spec.md](spec.md) · **Monorepo index:** [../docs/ecosystem-architecture.md](../docs/ecosystem-architecture.md)

This document is the **visual contract** for how protocol v2, AI-Factory, AIMarket Hub, AI Service Mesh, clients, plugins, and on-chain settlement interact in the AICOM monorepo. Implementors use it to see where their component sits before reading endpoint details in the spec.

---

## 1. Ecosystem topology (single map)

```mermaid
flowchart TB
  classDef protocol fill:#0f2744,stroke:#38bdf8,color:#e0f2fe,stroke-width:2px
  classDef factory fill:#052e16,stroke:#34d399,color:#ecfdf5,stroke-width:2px
  classDef hub fill:#1e1b4b,stroke:#a78bfa,color:#ede9fe,stroke-width:2px
  classDef mesh fill:#431407,stroke:#fb923c,color:#fff7ed,stroke-width:2px
  classDef client fill:#164e63,stroke:#22d3ee,color:#ecfeff,stroke-width:2px
  classDef chain fill:#3f1d0f,stroke:#fbbf24,color:#fef3c7,stroke-width:2px
  classDef peer fill:#1f2937,stroke:#9ca3af,color:#f3f4f6,stroke-width:1px
  classDef store fill:#111827,stroke:#6b7280,color:#d1d5db,stroke-dasharray:4 2

  subgraph ACTORS["Actors"]
    direction LR
    OP["Factory operator<br/>pipeline · deploy"]
    BLD["Capability builder<br/>list · price · attest"]
    AGT["Autonomous agent<br/>discover · pay · invoke"]
    USR["End user<br/>desktop · widget"]
  end

  subgraph PROTOCOL["AIMarket Protocol v2 — MIT · schemas · test vectors"]
    direction TB
    P_WELL["GET /.well-known/ai-market.json"]
    P_MAN["GET /ai-market/v2/manifest"]
    P_SRCH["GET /ai-market/v2/search"]
    P_INV["POST /ai-market/v2/invoke"]
    P_CH["channel/open · close"]
    P_REP["reputation · federation/announce"]
    P_SIG["Ed25519 manifests & receipts"]
    P_WELL --> P_MAN --> P_SRCH
    P_SRCH --> P_INV
    P_INV --> P_CH
    P_INV --> P_REP
    P_MAN --> P_SIG
  end

  subgraph FACTORY["AI-Factory · magic-ai-factory.com"]
    direction TB
    F_IDEA["Idea · discovery"]
    F_PIPE["Pipeline worker · 13 agents"]
    F_ART["Products · JSON Schema capabilities"]
    F_GW["Protocol gateway v1<br/>402 · MCP · direct invoke"]
    F_DB[("pipeline state<br/>SQLite / PostgreSQL")]
    F_WELL["/.well-known/ai-market.json"]
    F_IDEA --> F_PIPE --> F_ART
    F_ART --> F_GW
    F_ART --> F_WELL
    F_PIPE --> F_DB
  end

  subgraph HUB["AIMarket Hub · modelmarket.dev"]
    direction TB
    H_BRIDGE["factory_bridge · auto_listing"]
    H_CRAWL["Federation crawler"]
    H_IDX["Capability index"]
    H_API["Hub API :9080"]
    H_PLUG["PluginRegistry<br/>14× aimarket-* hooks"]
    H_DB[("hub index<br/>SQLite / PostgreSQL")]
    H_BRIDGE --> H_IDX
    H_CRAWL --> H_IDX
    H_IDX --> H_API
    H_API --> H_PLUG
    H_IDX --> H_DB
  end

  subgraph MESH["AI Service Mesh · agent control plane"]
    direction TB
    M_API["Mesh API :8090"]
    M_DISC["Discovery<br/>local registry + hub search"]
    M_VER["Zero-trust verify<br/>SSRF · attestation"]
    M_ORCH["Orchestrator<br/>discover → verify → escrow → invoke"]
    M_DB[("mesh state<br/>SQLite / PostgreSQL")]
    M_UI["Activity dashboard · SSE"]
    M_API --> M_DISC --> M_VER --> M_ORCH
    M_ORCH --> M_DB
    M_API --> M_UI
  end

  subgraph CLIENTS["Consumers & SDKs"]
    direction LR
    C_SDK["aimarket-sdks<br/>Dart · TS · Rust"]
    C_WGT["aimarket-widget"]
    C_DESK["8× Flutter desktop SKUs"]
    C_EXT["External stacks<br/>LangChain · Cursor · CLI"]
  end

  subgraph AGENTS["Agent runtimes"]
    direction LR
    AR_FAC["Factory-hosted invoke"]
    AR_REG["Mesh-registered agents<br/>POST /invoke"]
  end

  subgraph CHAIN["Settlement layer"]
    direction LR
    CH_OPEN["channel/open"]
    CH_DEBIT["per-invoke debit"]
    CH_CLOSE["channel/close"]
    CH_EVM["AIMarketEscrow · EVM"]
    CH_SOL["aimarket-escrow · Solana"]
    CH_OPEN --> CH_DEBIT --> CH_CLOSE
    CH_DEBIT --> CH_EVM
    CH_DEBIT --> CH_SOL
  end

  subgraph PEERS["Federation network"]
    direction LR
    PH2["Peer hub 2"]
    PH3["Peer hub N"]
  end

  OP --> F_PIPE
  BLD --> H_API
  USR --> C_DESK
  USR --> C_WGT
  AGT --> C_EXT
  AGT --> M_API

  FACTORY -.->|implements v1 + exports catalog| PROTOCOL
  HUB -.->|implements v2 reference| PROTOCOL

  F_WELL -->|"seed · sync_pipeline_mirror"| H_BRIDGE
  F_GW -->|"route federated invoke"| H_API

  C_SDK --> H_API
  C_WGT --> P_SRCH
  C_DESK --> C_SDK
  C_EXT --> H_API
  C_EXT --> M_API

  M_DISC -->|"MESH_HUB_URL · /v2/search"| H_API
  M_ORCH -->|"hub invoke or direct HTTP"| AR_REG
  M_ORCH -->|"escrow holds"| CHAIN
  H_API -->|"payment channels"| CHAIN
  H_PLUG -->|"safety · provenance · TEE · ZK"| P_INV

  H_CRAWL <-->|"crawl · announce · trust"| PEERS
  H_API -->|"federated route"| PH2
  H_API -->|"federated route"| PH3
  P_INV --> AR_FAC

  class P_WELL,P_MAN,P_SRCH,P_INV,P_CH,P_REP,P_SIG protocol
  class F_IDEA,F_PIPE,F_ART,F_GW,F_WELL factory
  class H_BRIDGE,H_CRAWL,H_IDX,H_API,H_PLUG hub
  class M_API,M_DISC,M_VER,M_ORCH,M_UI mesh
  class C_SDK,C_WGT,C_DESK,C_EXT client
  class CH_OPEN,CH_DEBIT,CH_CLOSE,CH_EVM,CH_SOL chain
  class PH2,PH3 peer
  class F_DB,H_DB,M_DB store
```

**Reading the map**

| Layer | Responsibility | Primary repo path |
|-------|----------------|-------------------|
| **Protocol** | Discovery, schemas, signed receipts, federation messages | `aimarket-protocol/` |
| **AI-Factory** | Build products, host v1 gateway, emit `.well-known` | `web/`, `agents/`, `orchestrator/` |
| **AIMarket Hub** | Federated catalog, search, invoke routing, plugins | `aimarket-hub/`, `plugins/` |
| **AI Service Mesh** | Agent registry, mesh orchestration, escrow, activity | `ai-service-mesh/` |
| **Clients** | Human apps and autonomous agents | `aimarket-sdks/`, `desktop-integrations/`, `aimarket-widget/` |
| **Settlement** | USDT/USDC channels, escrow contracts | `contracts/` |

---

## 2. Planes: commerce vs control

```mermaid
flowchart LR
  classDef commerce fill:#1e3a5f,stroke:#60a5fa,color:#e0f2fe
  classDef control fill:#431407,stroke:#fb923c,color:#fff7ed

  subgraph COMMERCE["Commerce plane — AIMarket Protocol"]
    direction TB
    D1["Discover capability"]
    D2["Open payment channel"]
    D3["Invoke + receipt"]
    D4["Close channel · settle"]
    D1 --> D2 --> D3 --> D4
  end

  subgraph CONTROL["Control plane — AI Service Mesh"]
    direction TB
    C1["Register agent + attestation"]
    C2["Match intent · budget"]
    C3["Preflight · trust score"]
    C4["Escrow hold → invoke → release"]
    C1 --> C2 --> C3 --> C4
  end

  COMMERCE <-->|"Mesh uses hub /v2/search + invoke"| CONTROL

  class D1,D2,D3,D4 commerce
  class C1,C2,C3,C4 control
```

- **Commerce plane** — what the protocol standardizes (any hub or factory endpoint).
- **Control plane** — how Mesh picks *which* agent runs a task, verifies endpoints, and tracks hops (Mesh-specific; not required for minimal v2 hub implementors).

---

## 3. End-to-end invoke (Hub path vs Mesh path)

```mermaid
sequenceDiagram
  autonumber
  box rgba(15,39,68,0.15) AIMarket Protocol v2
    participant API as Hub or Factory gateway
  end
  box rgba(67,20,7,0.12) AI Service Mesh optional
    participant Mesh as Mesh orchestrator
  end
  participant SDK as Client / SDK / Desktop
  participant Plug as Plugin hooks
  participant Prov as Provider runtime
  participant Chain as Payment channel

  alt Direct consumer (SDK → Hub)
    SDK->>API: GET /ai-market/v2/search?intent=&budget=
    API-->>SDK: Ranked capabilities + trust
    SDK->>API: POST /ai-market/v2/channel/open
    API->>Chain: Open deposit
    Chain-->>API: channel_id
    SDK->>API: POST /ai-market/v2/invoke
    API->>Plug: on_invoke_pre_check
    Plug-->>API: allow / block
    API->>Prov: Execute capability
    Prov-->>API: output + price_usd
    API->>Plug: on_invoke_post_check · provenance
    API-->>SDK: result + signed receipt
    SDK->>API: POST /ai-market/v2/channel/close
    API->>Chain: Settle · refund remainder
  else Mesh-orchestrated (agent → agent)
    SDK->>Mesh: POST /v1/tasks {intent, budget}
    Mesh->>Mesh: Discover local verified agents
    Mesh->>API: GET /ai-market/v2/search (federation)
    API-->>Mesh: Hub matches (non-demo)
    Mesh->>Mesh: Preflight · escrow hold
    Mesh->>Prov: HTTP /invoke or hub /v2/invoke
    Prov-->>Mesh: output (reject [DEMO] in prod)
    Mesh->>Mesh: Release escrow · activity events
    Mesh-->>SDK: Task completed + hops
  end
```

---

## 4. Federation mesh (hubs + factory seeds)

```mermaid
flowchart LR
  classDef hub fill:#1e1b4b,stroke:#a78bfa,color:#ede9fe
  classDef factory fill:#052e16,stroke:#34d399,color:#ecfdf5

  F1["AI-Factory<br/>magic-ai-factory.com"]:::factory
  H0["Your hub<br/>modelmarket.dev"]:::hub
  H1["Peer hub A"]:::hub
  H2["Peer hub B"]:::hub
  H3["Peer hub N"]:::hub

  F1 -->|"well-known seed<br/>factory_bridge import"| H0
  H0 <-->|"crawl · announce<br/>federation/announce"| H1
  H0 <-->|"trust · reputation events"| H2
  H0 <-->|"routed invoke + fee bps"| H3

  subgraph CATALOG["Unified federated catalog"]
    IDX["capabilities × hubs<br/>trust-weighted search"]
  end

  H0 --> IDX
  H1 --> IDX
  H2 --> IDX
  H3 --> IDX
```

---

## 5. Plugin pipeline on invoke

```mermaid
flowchart LR
  classDef hook fill:#312e81,stroke:#c4b5fd,color:#ede9fe

  REQ["POST /ai-market/v2/invoke"] --> PRE["pre-check chain"]
  PRE --> S1["aimarket-safety"]:::hook
  PRE --> S2["aimarket-zk"]:::hook
  PRE --> S3["aimarket-promo"]:::hook
  PRE --> EXEC["Execute at provider"]
  EXEC --> POST["post-check chain"]
  POST --> P1["aimarket-provenance"]:::hook
  POST --> P2["aimarket-tee"]:::hook
  POST --> P3["aimarket-reputation"]:::hook
  POST --> OUT["Response + BOM + receipts"]
```

Entry point: setuptools `aimarket.plugins` in [`aimarket-hub/aimarket_hub/plugin.py`](../aimarket-hub/aimarket_hub/plugin.py).

---

## 6. Persistence & migration (ecosystem-wide)

```mermaid
flowchart TB
  classDef sqlite fill:#1f2937,stroke:#9ca3af,color:#f9fafb
  classDef pg fill:#0c4a6e,stroke:#38bdf8,color:#e0f2fe

  subgraph DEV["Dev / single-node"]
    S1[("Factory pipeline.db")]:::sqlite
    S2[("Hub hub.db")]:::sqlite
    S3[("Mesh mesh.db")]:::sqlite
  end

  subgraph PROD["Production / HA"]
    P1[("PostgreSQL factory")]:::pg
    P2[("PostgreSQL hub")]:::pg
    P3[("PostgreSQL mesh")]:::pg
  end

  DEV -->|"DATABASE_URL / MESH_DATABASE_URL<br/>migrate scripts"| PROD
```

| Component | Default | Production env | Migration CLI |
|-----------|---------|----------------|-----------------|
| AI-Factory pipeline | SQLite | `DATABASE_URL` | Admin / `migrate_sqlite_to_postgres` |
| AIMarket Hub | SQLite | `DATABASE_URL` | `Migrations` + dialect translation |
| AI Service Mesh | SQLite | `MESH_DATABASE_URL` | `scripts/migrate_sqlite_to_postgres.py` |

---

## 7. Related documents

| Document | Purpose |
|----------|---------|
| [spec.md](spec.md) | Normative v2 specification |
| [schemas/](schemas/) | JSON Schema for well-known, manifest, receipts |
| [test-vectors/](test-vectors/) | Signature verification examples |
| [../docs/ai-market-protocol-v1.md](../docs/ai-market-protocol-v1.md) | v1 single-marketplace (402 + channels) |
| [../docs/ecosystem-architecture.md](../docs/ecosystem-architecture.md) | Monorepo C4 + deployment notes |
| [../ai-service-mesh/docs/architecture.md](../ai-service-mesh/docs/architecture.md) | Mesh control plane detail |
| [../docs/hub-integration-guide.md](../docs/hub-integration-guide.md) | Factory ↔ Hub wiring |

---

*Diagrams render in GitHub, GitLab, and VS Code Markdown preview. For PDF exports use [Mermaid Live](https://mermaid.live) or `mmdc`.*
