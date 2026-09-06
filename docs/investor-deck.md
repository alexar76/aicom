# AI-Factory Investor Deck (Current State)

This document is the investor-facing narrative of the platform as it exists today: what the system does, how control loops work, and why this is commercially scalable.

---

## 1) Executive Snapshot

AI-Factory is an autonomous product engine, not a single app generator.

It combines:
- continuous idea intake and discovery ranking;
- a staged multi-agent delivery pipeline;
- strict quality gates before storefront listing;
- human override controls for governance;
- feedback loops that push real usage signals back into production.

**Core investment thesis:** the moat is operational quality at scale (policy + telemetry + recovery), not one-off generation.

---

## 2) Product System (Block Diagram)

```mermaid
flowchart LR
    A[Idea Intake<br/>support, discovery, briefs] --> B[Discovery Ranking<br/>signals + prioritization]
    B --> C[Multi-Agent Build Pipeline<br/>Analyst -> PM -> Architect/Design -> Developer]
    C --> D[Quality Gates<br/>QA + Security + Release Critic + Marketplace checks]
    D --> E[Storefront & Billing<br/>listing, checkout, plans]
    E --> F[Feedback & Telemetry<br/>usage, support, ratings]
    F --> B
    F --> C
```

**Mechanic:** products flow forward only when passing quality policy; failures and weak outputs are routed back into controlled rework loops.

---

## 3) Governance Mechanics (How Quality Is Enforced)

```mermaid
flowchart TD
    P[Policy Layer<br/>thresholds, gate rules, storefront eligibility] --> X[Pipeline Execution]
    X --> V[Verification Layer<br/>QA, security, hardening]
    V -->|pass| L[Eligible for Listing]
    V -->|fail| R[Rework Queue]
    R --> X
    L --> O[Observe in Production<br/>telemetry + support]
    O --> A[Admin Controls<br/>quality score, follow-up, force-list, human rework]
    A --> P
```

### Key mechanics investors should note
- **Storefront conversion is explicit:** `Completed` and `On storefront` are separate metrics by design.
- **Automated remediation exists:** completed-but-not-listed products can be auto-routed for rework (with configurable limits/modes).
- **Human governance exists:** operators can set follow-up (`planned` / `not_pursuing`), assign quality score, force-list, or trigger manual rework.
- **No blind automation:** policy and admin decisions are persisted and observable in admin APIs and operational logs.

---

## 4) Live Product Surfaces (Screenshots)

### Admin dashboard and conversion visibility
![Admin dashboard](./assets/screenshots/admin-dashboard.png)

### Pipeline monitor (stateful product flow + controls)
![Admin pipeline](./assets/screenshots/admin-pipeline.png)

### Discovery queue (ranked opportunities)
![Admin discovery](./assets/screenshots/admin-discovery.png)

### LLM observability (provider/model/task-level logs)
![Admin LLM logs](./assets/screenshots/admin-llm-logs.png)

### Public growth surface (launch/distribution content)
![Public launch-kit](./assets/screenshots/public-launch-kit.png)

---

## 5) Unit Economics Flywheel (Mechanics)

```mermaid
flowchart LR
    I[More Ideas Ingested] --> S[Faster Structured Delivery]
    S --> M[More Market-Ready Listings]
    M --> R[More Revenue + Feedback]
    R --> G[Better Playbooks + Quality Models]
    G --> I
```

**Why this matters:** every shipped product improves future throughput and conversion by feeding policy, prompts, and rework heuristics.

---

## 6) What Is Already Operational

- Multi-agent staged execution across product lifecycle.
- Persisted pipeline state and recovery/requeue logic.
- Marketplace/listing quality gates with explicit reasons.
- Admin observability stack (pipeline, logs, security, director/discovery).
- Public commercialization surfaces (plans, checkout, referral, launch pages).
- Build/runtime hardening: frontend data loading supports build-safe local fallback to avoid loopback API coupling in image/build phase.

---

## 7) Current Control Plane for Scale

### Human-in-the-loop controls
- mark non-listed outputs as `planned` or `not_pursuing`;
- assign human quality scores;
- force-list selectively when business context justifies it;
- inject manual rework into pipeline for targeted correction.

### Automated control loops
- auto-detect products stuck at `completed` but not eligible for storefront;
- configurable remediation mode (`full` vs `annotate_only`);
- per-cycle caps to avoid unstable mass reprocessing.

**Result:** growth pressure and quality pressure are balanced by policy, not ad hoc operator work.

---

## 8) Due Diligence Talking Points

- **Defensibility:** policy + telemetry + recovery loops produce compounding operational advantage.
- **Scalability:** one control plane governs many generated products with consistent quality criteria.
- **Governability:** admin controls can override or defer automation without losing auditability.
- **Commercial readiness:** listing, distribution pages, and billing stack are integrated with production pipeline outputs.

---

## 9) Related Docs

- `docs/investor-functional-overview.md` — concise functional snapshot.
- `docs/factory-capabilities.md` — complete capability map.
- `docs/factory-metrics-reference.md` — metric definitions and interpretation.
- `docs/admin-guide.md` — admin surfaces and operations reference.
