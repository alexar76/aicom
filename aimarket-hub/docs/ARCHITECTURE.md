# AIMarket Hub — Architecture & Interaction Diagrams

## System Overview

```mermaid
graph TB
    subgraph External["🌐 External"]
        AGENT["🤖 AI Agent<br/>(Claude/GPT/Cursor)"]
        USER["👤 User<br/>(Browser/CLI)"]
        BLOG["📝 Blog<br/>(Widget embedded)"]
    end

    subgraph Factory["🏭 AI-Factory (closed core)"]
        PIPELINE["⚙️ 13-agent Pipeline"]
        STOREFRONT["🛒 Storefront<br/>(Next.js)"]
        ADMIN["🔧 Admin Panel"]
    end

    subgraph Hub["🔄 AIMarket Hub (Apache-2.0)"]
        direction TB
        WK["📋 .well-known<br/>GET /ai-market.json"]
        CRAWLER["🕷️ Crawler<br/>(BFS daemon)"]
        INDEXER["🗄️ Indexer<br/>(SQLite)"]
        SEARCH["🔍 Search API<br/>/v2/search"]
        ROUTER["🚦 Routing Proxy<br/>/v2/invoke"]
        SAFETY["🛡️ Safety Gate<br/>(pre/post invoke)"]
        TRUST["⭐ Trust Scorer<br/>(age+bond+success+volume)"]
        VALIDATOR["✅ Schema Validator<br/>(JSON Schema)"]
        SIGNER["🔐 Signer<br/>(Ed25519)"]
        STATS["📊 Live Stats<br/>/v2/stats/live"]
        EXPORTER["📦 Dataset Exporter<br/>(weekly JSONL)"]
    end

    subgraph Federation["🌍 Federation Network"]
        HUB2["Hub 2<br/>Legal AI"]
        HUB3["Hub 3<br/>DeFi AI"]
        HUB4["Hub N...<br/>Any provider"]
    end

    subgraph Chain["⛓️ Blockchain"]
        BASE["Base L2<br/>(USDT settlement)"]
        ETH["Ethereum<br/>(USDC settlement)"]
    end

    %% Flows
    AGENT -->|"① GET .well-known"| WK
    AGENT -->|"② Discover"| SEARCH
    AGENT -->|"③ Invoke (402)"| ROUTER
    USER -->|"Browser"| STOREFRONT
    BLOG -->|"Widget"| ROUTER
    STOREFRONT -->|"Federated catalog"| SEARCH
    ADMIN -->|"Manage"| CRAWLER
    PIPELINE -->|"Products → capabilities"| INDEXER

    CRAWLER -->|"Crawl .well-known"| HUB2
    CRAWLER -->|"Crawl .well-known"| HUB3
    CRAWLER -->|"Discover"| HUB4
    CRAWLER -->|"Index manifests"| INDEXER
    INDEXER -->|"Store"| SEARCH
    INDEXER -->|"Store"| TRUST

    ROUTER -->|"Pre-check"| SAFETY
    SAFETY -->|"Pass"| ROUTER
    SAFETY -->|"Block → refund"| ROUTER
    ROUTER -->|"Forward invoke"| HUB2
    ROUTER -->|"Return receipt"| AGENT

    TRUST -->|"Score peers"| INDEXER
    VALIDATOR -->|"Validate"| CRAWLER
    SIGNER -->|"Sign manifests"| WK
    SIGNER -->|"Sign receipts"| ROUTER
    STATS -->|"Live feed"| USER
    EXPORTER -->|"Weekly corpus"| USER

    ROUTER -->|"Settlement"| BASE
    ROUTER -->|"Settlement"| ETH

    style Hub fill:#1a1a2e,stroke:#6c5ce7,color:#e0e0e0
    style Factory fill:#16213e,stroke:#0f3460,color:#e0e0e0
    style Federation fill:#0f3460,stroke:#e94560,color:#e0e0e0
    style External fill:#533483,stroke:#e94560,color:#e0e0e0
    style Chain fill:#1b1b2f,stroke:#f5c518,color:#e0e0e0
```

---

## Autonomous Invoke Cycle (Full Flow)

```mermaid
sequenceDiagram
    participant Agent as 🤖 AI Agent
    participant Hub as 🔄 Routing Hub
    participant Safety as 🛡️ Safety Gate
    participant Provider as 🏭 Provider Hub
    participant Chain as ⛓️ Blockchain

    Note over Agent,Chain: Phase 1 — Discovery

    Agent->>Hub: GET /.well-known/ai-market.json
    Hub-->>Agent: { name, manifest_url, federation, peers }

    Agent->>Hub: GET /ai-market/v2/manifest
    Hub-->>Agent: { tools: [...all capabilities...], signature }

    Agent->>Hub: POST /ai-market/v2/search?intent=translate&budget=3.00
    Hub-->>Agent: { matches: [...ranked by trust+price...] }

    Note over Agent,Chain: Phase 2 — Payment Channel

    Agent->>Chain: Deposit $3.00 USDT
    Chain-->>Agent: tx_hash: 0x...
    Agent->>Hub: POST /ai-market/channel/open { deposit: 3.00, tx_hash }
    Hub-->>Agent: { channel_id: ch_abc123, balance: 3.00 }

    Note over Agent,Chain: Phase 3 — Invoke with Safety Gate

    Agent->>Hub: POST /ai-market/v2/invoke<br/>X-Payment-Channel: ch_abc123<br/>{ product_id, capability_id, input }

    Hub->>Safety: pre_invoke_check(input)
    alt Input flagged (injection/PII/medical)
        Safety-->>Hub: BLOCKED: class:injection
        Hub-->>Agent: 403 { error: safety_blocked, rejection_receipt, refund }
    else Input clean
        Safety-->>Hub: PASS

        Hub->>Provider: Forward invoke<br/>X-AIMarket-Routing-Hub: hub_url<br/>X-AIMarket-Routing-Fee: 100

        alt Provider requires payment
            Provider-->>Hub: 402 Payment Required
            Hub-->>Agent: 402 { payment_required, amount, recipient }
            Agent->>Chain: Sign & send tx
            Agent->>Hub: Retry with X-Payment: { tx_hash }
            Hub->>Provider: Forward with payment proof
        end

        Provider-->>Hub: 200 { success, result, receipt, price, latency }

        Hub->>Safety: post_response_check(result)
        alt Response flagged (PII leak/harmful)
            Safety-->>Hub: BLOCKED: class:PII
            Hub-->>Agent: 403 { error: safety_blocked_response, refund }
        else Response clean
            Safety-->>Hub: PASS
            Hub-->>Agent: 200 { success, result, receipt, safety_checked }
        end
    end

    Note over Agent,Chain: Phase 4 — Settlement

    Agent->>Hub: POST /ai-market/channel/close<br/>{ channel_id, settle_tx_hash }
    Hub-->>Agent: { settlement: { used: $1.60, refund: $1.40 } }

    Note over Agent,Chain: Phase 5 — Audit Trail

    Agent->>Agent: Save signed bill_of_materials.json<br/>(receipts + safety attestations)

    Note over Agent,Chain: ✅ Full autonomous cycle complete
```

---

## Federation Crawl Protocol

```mermaid
sequenceDiagram
    participant Crawler as 🕷️ Crawler
    participant Seed as 🌱 Seed Hub
    participant Peer2 as 🔗 Peer Hub 2
    participant Peer3 as 🔗 Peer Hub 3
    participant DB as 🗄️ Local Index

    Note over Crawler,DB: BFS Crawl Cycle (every 3600s)

    Crawler->>Seed: GET /.well-known/ai-market.json<br/>User-Agent: AIMarketHub/2.0.0
    Seed-->>Crawler: { name, manifest_url, peers: [Hub2, Hub3] }

    Crawler->>DB: Validate well-known (JSON Schema)
    Crawler->>DB: Upsert peer (Seed)

    Crawler->>Seed: GET /ai-market/manifest
    Seed-->>Crawler: { tools: [...], signature: {...} }

    Crawler->>Crawler: Verify Ed25519 signature
    Crawler->>Crawler: Validate each capability (JSON Schema)

    loop For each capability
        Crawler->>DB: Upsert capability<br/>(source_hub=Seed, routed_price=price*1.01)
    end

    Note over Crawler: Discover new peers from Seed's response

    Crawler->>Peer2: GET /.well-known/ai-market.json (depth=1)
    Peer2-->>Crawler: { ...capabilities, peers: [Hub4] }

    Crawler->>Peer3: GET /.well-known/ai-market.json (depth=1)
    Peer3-->>Crawler: { ...capabilities, peers: [] }

    Crawler->>Peer2: GET /ai-market/manifest
    Peer2-->>Crawler: { tools: [...], signature }

    Crawler->>Peer3: GET /ai-market/manifest
    Peer3-->>Crawler: { tools: [...], signature }

    Note over Crawler: Max depth reached (3), stop BFS

    Crawler->>DB: Compute trust scores for all peers
    Crawler->>DB: Store federation stats

    Note over Crawler,DB: ✅ Crawl complete: 3 hubs, N capabilities
```

---

## Safety Gate Decision Tree

```mermaid
flowchart TD
    START([Invoke Request]) --> PRE{Pre-Invoke<br/>Safety Check}

    PRE -->|"Injection patterns?"| INJ_CHECK{"CRITICAL ≥ 1<br/>or STRONG ≥ 2?"}
    INJ_CHECK -->|Yes| BLOCK_INJ[❌ BLOCK<br/>class:injection]
    INJ_CHECK -->|No| PII_CHECK{"PII patterns?<br/>(SSN, email, card)"}

    PII_CHECK -->|Yes + blocked| BLOCK_PII[❌ BLOCK<br/>class:PII]
    PII_CHECK -->|No| MED_CHECK{"Medical terms?<br/>(≥2 matches)"}

    MED_CHECK -->|Yes + blocked| BLOCK_MED[❌ BLOCK<br/>class:medical]
    MED_CHECK -->|No| CHILD_CHECK{"Children's data?"}

    CHILD_CHECK -->|Yes + blocked| BLOCK_CHILD[❌ BLOCK<br/>class:children]
    CHILD_CHECK -->|No| LEN_CHECK{"Input > max_length?"}

    LEN_CHECK -->|Yes| BLOCK_LEN[❌ BLOCK<br/>class:constitutional]
    LEN_CHECK -->|No| EXECUTE[▶ EXECUTE<br/>Capability]

    EXECUTE --> POST{Post-Response<br/>Safety Check}
    POST -->|"PII in output?"| OUT_PII{"PII leaked?"}
    OUT_PII -->|Yes| BLOCK_OUT[❌ BLOCK<br/>class:PII leak]
    OUT_PII -->|No| HARASS{"Harmful content?"}
    HARASS -->|Yes| BLOCK_HARM[❌ BLOCK<br/>class:harassment]
    HARASS -->|No| PASS([✅ RETURN RESULT<br/>+ signed receipt])

    BLOCK_INJ --> REFUND1[💰 Refund Channel]
    BLOCK_PII --> REFUND2[💰 Refund Channel]
    BLOCK_MED --> REFUND3[💰 Refund Channel]
    BLOCK_CHILD --> REFUND4[💰 Refund Channel]
    BLOCK_LEN --> REFUND5[💰 Refund Channel]
    BLOCK_OUT --> REFUND6[💰 Refund Channel]
    BLOCK_HARM --> REFUND7[💰 Refund Channel]

    REFUND1 --> REJECT[📝 Sign Rejection Receipt]
    REFUND2 --> REJECT
    REFUND3 --> REJECT
    REFUND4 --> REJECT
    REFUND5 --> REJECT
    REFUND6 --> REJECT
    REFUND7 --> REJECT

    REJECT --> RETURN([🔙 403 Response<br/>+ signed rejection receipt])

    style START fill:#1a1a2e,stroke:#6c5ce7,color:#fff
    style EXECUTE fill:#0f3460,stroke:#3b82f6,color:#fff
    style PASS fill:#064e3b,stroke:#22c55e,color:#fff
    style BLOCK_INJ fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_PII fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_MED fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_CHILD fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_LEN fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_OUT fill:#3b1f1f,stroke:#ef4444,color:#fff
    style BLOCK_HARM fill:#3b1f1f,stroke:#ef4444,color:#fff
```

---

## Data Model (Entity Relationships)

```mermaid
erDiagram
    PEER ||--o{ CAPABILITY : "hosts"
    PEER {
        string url PK
        string name
        int capabilities_count
        string last_crawl
        float trust_score
        int depth
        string discoverer
    }

    CAPABILITY {
        int id PK
        string capability_id
        string product_id
        string name
        string version
        string description
        json input_schema
        json output_schema
        float price_per_call_usd
        int p50_latency_ms
        float success_rate_30d
        string source_hub FK
        float routed_price_usd
        int routing_fee_bps
        float trust_score
    }

    INVOCATION_STATS ||--o{ CAPABILITY : "tracks"
    INVOCATION_STATS {
        int id PK
        string capability_id
        string product_id
        string source_hub
        float price_usd
        int latency_ms
        bool success
        string timestamp
        string consumer_hub
    }

    REPUTATION_EVENTS ||--o{ PEER : "about"
    REPUTATION_EVENTS {
        int id PK
        string event_type
        string provider_hub FK
        string capability_id
        string timestamp
        float price_usd
        int latency_ms
        string consumer_hub
        string signature
    }

    PEER ||--o{ REPUTATION_EVENTS : "receives"
```

---

## Deployment Topology

```mermaid
graph TB
    subgraph Internet["🌐 Public Internet"]
        CDN["📦 CDN<br/>(widget.js)"]
        DNS["🔗 modelmarket.dev"]
    end

    subgraph VPS["🖥️ VPS / Cloud"]
        subgraph Docker["🐳 Docker Compose"]
            HUB["🔄 aimarket-hub<br/>:9080"]
            DB["🗄️ SQLite<br/>(/app/data/hub.db)"]
        end
        NGINX["🔀 Nginx<br/>(reverse proxy, TLS)"]
    end

    subgraph Peers["🌍 Federated Peers"]
        P1["Hub A"]
        P2["Hub B"]
        P3["Hub C"]
    end

    subgraph Factory["🏭 AI-Factory"]
        FW["Web Backend<br/>(FastAPI)"]
        FE["Storefront<br/>(Next.js)"]
    end

    DNS --> NGINX
    NGINX --> HUB
    HUB --> DB
    HUB -->|"Crawl"| P1
    HUB -->|"Crawl"| P2
    HUB -->|"Crawl"| P3
    HUB -->|"Bridge"| FW
    CDN -->|"widget.js"| FE
    FE -->|"API calls"| HUB
    FW -->|"Export products"| HUB

    style Docker fill:#1a1a2e,stroke:#6c5ce7,color:#e0e0e0
    style Internet fill:#0f3460,stroke:#e94560,color:#e0e0e0
    style Factory fill:#16213e,stroke:#3b82f6,color:#e0e0e0
```

---

## Widget Embed Lifecycle

```mermaid
sequenceDiagram
    participant Blog as 📝 Blog Page
    participant Widget as 🧩 Widget (JS)
    participant Hub as 🔄 Hub API
    participant Provider as 🏭 Capability Provider

    Note over Blog,Provider: Page Load

    Blog->>Widget: <script src="widget.js"<br/>data-intent="summarize"<br/>data-theme="cyber"<br/>data-affiliate-id="my_blog">

    Widget->>Widget: Render search UI<br/>(theme: cyber)

    Note over Blog,Provider: User Interaction

    Blog->>Widget: User types "summarize this article"
    Widget->>Hub: GET /v2/search?intent=summarize&limit=6
    Hub-->>Widget: { matches: [3 capabilities] }
    Widget->>Widget: Render capability cards<br/>(price, trust, latency)

    Blog->>Widget: User clicks "Try" on summarize@v1

    Widget->>Hub: POST /ai-market/channel/open<br/>{ deposit: 1.00, tx_hash: "demo-..." }
    Hub-->>Widget: { channel_id: ch_xyz }

    Widget->>Hub: POST /v2/invoke<br/>X-Payment-Channel: ch_xyz<br/>X-AIMarket-Affiliate: my_blog<br/>{ capability_id: "summarize@v1", input: {text: "..."} }

    Hub->>Hub: Safety gate: pre_invoke_check ✓
    Hub->>Provider: Forward invoke
    Provider-->>Hub: 200 { result: "Summary text..." }
    Hub->>Hub: Safety gate: post_response_check ✓

    Hub-->>Widget: 200 { success, result, receipt, safety_checked }

    Widget->>Widget: Show result<br/>+ "Earned $0.015 for my_blog"
    Widget->>Widget: Show "Powered by aimarket-hub"

    Widget->>Hub: POST /ai-market/channel/close<br/>{ channel_id: ch_xyz }
    Hub-->>Widget: { settlement: { used: 0.05, refund: 0.95 } }

    Note over Blog,Provider: ✅ Affiliate: my_blog earns 30% of $0.05 = $0.015
```

---

## Trust Score Computation Flow

```mermaid
flowchart LR
    subgraph Inputs["📥 Data Sources"]
        AGE["📅 Hub Age<br/>(days since first crawl)"]
        BOND["💰 Economic Bond<br/>(USDT staked)"]
        SUCCESS["✅ Success Rate<br/>(30-day window)"]
        VOLUME["📊 Volume<br/>(USD in 30 days)"]
    end

    subgraph Normalize["📐 Normalize (0..1)"]
        AF["age_factor<br/>= min(days/365, 1.0)"]
        BF["bond_factor<br/>= min(log10($)/4, 1.0)"]
        SR["success_rate<br/>= ok/total"]
        VF["volume_factor<br/>= min(log10($)/5, 1.0)"]
    end

    subgraph Weights["⚖️ Weighted Sum"]
        W1["w1 = 0.20"]
        W2["w2 = 0.30"]
        W3["w3 = 0.35"]
        W4["w4 = 0.15"]
    end

    subgraph Output["📤 Trust Score"]
        SCORE["trust_score<br/>= Σ(weight × factor)<br/>Range: 0.0 – 1.0"]
    end

    AGE --> AF --> W1
    BOND --> BF --> W2
    SUCCESS --> SR --> W3
    VOLUME --> VF --> W4
    W1 --> SCORE
    W2 --> SCORE
    W3 --> SCORE
    W4 --> SCORE

    style Inputs fill:#1a1a2e,stroke:#6c5ce7,color:#e0e0e0
    style Normalize fill:#0f3460,stroke:#3b82f6,color:#e0e0e0
    style Weights fill:#16213e,stroke:#e94560,color:#e0e0e0
    style Output fill:#064e3b,stroke:#22c55e,color:#e0e0e0
```
