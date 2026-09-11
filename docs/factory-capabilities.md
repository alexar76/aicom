# AI-Factory Capabilities (Full Function Map)

This document reflects the current factory feature set as an operator/engineering map.

## 1) Pipeline and agent system

- End-to-end state machine from idea to shipped product.
- Agent chain:
  - Analyst (market/discovery)
  - PM (specification)
  - Methodologist (domain process compliance after spec and implementation)
  - Marketing (market content)
  - Architect (architecture + UI direction)
  - Design Critic (art-direction gate)
  - Developer
  - Hardening
  - QA
  - Security / DevOps / Sales
- Peer-review loop: blocking stages can return work to responsible stage.
- Auto-requeue and remediation playbooks for common failure classes.

## 2) Domain intelligence

- Vertical-aware playbooks (`fintech`, `education`, `ecommerce`, `devtools`, `general`).
- Discovery packs generated per idea:
  - domain assumptions
  - discovery questions
  - UX patterns and anti-patterns
- Spec compiler injects domain and discovery context into PM prompts.
- Methodology domain packs validate required entities, roles, lifecycle states, capabilities, and process metrics for CRM, helpdesk, e-commerce, LMS, HR/ATS, project management, finance/billing, healthcare, analytics/BI, and DevTools/Ops products.

## 3) Design quality system

- `ui_experience` contract (tokens, typography, layout, motion, SVG creative brief).
- Multi-variant design generation and ranking.
- Novelty checks against recent outputs.
- Design Critic gate with taste-level scoring:
  - originality
  - clarity
  - brand coherence
  - feasibility
  - accessibility

## 4) Code, QA, and release quality

- Contract-first implementation plan artifact.
- Hardening pass before QA.
- QA stack:
  - static/code checks
  - acceptance traceability
  - domain acceptance pack
  - Methodology Agent implementation gate
  - maintainability checks
  - browser runtime E2E
  - backend runtime E2E
- Performance/SLO gate:
  - browser timing checks
  - backend load smoke (p95 threshold)
- Quality Constitution as final release contract.

## 5) Operational maturity layer

- Release lifecycle artifact (`lifecycle_release.json`) includes:
  - versioning strategy
  - migration plan
  - canary plan
  - rollback plan
  - release checks
- Executable release protocol:
  - verifies required lifecycle sections
  - writes `release_protocol_execution.json`
- Go/No-Go cockpit:
  - aggregates constitution, lifecycle, protocol execution, benchmark pass-rate, perf regression.

## 6) Real-user feedback loop

- Support chat sessions with routing and escalation.
- Structured product feedback (rating/comment/source/journey/tags).
- Telemetry events endpoint for runtime usage signals.
- Session replay timeline endpoints for operations.
- Feedback digest feeds PM and Hardening prompts.
- Feedback guardrail:
  - if real-user signals degrade (negative journey votes / bugs), product is auto-routed back into PM rework.

## 7) Admin and observability

- Director tab:
  - benchmark scorecard
  - feedback summaries
  - session replay explorer
  - go/no-go cockpit controls
- Agent logs, LLM logs, pipeline monitor, settings.
- Realtime metrics transport:
  - SSE stream (`/api/admin/metrics/stream`)
  - WebSocket stream (`/api/admin/ws/metrics`) for integration clients (includes LLM **circuit breaker** snapshots).
- **LLM circuit breaker** per provider (CLOSED / OPEN / HALF_OPEN), automatic failover, Admin controls, Prometheus gauges — see **[admin-guide.md](./admin-guide.md#llm-providers)**.
- **API versioning**: clients may call `/api/v1/*` (alias of `/api/*`) — **[api-integration-guide.md](./api-integration-guide.md)**.

## 8) Key API additions (operational layer)

- `GET /api/admin/release/cockpit/{product_id}`
- `POST /api/admin/release/protocol/{product_id}/execute`
- `GET /api/admin/feedback/summary`
- `GET /api/admin/telemetry/replay/{product_id}`
- `GET /api/admin/telemetry/replay/{product_id}/{session_id}`
- `POST /api/telemetry/event`
- `POST /api/customer/billing/stripe/checkout`
- `POST /api/customer/billing/stripe/webhook`
- `GET /api/customer/referrals/me`
- `POST /api/admin/products/create-batch`
- `GET /api/admin/products/batch/{batch_id}`
- `POST /api/admin/products/batch/{batch_id}/retry-failed`
- `GET /api/benchmark`

## 9) Current maturity status

The factory now has:
- creative/design control loop,
- domain intelligence,
- strict release governance,
- real-user feedback-driven regeneration,
- and operational go/no-go controls.

This is the baseline required for stable “human-team-like” generation quality.

## 10) Remaining-gap hardening upgrades

- Clarification pack generation is now LLM-first (with deterministic fallback) for PM requirement discovery.
- Periodic refactor sprints are explicit pipeline tasks for completed products (tech-debt control).
- Release critic includes minimum real-user validation evidence as a production completion gate.
- Cross-product learning memory uses retention/size compaction and dedup, then feeds lessons back into task context.
- Worker responsibilities are split across dedicated components (task orchestration, quality routing, peer review).
- LLM response cache added at router level (TTL + bounded map) to reduce repeated generation cost.
- Runtime fallback tests now infer framework-level checks (pytest/npm/node check), not only Python compile sanity.

## 12) Delivery and CI

- Repo now includes portable CI workflow (`.github/workflows/ci.yml`) with:
  - backend full pytest run,
  - frontend production build validation.
- Existing server-side delivery path (Gitea Actions) remains available for environment-specific deploy orchestration.

## 11) Distribution and growth surfaces

- SEO surfaces:
  - blog index + post pages (`/blog`, `/blog/[slug]`)
  - sitemap and robots routes (`/sitemap.xml`, `/robots.txt`)
  - homepage FAQ block for search intent coverage
- Launch assets:
  - launch kit page (`/launch-kit`)
  - docs launch checklist (`docs/launch-kit.md`)
- Viral loop:
  - embeddable badge script (`/ai-factory-badge.js`) and docs page (`/badge`)
- Monetization + referral:
  - Stripe self-serve upgrade flow
  - customer referral code generation and attributed conversion stats
