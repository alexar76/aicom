# AI-Factory Documentation

> **Ecosystem knowledge base (start here):** [`ecosystem/knowledge-base.md`](./ecosystem/knowledge-base.md) · [RU](./ecosystem/knowledge-base-ru.md) · [ES](./ecosystem/knowledge-base-es.md) · [FR](./ecosystem/knowledge-base-fr.md) · [ZH](./ecosystem/knowledge-base-zh.md) · [whitepaper](./ecosystem/whitepaper/)
>
> **Live:** [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) · **Metis:** [metis.modelmarket.dev](https://metis.modelmarket.dev) · **Oracles ×17:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · [GitHub](https://github.com/alexar76/oracles) (EN / [RU](https://github.com/alexar76/oracles/blob/main/docs/ru.md) / [ES](https://github.com/alexar76/oracles/blob/main/docs/es.md))
>
> **Community:** [Ask Castor (bot)](https://t.me/next_agent_market_bot) · [Castor channel](https://t.me/just_for_agents) · [Discord · Pollux](https://discord.gg/aimarket) · [THEOROS canon](https://alexar76.github.io/theoros/) · [DIOSCURI](https://github.com/alexar76/dioscuri) · [Content playbook](growth/content-playbook.md)

> 🔴 **Live on Base MAINNET (demo) — not a testnet.** The full contract suite is deployed +
> source-verified on Base mainnet (chainId 8453, real USDC/ETH). Every deploy + transaction with
> Basescan links: **[on-chain journal → `onchain-journal.md`](onchain-journal.md)** ·
> network/RPC config: [`chain-networks.md`](chain-networks.md).

## SDKs & packages

Published client SDKs — install and what each is for:

| Package | Registry | Install | Purpose |
|---|---|---|---|
| [`aimarket-agent`](https://pypi.org/project/aimarket-agent/) | PyPI | `pip install aimarket-agent` | Python consumer SDK (AI Market Protocol v2) — **v2.1.x line** |
| [`aimarket-hub`](https://pypi.org/project/aimarket-hub/) | PyPI | `pip install aimarket-hub` | Reference federation hub server — **v3.0.x** |
| [`@aimarket/agent`](https://www.npmjs.com/package/@aimarket/agent) | npm | `npm install @aimarket/agent` | TypeScript SDK — **v0.1.x line** (see [`sdk-version-policy.md`](./sdk-version-policy.md)) |
| [`aimarket-agent`](https://crates.io/crates/aimarket-agent) | crates.io | `aimarket-agent = "0.1.0"` | Rust SDK — v0.1.x |
| [`aimarket-agent`](https://pub.dev/packages/aimarket_agent) | pub.dev | `dart pub add aimarket_agent` | Dart SDK — v0.1.x |
| [`aimarket-metis`](https://pypi.org/project/aimarket-metis/) | PyPI | `pip install aimarket-metis` | Metis cognition engine (CLI + library) |
| [`aimarket-mcp`](https://pypi.org/project/aimarket-mcp/) | PyPI | `pip install aimarket-mcp` | Shared MCP gateway — web fetch/search + Metis verify (stdio + HTTP) |
| [`aimarket-bridges`](https://pypi.org/project/aimarket-bridges/) | PyPI | `pip install "aimarket-bridges[langgraph]"` | LangGraph / CrewAI / AutoGen adapters over Hub capabilities · [landing](https://modeldev.modelmarket.dev/bridges/) |
| [`aimarket-oracle-gateway`](https://pypi.org/project/aimarket-oracle-gateway/) | PyPI | `pip install aimarket-oracle-gateway` | 35 verifiable oracle MCP tools (stdio) |

**Hub plugins (PyPI):** `aimarket-tee`, `aimarket-channels`, `aimarket-reputation`, `aimarket-safety`, `aimarket-mcp-packager` — [`plugins/docs/install.md`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/docs/install.md).

**Version policy:** [`sdk-version-policy.md`](./sdk-version-policy.md) — why Python is 2.x and Dart/TS/Rust are 0.1.x.

## Documentation languages

| Scope | Languages |
|-------|-----------|
| **Ecosystem whitepaper** (ideology, all components, admin) | **EN** · [RU](./ecosystem/whitepaper/ru.md) · [ES](./ecosystem/whitepaper/es.md) · [FR](./ecosystem/whitepaper/fr.md) · [ZH](./ecosystem/whitepaper/zh.md) |
| **ARGUS user guide + humor** | **20** — [`argus/docs/user-guide/`](https://github.com/alexar76/argus/tree/main/docs/user-guide/) |
| **ARGUS wiki** (install, WARDEN, channels) | **EN** — [github.com/alexar76/argus/wiki](https://github.com/alexar76/argus/wiki) · source: [`scripts/wiki-argus/`](../scripts/wiki-argus/) |
| **Factory operator** | EN · [RU](./USER_GUIDE.ru.md) · [ES](./USER_GUIDE.es.md) · [FR](./USER_GUIDE.fr.md) · [ZH](./USER_GUIDE.zh.md) |

### Ecosystem knowledge base & white book

- **[`ecosystem/knowledge-base.md`](./ecosystem/knowledge-base.md)** — **master guide**: live URLs, every component, MCP + 17 oracles table, Metis + aimarket-mcp, ARGUS sell path, SDKs, deploy, wikis, reading order.
- **[`metis-integration.md`](./metis-integration.md)** — **Metis ⇄ AI-Factory**: optional confidence gate on high-stakes stages (EN · [RU](./metis-integration.ru.md) · [ES](./metis-integration.es.md) · [FR](./metis-integration.fr.md) · [ZH](./metis-integration.zh.md)).
- **[`ecosystem/whitepaper/`](./ecosystem/whitepaper/)** — full white book (EN/RU/ES/FR/ZH): ideology, architecture, every component, money/trust flows, Base mainnet demos, admin deploy, config tables, roadmap.

| Language | Files |
|----------|--------|
| **English (primary)** | All guides under `docs/` except the optional RU/ES companions below — technical reference, ops, API, architecture. |
| **Russian (optional)** | [`USER_GUIDE.ru.md`](./USER_GUIDE.ru.md), [`FAQ.ru.md`](./FAQ.ru.md), [`funnel-growth.ru.md`](./funnel-growth.ru.md), [`security-persistence.ru.md`](./security-persistence.ru.md), [`alien-monitor-factory-catalog.ru.md`](./alien-monitor-factory-catalog.ru.md) |
| **Spanish (optional)** | [`USER_GUIDE.es.md`](./USER_GUIDE.es.md), [`FAQ.es.md`](./FAQ.es.md), [`funnel-growth.es.md`](./funnel-growth.es.md), [`security-persistence.es.md`](./security-persistence.es.md), [`alien-monitor-factory-catalog.es.md`](./alien-monitor-factory-catalog.es.md) |

Operator-facing UI strings may be **en / ru / es** in Admin; that is product i18n, not documentation locale. Wiki language policy: [`scripts/wiki-gitea/Languages.md`](../scripts/wiki-gitea/Languages.md).

**In-app docs** at `/docs` (Next.js) use JSON language packs in [`web/frontend/language-packs/docs/`](../web/frontend/language-packs/docs/) — regenerate with `python3 scripts/generate_docs_i18n.py`. Wiki: [`Ecosystem`](../scripts/wiki-gitea/Ecosystem.md) · [`Oracles`](../scripts/wiki-gitea/Oracles.md) ([RU](../scripts/wiki-gitea/Oracles-RU.md) · [ES](../scripts/wiki-gitea/Oracles-ES.md)).

## Operator / owner playbook

- **`USER_GUIDE.md`** — **detailed illustrated walkthrough** (EN): situation cheat sheet, scenario playbooks, Pipeline catalog loading, screenshot index. Start here for **hands-on usage**.
- **`USER_GUIDE.ru.md`** — **подробное руководство (RU)** с теми же скриншотами, кейсами и таблицей «куда смотреть».
- **`USER_GUIDE.es.md`** — **guía detallada (ES)** con las mismas capturas y escenarios.
- **`FAQ.md`** / **`FAQ.ru.md`** / **`FAQ.es.md`** — **detailed FAQ** (EN + RU + ES): Pipeline retries, cache, storefront vs Completed, LLM, discovery, data volumes.
- **`owner-guide.md`** — English handbook for the platform owner: step-by-step flows, **Mermaid** diagrams, storefront policy, support vs pipeline, pitfalls. Start here if you run an instance.
- **`api-integration-guide.md`** — REST integration: auth patterns, router map, curl examples (companion to Swagger `/api/docs`).
- **`cli-reference.md`** — commands implemented in `cli/ai_company_cli.py`, plus notes on stubs vs real behavior.

## Operations & recovery

- **`production-metrics.md`** — public demo SLOs (RPS, latency, uptime, incidents); live [`/api/public/ecosystem-status`](../web/backend/main.py); refresh with [`scripts/collect_production_metrics.py`](../scripts/collect_production_metrics.py).
- **`ecosystem-audit-report.md`** — связность + безопасность экосистемы (баги, дыры, remediation).
- **`recovery-mechanisms.md`** — factory hold, backup/restore, migration rollback, pipeline reopen, LLM circuit breaker, ZK artifact recovery, fleet redeploy order.
- **`pipeline-operations.md`** — pipeline worker, Director, factory hold semantics.

## Deployment

- **`deploy-ecosystem.md`** — **full fleet redeploy** (Factory → **`deploy_hub.sh`** → Mesh → Monitor → verify). Hub must **not** be restarted via `aimarket-hub/docker compose`; use `./scripts/deploy_ecosystem.sh` or `./scripts/deploy_hub.sh`.
- **`deploy-ecosystem-runbook.md`** — **runbook для ops**: pre-flight секреты, Monitor/Mesh auth, post-deploy чеклист, channel secret breaking change, cron, troubleshooting.
- **`configuration.md`** — layered YAML (`config/fragments/` + overlay), env vars, Admin Settings save semantics, and what *not* to merge.
- **`security.md`** — first-run admin password (console prompt / bootstrap file), CSRF, firewall, audit chain, sandbox/host-gateway, landing language rules.
- **[`scripts/deploy.sh`](../scripts/deploy.sh)** — Docker Compose: optional `.env` auto-fill for **missing** keys (`scripts/fill_production_env.py`, `--public-url`, `--dry-run`) + `build` / `up -d app`.
- `auto-publish.md` — static deploy after DevOps (Vercel / Netlify / Cloudflare Pages); env tokens and `data/state/.../auto_publish.json`.
- **`green-badges-runbook.md`** — keep GitHub CI / Security / Pages badges green after Gitea + `publish_all_repos` (factory workflows, gitleaks, coverage drift).
- `deploy-full-software-cloud.md` — **full_software** backends (DB, long-lived API): Railway/Fly/Run-style layout, **Admin → Settings** Railway hook, `railway_deploy.json` for external CI.
- [`packaging/templates/README.md`](../packaging/templates/README.md) — inventory of **nixpacks.toml**, **Procfile**, **railway.json**, Dockerfiles in reference templates.

## Product and Operations

- **`architecture-diagrams.md`** — **Mermaid hub**: full runtime architecture, pipeline LR + extended gates, state machine, discovery, storefront flow, comparison table, Grafana panel map (moved from root README).
- **`architecture-orchestrator.md`** — pipeline worker SRP split, sync/async state machine, Director JSON vs SQLite decisions store.
- `pipeline-operations.md` — discovery, scheduler, batch pipeline, benchmark gate, monitoring loops, **per-product LLM spend cap** (Admin Settings + env).
- `uni-economics.md` — UNI store credit (fixed peg, fees, treasury, API); aligns with in-app docs section **UNI credit bus** (EN/RU/ES).
- **`free-and-paid-tiers.md`** — what the ecosystem gives away and why: 42 of 47 capabilities are free today, the two that sell sequential computation, their measured cost, the free-tier ceilings and CPU budgets that bound them, and the **two switches that turn selling on** — `ORACLE_PAID_TIER_SECRET` on the oracle side and `AIMARKET_SELLS_FOR` on the hub, which makes 42 free capabilities paid the minute it is set (EN · [RU](./free-and-paid-tiers.ru.md) · [ES](./free-and-paid-tiers.es.md) · [FR](./free-and-paid-tiers.fr.md) · [ZH](./free-and-paid-tiers.zh.md)).
- **`crypto-switch.md`** — the master on/off for the on-chain economy, and why enabling crypto is *not* the same as enabling selling (EN · [RU](./crypto-switch.ru.md) · [ES](./crypto-switch.es.md) · [FR](./crypto-switch.fr.md) · [ZH](./crypto-switch.zh.md)).
- `postgres-production-runbook.md` — Postgres cutover for pipeline and UNI ledger.
- **`observability-langsmith.md`** — opt-in OpenTelemetry tracing for **LangSmith / Phoenix / Helicone / Jaeger**. Uses `gen_ai.*` semantic conventions on every LLM call; `factory.pipeline_stage` parent spans show the agent tree; `trace_id` is stamped into UNI receipts so a buyer can follow a payment back to the LLM trace.
- `sandbox-trust-model.md` — sandbox isolation limits and hardening checklist.
- `agents.md` — pipeline agent roster, **markdown system prompts** under `agents/prompts/`, including `methodologist`.
- `audit-delta-changes.md` — Staff audit remediation tracker (circuit breaker, watchfiles, API v1, logging).
- `methodology-agent.md` — domain methodology gate, domain packs, artifacts, and rework behavior.
- `factory-capabilities.md` — full feature map (agents, quality, ops, monetization surfaces).
- `factory-metrics-reference.md` — complete metric registry and action mapping.
- **`product-pnl.md`** ([RU](./product-pnl.ru.md)) — **live per-product P&L / unit economics**: joins paid orders (revenue) with per-product LLM spend (COGS) into margin, ROI and cost-recovery, plus a portfolio rollup. Endpoint `GET /api/admin/finance/product-pnl`. Mermaid data-flow + request diagrams.
- `benchmark-ops.md` — benchmark scorecard operations and alerting flow.
- `admin-guide.md` — full admin tab reference + screenshot mappings.
- `admin-panel-rbac.md` — **human admin roles** (`viewer` / `operator` / `admin` / `super_admin`), APIs, and where they are enforced.

## Growth and GTM

- **`funnel-growth.md`** — public leads, auto-pipeline, status page, waitlist embed, admin funnel dashboard, distribute on COMPLETED (**[RU](./funnel-growth.ru.md)** · **[ES](./funnel-growth.es.md)**).
- `marketing.md` — storefront behavior, referral attribution, analytics, and public pages.
- **[`growth/content-playbook.md`](./growth/content-playbook.md)** — landings, READMEs, docs: canonical links, Ask the twins CTAs, MNEMOSYNE · **[RU](./growth/content-playbook-ru.md)**
- **[`growth/seeding-playbook.md`](./growth/seeding-playbook.md)** — MCP registries, awesome lists, Glama

## Security (recent)

- **`security-persistence.md`** — SQLite rate limits + OIDC nonce replay (H-3/H-5) (**[RU](./security-persistence.ru.md)** · **[ES](./security-persistence.es.md)**).

## Alien Monitor

- **`alien-monitor-factory-catalog.md`** — Factory product clusters in UNI/LIVE (**[RU](./alien-monitor-factory-catalog.ru.md)** · **[ES](./alien-monitor-factory-catalog.es.md)**).
- `launch-kit.md` — press kit checklist for Product Hunt / Show HN / Reddit launch.
- `investor-deck.md` — visual investor narrative with mechanics, diagrams, and screenshots.
- `investor-functional-overview.md` — investor-facing functional snapshot.

## Protocols and domain playbooks

- **[ecosystem-architecture.md](./ecosystem-architecture.md)** — **Monorepo map**: AI-Factory ↔ AIMarket Hub ↔ desktop apps (C4, Mermaid sequences, deployment topology).
- **[`metis-integration.md`](./metis-integration.md)** — Metis cognition gate + Alien Monitor chat proxy (optional; factory fail-open without Metis).
- **`ai-market-protocol-v1.md`** — **AI Market Protocol v1**: `.well-known`, MCP manifest, HTTP 402, payment channels, pipelines, reference agent (`cli/ai_market_agent.py`).
- **[`pay-on-verified.md`](./pay-on-verified.md)** — **Pay-on-Verified settlement**: buyer-opt-in escrow hold on hub invoke, Metis verdict → capture or refund (additive on v2; legacy debit path unchanged without it).
- **[`iot-physical-oracles.md`](./iot-physical-oracles.md)** — **GAIA physical-oracle gateway**: attested virtual-sensor readings sold as v2 capabilities, statistical plausibility verifier in the Pay-on-Verified slot, device identity chain, WoT bridge, micro-billing.
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

