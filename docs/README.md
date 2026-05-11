# AI-Factory Documentation

## Operator / owner playbook

- **`owner-guide.md`** — English handbook for the platform owner: step-by-step flows, **Mermaid** diagrams, storefront policy, support vs pipeline, pitfalls. Start here if you run an instance.
- **`api-integration-guide.md`** — REST integration: auth patterns, router map, curl examples (companion to Swagger `/api/docs`).
- **`cli-reference.md`** — commands implemented in `cli/ai_company_cli.py`, plus notes on stubs vs real behavior.

## Deployment

- `auto-publish.md` — static deploy after DevOps (Vercel / Netlify / Cloudflare Pages); env tokens and `data/state/.../auto_publish.json`.
- `deploy-full-software-cloud.md` — **full_software** backends (DB, long-lived API): Railway/Fly/Run-style layout, **Admin → Settings** Railway hook, `railway_deploy.json` for external CI.
- [`packaging/templates/README.md`](../packaging/templates/README.md) — inventory of **nixpacks.toml**, **Procfile**, **railway.json**, Dockerfiles in reference templates.

## Product and Operations

- `pipeline-operations.md` — discovery, scheduler, batch pipeline, benchmark gate, monitoring loops.
- `agents.md` — pipeline agent roster, including `methodologist`.
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

- `ai-market-protocol-v0.md` — reference protocol for AI-to-AI commerce.
- **`domain-guides/README.md`** — index of all **10 built-in** domain methodology packs + links to short playbooks (source: `web/backend/services/domain_methodology/packs/`).
- Full pack table and methodology schema: **`methodology-agent.md`**.
- Narrative playbooks live under `domain-guides/` (see index); note `fintech.md` maps to pack `finance_billing`, `healthcare.md` → `healthcare_wellness`, `ecommerce.md` → `ecommerce`.

## Screenshots and visual documentation

- `gallery/README.md` — **README hero gallery**: WebP tiles from **`scripts/capture_gallery_landings.py`** (`/api/sandbox/file/…/index.html`, default stack **:9080**).
- `production-domain.md` — **Public hostname** for this fleet: **`magic-ai-factory.com`**, nginx on **:80**, `NEXT_PUBLIC_SITE_URL`, rebuild notes.
- `assets/screenshots/README.md` — capture workflow and screenshot inventory.
- `assets/screenshots/MISSING.md` — coverage report (what is captured vs pending refresh).

