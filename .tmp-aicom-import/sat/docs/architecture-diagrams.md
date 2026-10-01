# Architecture & pipeline diagrams

Visual reference moved out of the root [README.md](../README.md) during the conversion-focused layout. **Mermaid** blocks render on GitHub, Gitea, and most Markdown viewers.

For a wide competitive feature matrix see **[competitive-analysis.md](./competitive-analysis.md)**. For operator playbooks with more sequence diagrams see **[owner-guide.md](./owner-guide.md)**.

---

## North star (positioning)

Turn a **short plain-language brief** into a **presentable web page** you can share — with **quality gates** (demo/TZ, browser smoke, optional marketplace rules) so sloppy stubs get reworked.

**One pipeline** for everyone:

| Mode | What feeds the pipeline |
|------|-------------------------|
| **Autonomous** | **Discovery** (external signals → validation → scoring) → top idea as `IDEA_RECEIVED` |
| **On-demand** | Customer phrase / Admin → New Product — same downstream stages |

Details: [product-concept.md](./product-concept.md) · [marketing.md](./marketing.md)

---

## Pipeline at a glance (13 worker agents)

```mermaid
flowchart LR
  A[💡 Idea] --> B[🔍 Discovery]
  B --> C[📋 Analyst]
  C --> D[📝 PM]
  D --> E[🎨 Architect]
  E --> F[👨‍💻 Developer]
  F --> G[🧪 QA + E2E]
  G --> H[🔒 Security]
  H --> I[🚀 DevOps]
  I --> J[📢 Marketing]
  J --> K[💰 Sales]
  K --> L[🔄 Evolution]
```

The **pipeline worker** also runs **Design critic** and **Hardening** when `AIFACTORY_EXTENDED_PIPELINE` is enabled — optional hops, not separate rows on Admin → AI Agents (11 roster slots). See [agents.md](./agents.md).

---

## Extended pipeline (gates on the worker graph)

```mermaid
flowchart LR
  Idea[Idea or discovery] --> A[Analyst]
  A --> PM[PM / Spec]
  PM --> AR[Architect + UX brief]
  AR --> DC[Design critic gate]
  DC --> DEV[Developer]
  DEV --> HARD[Hardening]
  HARD --> QA[QA]
  QA --> SEC[Security]
  SEC --> DO[DevOps]
  DO --> MKT[Marketing]
  MKT --> SAL[Sales]
  SAL --> DONE[COMPLETED / Deployed]
```

---

## Product state machine

```mermaid
stateDiagram-v2
  [*] --> IDEA_RECEIVED
  IDEA_RECEIVED --> SPEC_WRITTEN
  SPEC_WRITTEN --> ARCH_DESIGNED
  ARCH_DESIGNED --> CODE_COMMITTED
  CODE_COMMITTED --> QA_TESTED
  QA_TESTED --> SECURITY_SCANNED
  SECURITY_SCANNED --> DEVOPS_DEPLOYED
  DEVOPS_DEPLOYED --> MARKET_CONTENT_READY
  MARKET_CONTENT_READY --> SALES_ACTIVE
  SALES_ACTIVE --> DEPLOYED_PRODUCTION
  DEPLOYED_PRODUCTION --> EVOLUTION_ANALYZING
  EVOLUTION_ANALYZING --> COMPLETED
  QA_TESTED --> DEV_FIXING: peer review block
  DEV_FIXING --> QA_TESTED: developer fix
```

Text chain (compact):  
`IDEA_RECEIVED` → `SPEC_WRITTEN` → `ARCH_DESIGNED` → `CODE_COMMITTED` → `QA_TESTED` → `SECURITY_SCANNED` → `DEVOPS_DEPLOYED` → `MARKET_CONTENT_READY` → `SALES_ACTIVE` → `DEPLOYED_PRODUCTION` → `EVOLUTION_ANALYZING` → `COMPLETED`

---

## Runtime architecture (full)

High-level layout — **full** diagram (README had a shortened copy inside `<details>`).

```mermaid
flowchart TB
  subgraph clients["Clients"]
    U["Public storefront"]
    AD["Admin console"]
  end

  subgraph web["Web tier"]
    FE["Next.js :8080"]
    BE["FastAPI :8081"]
  end

  subgraph workers["Background workers"]
    PW["Pipeline worker"]
    DW["Director AI worker"]
  end

  subgraph agents["Specialized agents"]
    AG["11 Admin roster rows + optional Design critic / Hardening (worker)"]
  end

  subgraph llm["Model routing"]
    RT["LLM router"]
    PR["Providers OpenAI-compatible · local"]
  end

  subgraph data["Persistent workspace: host `./data` mounted at `/app/data`"]
    DB["SQLite pipeline state (JSON fallback in tests)"]
    ART["Specs · arch · code · telemetry · logs"]
  end

  subgraph ops["Observability optional"]
    PRM["Prometheus"]
    GRA["Grafana"]
  end

  U --> FE
  AD --> FE
  FE -->|"HTTP `/api/*`"| BE
  BE --> DB
  BE --> ART
  PW --> DB
  PW --> ART
  PW --> AG
  DW --> DB
  DW --> RT
  AG --> RT
  RT --> PR
  CLI["CLI · ai-company"] -.->|"orchestration"| PW
  BE --> PRM
  PRM --> GRA
```

Compose maps container **8080/8081** → host **9080/9081**. Deep dive: [architecture-orchestrator.md](./architecture-orchestrator.md).

---

## Public site vs Admin (same deployment)

```mermaid
flowchart TB
  subgraph Public["Public (no admin JWT)"]
    SF[Storefront Next.js]
    API_P["/api/products, /api/sandbox, /api/support …"]
  end
  subgraph Admin["Admin (JWT)"]
    ADM["/admin SPA"]
    API_A["/api/admin/*"]
  end
  subgraph Runtime["Same deployment"]
    PY[FastAPI :8081]
    WORK[Pipeline worker + Director]
    DATA[("/app/data bind mount")]
  end
  SF --> API_P
  ADM --> API_A
  API_P --> PY
  API_A --> PY
  PY --> DATA
  WORK --> DATA
```

---

## Discovery (pre-pipeline)

```mermaid
flowchart LR
  S[Signal collector\nReddit · HN · GitHub · …] --> V[Need validation]
  V --> SC[Idea scorecard]
  SC --> R[Ranked ideas]
  R --> E[Enqueue IDEA_RECEIVED]
```

Engine: `director/discovery_pipeline.py` · Ops: [pipeline-operations.md](./pipeline-operations.md)

---

## Storefront listing decision

```mermaid
flowchart TD
  Q{Passes code + quality gates?}
  Q -->|yes| LIST[Listed on storefront]
  Q -->|no| F{Admin force-list + note?}
  F -->|yes| LIST
  F -->|no| HID{Hidden or not pursuing?}
  HID -->|yes| OFF[Not listed + GET product 404]
  HID -->|no| WAIT[Not listed — see gate reasons in admin]
```

---

## Operator: enqueue one product

```mermaid
sequenceDiagram
  participant You
  participant Admin
  participant API
  participant Worker
  You->>Admin: New Product → submit idea
  Admin->>API: POST create product
  API->>Worker: enqueue tasks
  Worker-->>Admin: stage updates in Pipeline tab
  You->>Admin: Pipeline → expand card → inspect tasks / errors
```

---

## Compared to hosted AI app builders

Hosted builders (Bolt.new, Lovable, v0, Devin) and AI-Factory solve different problems. Hosted products give a polished editor, team accounts, integrations, and pay-per-seat pricing; AI-Factory gives a **self-hosted MIT pipeline** with your own LLM keys, on-disk artifacts/state, Playwright E2E + security gates, an optional human gate, and a public storefront — at the cost of running Docker and bringing your own keys. Don’t treat this as a head-to-head ranking — pick by which trade-off matches your context, and verify vendor pricing/features yourself.

---

## Observability (Grafana overview)

When Compose includes Prometheus + Grafana (`./run-compose.sh`), the **AI Factory Overview** dashboard includes:

| Row | Panels |
|-----|--------|
| **Pipeline overview** | Active products · Total created (24h) · Pending tasks · Failed tasks (24h) |
| **Products by state** | Pie chart of pipeline states |
| **Tasks & performance** | Tasks by status · Task duration P99 · Avg duration by agent |
| **Director AI** | Decisions (24h) · Analysis duration |
| **LLM health** | Requests by provider · Error rate · Provider UP/DOWN · Latency P95 |

Default URLs (host): App **9080** · API **9081** · Prometheus **9090** · Grafana **9082**.

---

## Related docs

| Topic | File |
|-------|------|
| Orchestrator / worker split | [architecture-orchestrator.md](./architecture-orchestrator.md) |
| Agent roster | [agents.md](./agents.md) |
| Factory feature map | [factory-capabilities.md](./factory-capabilities.md) |
| Investor narrative + diagrams | [investor-deck.md](./investor-deck.md) |
