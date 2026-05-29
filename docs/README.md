# AI-Factory Documentation

> **Ecosystem:** [AICOM overview & live demos](https://alexar76.github.io/aicom/)

## Documentation languages

| Language | Files |
|----------|--------|
| **English (primary)** | All guides under `docs/` except the optional RU/ES companions below — technical reference, ops, API, architecture. |
| **Russian (optional)** | [`USER_GUIDE.ru.md`](./USER_GUIDE.ru.md), [`FAQ.ru.md`](./FAQ.ru.md) — same topics as the English user guide / FAQ, maintained in parallel. |
| **Spanish (optional)** | [`USER_GUIDE.es.md`](./USER_GUIDE.es.md), [`FAQ.es.md`](./FAQ.es.md) — same topics as EN user guide / FAQ. UI: `NEXT_PUBLIC_MARKETING_LOCALE=es`, Admin locale **es**. |

Operator-facing UI strings may be **en / ru / es** in Admin; that is product i18n, not documentation locale. Wiki language policy: [`scripts/wiki-gitea/Languages.md`](../scripts/wiki-gitea/Languages.md).

**In-app docs** at `/docs` (Next.js) use JSON language packs in [`web/frontend/language-packs/docs/`](../web/frontend/language-packs/docs/) — regenerate with `python3 scripts/generate_docs_i18n.py`. Wiki ecosystem overview: [`scripts/wiki-gitea/Ecosystem.md`](../scripts/wiki-gitea/Ecosystem.md).

## Operator / owner playbook

- **`USER_GUIDE.md`** — **detailed illustrated walkthrough** (EN): situation cheat sheet, scenario playbooks, Pipeline catalog loading, screenshot index. Start here for **hands-on usage**.
- **`USER_GUIDE.ru.md`** — **подробное руководство (RU)** с теми же скриншотами, кейсами и таблицей «куда смотреть».
- **`USER_GUIDE.es.md`** — **guía detallada (ES)** con las mismas capturas y escenarios.
- **`FAQ.md`** / **`FAQ.ru.md`** / **`FAQ.es.md`** — **detailed FAQ** (EN + RU + ES): Pipeline retries, cache, storefront vs Completed, LLM, discovery, data volumes.
- **`owner-guide.md`** — English handbook for the platform owner: step-by-step flows, **Mermaid** diagrams, storefront policy, support vs pipeline, pitfalls. Start here if you run an instance.
- **`api-integration-guide.md`** — REST integration: auth patterns, router map, curl examples (companion to Swagger `/api/docs`).
- **`cli-reference.md`** — commands implemented in `cli/ai_company_cli.py`, plus notes on stubs vs real behavior.

## Deployment

- **`configuration.md`** — layered YAML (`config/fragments/` + overlay), env vars, Admin Settings save semantics, and what *not* to merge.
- **`security.md`** — first-run admin password (console prompt / bootstrap file), CSRF, firewall, audit chain, sandbox/host-gateway, landing language rules.
- **[`scripts/deploy.sh`](../scripts/deploy.sh)** — Docker Compose: optional `.env` auto-fill for **missing** keys (`scripts/fill_production_env.py`, `--public-url`, `--dry-run`) + `build` / `up -d app`.
- `auto-publish.md` — static deploy after DevOps (Vercel / Netlify / Cloudflare Pages); env tokens and `data/state/.../auto_publish.json`.
- `deploy-full-software-cloud.md` — **full_software** backends (DB, long-lived API): Railway/Fly/Run-style layout, **Admin → Settings** Railway hook, `railway_deploy.json` for external CI.
- [`packaging/templates/README.md`](../packaging/templates/README.md) — inventory of **nixpacks.toml**, **Procfile**, **railway.json**, Dockerfiles in reference templates.

## Product and Operations

- **`architecture-diagrams.md`** — **Mermaid hub**: full runtime architecture, pipeline LR + extended gates, state machine, discovery, storefront flow, comparison table, Grafana panel map (moved from root README).
- **`architecture-orchestrator.md`** — pipeline worker SRP split, sync/async state machine, Director JSON vs SQLite decisions store.
- `pipeline-operations.md` — discovery, scheduler, batch pipeline, benchmark gate, monitoring loops, **per-product LLM spend cap** (Admin Settings + env).
- `uni-economics.md` — UNI store credit (fixed peg, fees, treasury, API); aligns with in-app docs section **UNI credit bus** (EN/RU/ES).
- `postgres-production-runbook.md` — Postgres cutover for pipeline and UNI ledger.
- **`observability-langsmith.md`** — opt-in OpenTelemetry tracing for **LangSmith / Phoenix / Helicone / Jaeger**. Uses `gen_ai.*` semantic conventions on every LLM call; `factory.pipeline_stage` parent spans show the agent tree; `trace_id` is stamped into UNI receipts so a buyer can follow a payment back to the LLM trace.
- `sandbox-trust-model.md` — sandbox isolation limits and hardening checklist.
- `agents.md` — pipeline agent roster, **markdown system prompts** under `agents/prompts/`, including `methodologist`.
- `audit-delta-changes.md` — Staff audit remediation tracker (circuit breaker, watchfiles, API v1, logging).
- `methodology-agent.md` — domain methodology gate, domain packs, artifacts, and rework behavior.
- `factory-capabilities.md` — full feature map (agents, quality, ops, monetization surfaces).
- `factory-metrics-reference.md` — complete metric registry and action mapping.
- `benchmark-ops.md` — benchmark scorecard operations and alerting flow.
- `admin-guide.md` — full admin tab reference + screenshot mappings.
- `admin-panel-rbac.md` — **human admin roles** (`viewer` / `operator` / `admin` / `super_admin`), APIs, and where they are enforced.

## Growth and GTM

- `marketing.md` — storefront behavior, referral attribution, analytics, and public pages.
- `launch-kit.md` — press kit checklist for Product Hunt / Show HN / Reddit launch.
- `investor-deck.md` — visual investor narrative with mechanics, diagrams, and screenshots.
- `investor-functional-overview.md` — investor-facing functional snapshot.

## Protocols and domain playbooks

- **[ecosystem-architecture.md](./ecosystem-architecture.md)** — **Monorepo map**: AI-Factory ↔ AIMarket Hub ↔ desktop apps (C4, Mermaid sequences, deployment topology).
- **`ai-market-protocol-v1.md`** — **AI Market Protocol v1**: `.well-known`, MCP manifest, HTTP 402, payment channels, pipelines, reference agent (`cli/ai_market_agent.py`).
- `ai-market-protocol-v0.md` — v0 pilot (catalog, on-chain settlement confirm, license invoke).
- **`domain-guides/README.md`** — index of all **10 built-in** domain methodology packs + links to short playbooks (source: `web/backend/services/domain_methodology/packs/`).
- Full pack table and methodology schema: **`methodology-agent.md`**.
- Narrative playbooks live under `domain-guides/` (see index); note `fintech.md` maps to pack `finance_billing`, `healthcare.md` → `healthcare_wellness`, `ecommerce.md` → `ecommerce`.

## Screenshots and visual documentation

- `gallery/README.md` — **README hero gallery**: WebP tiles from **`scripts/capture_gallery_landings.py`** (`/api/sandbox/file/…/index.html`, default stack **:9080**).
- `production-domain.md` — **Public hostname** for this fleet: **`magic-ai-factory.com`**, nginx on **:80**, `NEXT_PUBLIC_SITE_URL`, rebuild notes.
- **`production-modelmarket-dev.md`** — **AIMarket Hub** at **`https://modelmarket.dev`**, certbot TLS, hub Docker on **:9083**.
- `assets/screenshots/README.md` — capture workflow and screenshot inventory.
- `assets/screenshots/MISSING.md` — coverage report (what is captured vs pending refresh).

