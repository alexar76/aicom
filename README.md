# AI-Factory v2.1

**MIT · self-hosted · full agent pipeline · Deep Playwright QA · optional human gates**

**Website:** [magic-ai-factory.com](https://magic-ai-factory.com) · Production notes: [docs/production-domain.md](docs/production-domain.md)

> **Product disclaimer**  
> Not everyone will fully connect with the intent and scope of this project — that is expected.  
> **This is not a quick landing-page generator.** It is an attempt to build an **autonomously operating AI company**: from discovering an idea through shipping a **real product**, with ongoing support, evolution, and monetization.

Turn one sentence into a presentable site or MVP-shaped codebase — with demo gates, browser crawl, and an operator-grade admin UI.

### Deploy (Docker Compose)

**[`./scripts/deploy.sh`](scripts/deploy.sh)** appends **missing** keys to **`.env`** only (optional `--public-url` sets `NEXT_PUBLIC_SITE_URL` and `AIFACTORY_CORS_ORIGINS`; generates `AIFACTORY_FIREWALL_RULES_FERNET_KEY` when possible; defaults `AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION=1`), then runs `docker compose build` + `up -d app`. Logic: [`scripts/fill_production_env.py`](scripts/fill_production_env.py) (`--dry-run` supported).

```bash
chmod +x scripts/deploy.sh   # once
cp -n .env.example .env      # if you do not have .env yet
./scripts/deploy.sh --public-url https://your-factory.example.com
```

Why not fully automatic: the script cannot infer your real public URL without you (or your reverse proxy). Existing `.env` assignments are **never overwritten** so we do not clobber secrets you already set.

### The pipeline at a glance

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

### Compared to hosted AI app builders

Rough positioning — **verify vendor pricing/features** before you debate Twitter.

| | Bolt.new | Lovable | v0 | Devin | **AI-Factory** |
|--|:---:|:---:|:---:|:---:|:---:|
| **Self-hosted** | ❌ | ❌ | ❌ | ❌ | ✅ MIT |
| **E2E tests** | ❌ | ❌ | ❌ | ❌ | ✅ Deep Playwright crawl |
| **Human gate** | ❌ | ❌ | ❌ | ✅ | ✅ Human pipeline |
| **Typical price** | ~$20/mo | ~$50/mo | ~$20/mo | ~$500/mo | **Free (bring your own keys)** |

### Gallery — generated landings

Built pages only (1440×900 WebP): screenshots are **`/api/sandbox/file/…/index.html`** — not the sandbox viewer UI — refresh with **`python scripts/capture_gallery_landings.py`** (stack on **http://127.0.0.1:9080**). Details: **[docs/gallery/README.md](docs/gallery/README.md)**.

Sample **screen recording** (login → Live Monitor → Pipeline → enqueue idea → Pipeline): [`docs/gallery/recordings/pipeline-demo-latest.webm`](docs/gallery/recordings/pipeline-demo-latest.webm) *(regenerate via `scripts/record_pipeline_demo_video.py`)*.

| ![Gallery 1](docs/gallery/landing-01.webp) | ![Gallery 2](docs/gallery/landing-02.webp) | ![Gallery 3](docs/gallery/landing-03.webp) |
|:---:|:---:|:---:|
| ![Gallery 4](docs/gallery/landing-04.webp) | ![Gallery 5](docs/gallery/landing-05.webp) | *optional 6th tile in README table* |

### Gallery — full_software (dashboard / auth / CRUD / settings)

**Committed baseline (no pipeline run):** build the FastAPI template and capture four WebPs (same routes the factory uses for real products):

```bash
# Docker + Playwright; writes docs/gallery/fullstack-01.webp … fullstack-04.webp
.venv/bin/python -m playwright install chromium   # once
.venv/bin/python scripts/capture_gallery_fullstack_packaging_demo.py
```

| ![FS 1](docs/gallery/fullstack-01.webp) | ![FS 2](docs/gallery/fullstack-02.webp) | ![FS 3](docs/gallery/fullstack-03.webp) | ![FS 4](docs/gallery/fullstack-04.webp) |
|:---:|:---:|:---:|:---:|
| `/` | `/login` | `/tasks` | `/settings` |

**From a real pipeline product** (compose sandbox on **:9080**, `AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1`):

```bash
GALLERY_FS_PRODUCT_ID=prod-xxxxxxxxxxxx \
  .venv/bin/python scripts/capture_gallery_full_software.py
```

See **[docs/gallery/README.md](docs/gallery/README.md)**.

**End-to-end demo seed:** `./scripts/demo_seed_fullstack.sh` enqueues a SaaS brief, waits for pipeline completion, runs optional `scripts/seed_factory_demo.py` if the Developer shipped one, then opens the product page.

### Prompt starters (Admin → New Product)

Default mode is **full product** (`full_software`). Use the **What to ship** control for a **brochure-only** SKU, or `./demo.sh --landing` from the CLI.

| 💡 Prompt | Notes |
|-----------|--------|
| **SaaS for managing remote teams** — dashboard, auth, API | Default build = full stack |
| **Echo / voice notes app** with backend sync | Full product |
| Landing page for **resume builder** | Choose **Marketing landing page only** in Admin, or `./demo.sh --landing "…"` |

### One command — enqueue + open Pipeline

```bash
chmod +x demo.sh    # once
./demo.sh "SaaS for managing remote teams"          # default: full_software
./demo.sh --landing "Landing page for resume tool" # brochure-only (faster)
./demo.sh --compose "SaaS dashboard MVP"           # Docker UI on :9080
```

Requires Docker + LLM keys in the container env. Opens **Admin → Pipeline**; a full run still takes **several minutes** — this is not instant magic, it’s visible autonomy.

### Packaging & live URLs

- **Auto-publish** — After **DevOps**, optionally deploy `data/code/<product_id>/` to **Vercel**, **Netlify**, or **Cloudflare Pages** (Admin → Settings → Auto-publish). Tokens via env (`VERCEL_TOKEN`, `NETLIFY_AUTH_TOKEN`, `CLOUDFLARE_API_TOKEN`). Details: **[docs/auto-publish.md](docs/auto-publish.md)**. Manual: `python3 scripts/publish_product_now.py prod-…`.
- **Full_software → cloud (e.g. Railway)** — For DB + API stacks, static auto-publish is not enough. Admin → Settings → **Railway (full_software)** sets `general.railway_*` and `RAILWAY_TOKEN` in env; after DevOps, `data/state/<product_id>/railway_deploy.json` is written for CI. See **[docs/deploy-full-software-cloud.md](docs/deploy-full-software-cloud.md)**.
- **Demo replay video** — Record `docs/gallery/recordings/pipeline-demo-latest.webm`, then enable Live Monitor replay: `python3 scripts/sync_demo_replay_from_recording.py` (copies into admin upload dir + enables config).
- **Batch demos** — `./batch-demo.sh` runs five preset phrases through **`demo.sh`** (requires the stack up).
- **“Built with AI-Factory” badge** — Admin → Settings: optional fixed-corner link on generated `*.html` (points to your GitHub repo for a viral loop).

---

**North star:** turn a **short plain-language brief** into a **presentable web page** you can share — with **quality gates** (demo/TZ, browser smoke, optional marketplace rules) so sloppy stubs get reworked. **One pipeline** for everyone: **autonomous** mode starts with a dedicated **Discovery layer** (external signals → validation → scoring/ranking) before creating `IDEA_RECEIVED`; **on-demand** runs the same downstream stages (research → spec → architecture → code → QA → security → DevOps → marketing → sales → evolution).

Technical overview: autonomous AI-powered software development pipeline — specialized agents orchestrated with LLM failover, admin console, storefront, optional crypto payments, monitoring.

See **[docs/product-concept.md](docs/product-concept.md)** for positioning, guarantees, default **~$4.99 USDT** landing pricing when no product price is set, i18n (`NEXT_PUBLIC_MARKETING_LOCALE`), and fork branding. **Homepage → Admin:** phrase prefill and `/admin?tab=new-product&idea=…` are documented in **[docs/marketing.md](docs/marketing.md)**.

## Screen recordings & Git remotes

`.git/config` is **local** and is not pushed by Git — but your **`origin`** URL may embed credentials (`http://user:token@host/...`). Before **screen recordings**, **live demos**, or **streaming**, avoid showing `git remote -v` (and similar) if that URL is sensitive. Prefer a credential-free remote URL (HTTPS without embedded credentials), for example:

`git remote set-url origin https://gitea.example.org/<owner>/<repo>.git`

(or `https://github.com/<you>/<repo>.git` if that is your host.)

## CI/CD

The repository includes:

- Gitea workflow: `.gitea/workflows/deploy.yml`
- GitHub workflow: `.github/workflows/ci.yml`
- **Pre–GitHub release:** [docs/github-release-checklist.md](docs/github-release-checklist.md) (secrets, default non-auto mode, CI, deploy tokens)

By default, local Compose endpoints are:

| What | URL |
|------|-----|
| **App (Compose defaults)** | `http://localhost:9080` |
| **API health** | `http://localhost:9081/api/health` |
| **Prometheus** | `http://localhost:9090` |
| **Grafana** | `http://localhost:9082` |

For hosted deployments, set endpoints via environment variables/secrets in your CI runner instead of hardcoding hostnames in the repository.

Also included for portable CI in this repo:
- **GitHub Actions workflow:** `.github/workflows/ci.yml`
  - backend: `pytest -q`
  - frontend: `npm run build`

### Full Pipeline Smoke (mandatory gates + browser)

Run one command to verify the stack is presentable end-to-end for a product:

```bash
docker compose exec -T app /app/venv/bin/python3 /app/scripts/full_pipeline_smoke.py <product_id>
```

This smoke enforces:
- API + frontend health checks
- `tests/test_demo_quality_gates.py`
- realistic combined bar from `scripts/real_e2e_smoke.py` (demo gates + headless Chromium E2E: **static**, **FastAPI/uvicorn**, or **Docker** preview — see [docs/pipeline-operations.md](docs/pipeline-operations.md))

**Policy audit:** the pipeline worker periodically re-checks completed products against **current** marketplace rules (`AIFACTORY_POLICY_AUDIT_*` in `.env.example`) and queues developer fixes when standards tighten.

**Also documented:** periodic **market monitoring** for COMPLETED products, optional **monitoring → developer refresh**, and **storefront category** resolution (pipeline vs marketing vs inference) — see **[docs/pipeline-operations.md](docs/pipeline-operations.md)**.

### Discovery (pre-pipeline)

- **Goal:** find what to build before main pipeline starts.
- **Engine:** `director/discovery_pipeline.py`
- **Sources:** direct Reddit/HN/GitHub API connectors + fallback search sources (ProductHunt, review pages, StackOverflow).
- **Flow:** Signal Collector -> Need Validation -> Idea Scorecard -> Ranked ideas -> top idea enqueued as `IDEA_RECEIVED`.
- **Depth layer:** Problem Interview Simulator + Competitive Gap Analysis + TAM/SAM/SOM estimation + pain-to-feature mapping.
- **Artifacts:** `/app/data/discovery/signals.jsonl`, `/app/data/discovery/ranked_ideas.json`, `/app/data/discovery/weekly_digest.md`.
- **Continuous mode:** Director scheduler refreshes discovery queue automatically (`AIFACTORY_DISCOVERY_INTERVAL_HOURS`, signal TTL/size pruning envs).

Run manually from CLI:

```bash
ai-company discover --top-k 5
ai-company discover --top-k 5 --enqueue
ai-company create-ideas-batch --ideas-file ./ideas.txt --mode continue_on_error
```

Run from admin API (JWT required):

```bash
POST /api/admin/discovery/run
{
  "create_product": true,
  "top_k": 5
}
```

Read queue in admin API:

```bash
GET /api/admin/discovery/ideas?limit=20
POST /api/admin/products/create-batch
GET /api/admin/products/batch/{batch_id}
```

Repository licensing and contribution policy:
- `LICENSE` (MIT)
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`

---

## Documentation

End-user and admin documentation (icons match the UI, step-by-step sections, screenshots in the repo):

- **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — **illustrated user guide** (step-by-step, screenshots): storefront, `/docs`, New product wizard, Workshop, error recovery
- **[docs/owner-guide.md](docs/owner-guide.md)** — **platform owner handbook** (English): scenarios, Mermaid diagrams, storefront controls, pitfalls
- **[docs/api-integration-guide.md](docs/api-integration-guide.md)** — REST auth, router map, curl examples (use with Swagger `/api/docs`)
- **[docs/cli-reference.md](docs/cli-reference.md)** — container CLI commands vs stubs
- **[docs/README.md](docs/README.md)** — index, screenshot gallery, admin navigation map
- **[docs/admin-guide.md](docs/admin-guide.md)** — every Admin Panel tab explained
- **[docs/corporate-chat-vs-discussions.md](docs/corporate-chat-vs-discussions.md)** — Corporate Chat vs Brainstorming: differences and code locations
- **Refresh screenshots:** from `web/frontend` run `npm run capture-docs-screenshots` (UI must be running; see [docs/assets/screenshots/README.md](docs/assets/screenshots/README.md))

## Quick Start

### 1. Prepare data directory (first time only)

```bash
mkdir -p ~/aicom-data
```

### 2. Build & run with one command

```bash
chmod +x run.sh        # make executable (first time)
./run.sh               # build image & start container
```

**Faster hook:** after the stack is up and LLM keys are set in the container env, enqueue an idea and jump to Pipeline:

```bash
chmod +x demo.sh   # once
./demo.sh "Marketing landing for AI resume coach"
```

Or skip rebuild if the image already exists:

```bash
./run.sh --no-build
```

> **⚠️ IMPORTANT: Always use `run.sh` for data persistence!**
>
> `run.sh` mounts **`~/aicom-data:/app/data`** as a **bind mount** — a directory on your host.
> Your pipeline products, LLM provider configs, API keys, and logs live here and **survive**
> container rebuilds, restarts, and image updates.

### 3. Manual `docker run` (without the script)

If you must run without the script, use the **identical bind mount path**:

```bash
docker run -d --name ai-factory --restart unless-stopped \
  -p 8080:8080 -p 8081:8081 \
  -v ~/aicom-data:/app/data \
  --add-host host.docker.internal:host-gateway \
  ai-factory:latest
```

> **🚨 CRITICAL: Use `-v ~/aicom-data:/app/data` (bind mount), NOT a Docker named volume!**
>
> A **bind mount** (`~/aicom-data:/app/data`) stores data in a real directory on your host at `~/aicom-data`.
> A **Docker named volume** (e.g., `ai-factory-data:/app/data`) stores data in Docker's internal storage —
> **invisible from your host filesystem**. If you accidentally use a named volume, then later
> switch back to a bind mount, your old data appears **permanently lost** (it's still in the
> named volume, but detached from any container).
>
> ✅ **Bind mount** → data lives at `~/aicom-data/` — you can `ls`, `cp`, `tar`, `rsync` it.
> ❌ **Named volume** → data is hidden inside Docker's internal storage.

### 4. Stop & restart with same data

```bash
docker stop ai-factory && docker rm ai-factory
# then run `./run.sh --no-build` again
```

### 5. Recovering lost data from a Docker named volume

If you previously ran with a named volume (e.g., `aicom_data` or `ai-factory-data`) and want to
migrate data to the bind mount:

```bash
# 1) Start a temporary container that mounts BOTH the named volume and the bind mount
docker run -d --name temp-migrate \
  -v aicom_data:/old-data:ro \
  -v ~/aicom-data:/new-data \
  alpine tail -f /dev/null

# 2) Copy data from the named volume to the bind mount
docker exec temp-migrate cp -a /old-data/. /new-data/

# 3) Clean up
docker stop temp-migrate && docker rm temp-migrate

# 4) Now run with the bind mount (run.sh or manual)
./run.sh --no-build
```

---

## Docker Compose (Prometheus + Grafana)

For a full monitoring stack with Prometheus metrics scraping and a pre-built Grafana dashboard,
use the Docker Compose setup. This launches 3 services:

| Service     | Internal Port | Published Port | Description                           |
|-------------|---------------|----------------|---------------------------------------|
| App         | 8080 / 8081   | 9080 / 9081    | AI-Factory frontend + backend + metrics |
| Prometheus  | 9090          | 9090           | Metrics scraping & storage            |
| Grafana     | 3000          | 9082           | Dashboard visualization               |

### Prerequisites (Compose)

Use **Docker Compose V2** (`docker compose`). On Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
docker compose version
```

Legacy **docker-compose** (Python v1) often breaks against modern Docker (`ContainerConfig`); upgrade the plugin.

### Quick Start with Docker Compose

```bash
cp .env.example .env                          # optional: ports, Grafana password
chmod +x run-compose.sh scripts/init-compose-volumes.sh
./scripts/init-compose-volumes.sh             # Prometheus/Grafana bind-mount ownership
sudo ./scripts/init-compose-volumes.sh        # if ./data was created as root
./run-compose.sh --build                      # build & start app + Prometheus + Grafana
```

Ports default to **9080** (UI), **9081** (API), **9090** (Prometheus), **9082** (Grafana). Override with `AICOM_PORT_*` in `.env`.

### Access URLs

| Service     | URL (defaults)                       | Credentials              |
|-------------|--------------------------------------|--------------------------|
| App         | http://localhost:9080                | admin / admin123 (Admin UI) |
| API Health  | http://localhost:9081/api/health     | —                        |
| Metrics     | http://localhost:9081/metrics        | —                        |
| Prometheus  | http://localhost:9090               | —                        |
| Grafana     | http://localhost:9082               | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in `.env` (defaults: admin / admin) |

### Production checklist (honest)

- Set **`GRAFANA_ADMIN_PASSWORD`**, rotate **admin** password after first login; store **LLM/API keys** only in `.env` or secrets manager, not in git.
- Configure Git credentials via credential helper (not embedded remote URLs), for example: `git config --global credential.helper store` or your OS keychain helper.
- **Customer JWT** is persisted under `data/secrets/customer_jwt.key` by the container entrypoint so purchases survive restarts.
- **Stripe self-serve plans**: set `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET`, then use `POST /api/customer/billing/stripe/checkout` and point Stripe webhook to `POST /api/customer/billing/stripe/webhook` for automatic `free -> maker/studio/enterprise` entitlement updates.
- **Referral system**: customer dashboard now exposes personal referral links via `GET /api/customer/referrals/me`; checkout attribution is stored per order (`referral_source`).
- **Payments**: on-chain verification is real; **jurisdiction, tax, KYC/AML**, and **wallet custody** are your legal/compliance scope — not solved by this repo alone.
- Put **HTTPS** and a reverse proxy (nginx, Caddy, Traefik) in front for public traffic.
- **Public hostname (this fleet):** `magic-ai-factory.com` — nginx on **:80** → Compose **9080**, `NEXT_PUBLIC_SITE_URL`, image rebuild: **[docs/production-domain.md](docs/production-domain.md)** (includes checked-in `deploy/nginx/magic-ai-factory.com.conf`).

### Grafana Dashboard

The `AI Factory Overview` dashboard is auto-provisioned and contains **14 panels** across **5 rows**:

**Row 1: Pipeline Overview** (4 Stat panels)
- **Active Products** — Count of products in non-terminal states (`IN_PROGRESS`, `REVIEW`, `TESTING`, `DEPLOYING`)
- **Total Products Created** — 24h increase of products created
- **Pending Tasks** — Current count of pending pipeline tasks
- **Failed Tasks (24h)** — 24h increase of failed tasks

**Row 2: Products by State**
- **Products by State** — Pie chart showing product distribution across all pipeline states

**Row 3: Tasks & Performance** (3 panels)
- **Tasks by Status** — Stacked bar chart of pending/running/completed/failed task rates
- **Task Duration (P99)** — 99th percentile task duration stat
- **Avg Task Duration by Agent** — Horizontal bar gauge per agent type

**Row 4: Director AI** (2 panels)
- **Director Decisions (24h)** — Time series of Director AI decisions grouped by action
- **Director Analysis Duration** — Gauge showing average analysis cycle duration

**Row 5: LLM Provider Health** (4 panels)
- **LLM Requests by Provider** — Stacked bar chart of LLM request rates
- **LLM Error Rate** — Time series showing error rate percentage
- **Provider Health** — Stat panel showing UP/DOWN status per provider
- **LLM Latency (P95)** — Gauge showing 95th percentile LLM request latency

### Docker Compose Commands

```bash
./run-compose.sh              # start (uses docker compose)
./run-compose.sh --build      # rebuild images
./run-compose.sh --down       # stop (./data bind mount kept)
./run-compose.sh --down-volumes  # stop + remove compose-named volumes (still keeps ./data)
./run-compose.sh --logs
docker compose up --build -d  # equivalent manual invocation
```

### SQLite with Docker Compose

SQLite is **enabled by default** in Compose (`USE_SQLITE=true`). The entrypoint migrates existing `pipeline.json` into SQLite when present. Data persists in **`./data`** on the host (bind mount).

To disable SQLite and use the JSON backend only, override in `docker-compose.yml` or run the single-container `run.sh` flow with `USE_SQLITE=false`.

---

## Access

| Service | URL | Port |
|---------|-----|------|
| Frontend (Main) | http://localhost:8080 | 8080 |
| Backend API | http://localhost:8081 | 8081 |

## Admin Panel

- **URL**: http://localhost:8080/admin/login
- **Login**: `admin`
- **Password**: `admin123`

## API Endpoints

### Public
- `GET /api/health` — Health check
- `GET /api/products` — List published products
- `GET /api/products/{id}` — Product details
- `GET /api/config/theme` — Current theme
- `POST /api/feedback/submit` — Submit feedback
- `POST /api/payment/create` — Create payment
- `GET /api/payment/chains` — Supported chains

### Admin (requires auth)
- `POST /api/admin/auth/login` — Login (returns JWT token)
- `GET /api/admin/dashboard` — Dashboard metrics
- `GET /api/admin/pipeline/products` — Pipeline status
- `POST /api/admin/products/create` — Create product idea
- `GET /api/admin/agents` — Agent statuses
- `GET /api/admin/providers` — LLM provider configs
- `GET /api/admin/security/logs` — Security audit logs
- `POST /api/admin/config/theme` — Set theme

## Pipeline Agents

**Admin → AI Agents** shows **11 roster rows** (same order as `web/frontend/lib/pipelineStages.ts`):

1. **Analyst** — Market research / competitive context feeding the spec
2. **PM** — Specifications from product ideas
3. **Architect** — System architecture
4. **Designer** — UX/design layer (paired with Architect output in the UI; not a separate LLM class)
5. **Developer** — Code generation
6. **QA** — Automated testing, static analysis, bug detection
7. **Security** — Vulnerability scanning, secrets, dependency audit
8. **DevOps** — Docker/K8s config, CI/CD, monitoring
9. **Marketing** — Go-to-market strategy, content
10. **Sales** — Pricing tiers, sales strategy
11. **Evolution Analyst** — Post-ship evolution and improvements

The **pipeline worker** (`pipeline_worker.py`) also loads **Design critic** and **Hardening** as separate LLM agents (**12 modules** total). Those stages are optional hops in the graph (see `AIFACTORY_EXTENDED_PIPELINE` in `.env.example` / `orchestrator/state_machine.py`); they are not separate rows on `/api/admin/agents`, which is why the console lists **11** slots, not 13.

## Pipeline States

`IDEA_RECEIVED` → `SPEC_WRITTEN` → `ARCH_DESIGNED` → `CODE_COMMITTED` → `QA_TESTED` → `SECURITY_SCANNED` → `DEVOPS_DEPLOYED` → `MARKET_CONTENT_READY` → `SALES_ACTIVE` → `DEPLOYED_PRODUCTION` → `EVOLUTION_ANALYZING` → `COMPLETED`

## Architecture

High-level runtime layout (rendered on GitHub and compatible Markdown viewers):

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

Ports assume defaults inside the container; with Compose they map to **9080** / **9081** on the host (see [Docker Compose](#docker-compose-prometheus--grafana)).

## SQLite / JSON Backend Behavior

`PipelineStateMachine` now chooses backend by runtime context:
- if a specific `state_file` path is passed (typical tests/local file runs) -> JSON mode;
- otherwise -> follows `USE_SQLITE` env (runtime default in this project is SQLite-enabled).

So JSON is still supported, but production/runtime paths are SQLite-first.

### Force SQLite explicitly

Set `use_sqlite=True` when creating the state machine:

```python
from orchestrator.state_machine import PipelineStateMachine

sm = PipelineStateMachine(use_sqlite=True, db_path="/app/data/state/pipeline.db")
```

### Migrate from JSON to SQLite

Use the CLI migration utility to transfer existing data:

```bash
# Inside the container
python -m orchestrator.migrate \
    --json /app/data/state/pipeline.json \
    --db /app/data/state/pipeline.db

# Or from host via docker exec
docker exec ai-factory python -m orchestrator.migrate \
    --json /app/data/state/pipeline.json \
    --db /app/data/state/pipeline.db
```

Or call the migration method programmatically:

```python
from orchestrator.state_machine import PipelineStateMachine

sm = PipelineStateMachine("/app/data/state/pipeline.json")
result = sm.migrate_json_to_sqlite("/app/data/state/pipeline.db")
print(f"Migrated {result['products_migrated']} products, {result['tasks_migrated']} tasks")
```

> **Note**: Migration reads JSON and inserts into SQLite.
> The JSON file is not modified; both backends remain available.

### SQLite Schema

Two tables with foreign keys and indexes:

| Table | Key Columns | Indexes |
|-------|-------------|---------|
| `products` | `id`, `idea`, `state`, `created_at`, `updated_at`, metadata JSON fields | `idx_products_state` |
| `tasks` | `id`, `product_id`, `agent_type`, `status`, `state`, timestamps, `output` (JSON), `priority` | `idx_tasks_product_id`, `idx_tasks_status` |

Nested fields (`spec`, `architecture`, `tags`, `output`, etc.) are stored as JSON strings
and automatically serialized/deserialized by `SQLiteManager`.

## Testing

Run tests inside the Docker container:

```bash
# All pipeline tests (JSON backend) — 79 tests
docker exec ai-factory python -m pytest tests/test_pipeline.py -v

# SQLite backend tests — 40 tests
docker exec ai-factory python -m pytest tests/test_pipeline_sqlite.py -v

# Run both suites together
docker exec ai-factory python -m pytest tests/test_pipeline.py tests/test_pipeline_sqlite.py -v
```

## Tech Stack

- **Backend**: Python FastAPI + Uvicorn
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS + Framer Motion
- **Container**: Docker (Python 3.11 + Node.js 20)
- **Security**: JWT auth, SHA256-salted passwords, TOTP 2FA, audit logging
- **LLM**: Pluggable provider system (OpenAI-compatible, Ollama)
- **State Persistence**: SQLite3 runtime backend with JSON compatibility mode
