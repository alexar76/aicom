# Pipeline operations

> Full guide: [`docs/pipeline-operations.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/pipeline-operations.md)

## Worker wake model

The pipeline worker is **event-driven**, not poll-only:

1. **watchfiles** — watches `pipeline.json` / `pipeline.db`
2. **`POST /wake`** on worker `:8091` after state writes (`AIFACTORY_PIPELINE_WORKER_WAKE=1`)
3. **Adaptive poll** — fast when busy (`AIFACTORY_PIPELINE_ACTIVE_POLL_SEC`), slow when idle

Health: `GET http://127.0.0.1:8091/health` inside container.

## Discovery (autonomous mode)

Before `IDEA_RECEIVED`:

| Stage | Output |
|-------|--------|
| Signal collector | Reddit, HN, GitHub, web fallbacks → `data/discovery/signals.jsonl` |
| Validation + interview sim | Candidate opportunities |
| Scoring + ranking | `ranked_ideas.json`, `weekly_digest.md` |
| Director pick | Top idea → normal product |

Manual trigger: `POST /api/admin/discovery/run`  
Queue: `GET /api/admin/discovery/ideas`

Schedule: `AIFACTORY_DISCOVERY_INTERVAL_HOURS` (default **6**).

## Product types

| Type | Typical use |
|------|-------------|
| `marketing_landing` | Fast brochure / hero page (~20–25 min) |
| `full_software` | API + DB + CRUD (~25 min – hours) |

Same pipeline code path; different stage depth and deploy targets.

## Gates & repair

Failures → **`BUG_FOUND` → `DEV_FIXING`** with repair hints until pass or budget exhausted.

| Mechanism | Purpose |
|-----------|---------|
| QA + Playwright E2E | Functional/browser smoke |
| Security scans | Dependency / pattern checks |
| Methodologist | Domain pack rules |
| Design critic | UX brief compliance |
| Demo/TZ gate | Marketplace-ready stub detection |

**After ship:**

- **Policy audit** — COMPLETED products re-checked vs new rules
- **Storefront remediation** — listing quality drift

Bounded by **`AIFACTORY_MAX_QUALITY_LOOPS`** (default **8**).

Optional harder model on repair rounds: **`AIFACTORY_GATE_FAILING_MODEL`** (same provider, different model id).

## Admin truth sources

| UI | Meaning |
|----|---------|
| **Pipeline** tab | Every product, stage, errors — **source of truth** |
| Dashboard KPIs | Snapshot on load |
| Storefront `/` | Filtered marketplace-ready subset |
| `GET /api/public/pipeline-status` | Public shipped vs in-pipeline counts |

## State machine reference

[`docs/architecture-diagrams.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/architecture-diagrams.md) — Mermaid LR flow, extended gates, storefront flow.

Config sequence: [`config/pipeline_flow.json`](http://5.129.212.122/Superowner/aicom/src/branch/main/config/pipeline_flow.json)
