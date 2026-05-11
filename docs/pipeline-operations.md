# Pipeline operations: discovery, audits, monitoring, storefront categories

Operational behavior of the **pipeline worker** and related services after deploy. All tunables below are also listed (commented) in **`.env.example`**.

## Discovery (pre-pipeline opportunity phase)

Before `IDEA_RECEIVED`, autonomous mode now runs a dedicated Discovery stage in `director/discovery_pipeline.py`:

- **Signal Collector**: gathers continuous external signals with direct API connectors:
  - Reddit: `/search.json`
  - Hacker News: Algolia HN API (`hn.algolia.com`)
  - GitHub: REST search API (`/search/repositories`)
  - plus fallback web-search sources (ProductHunt/review pages/StackOverflow and API fallback).
  Signals are normalized and appended to `/app/data/discovery/signals.jsonl`.
- **Need Validation**: converts signals into candidate opportunities with rationale and validation notes.
- **Problem Interview Simulator**: per-idea LLM interview simulation (virtual personas, willingness-to-pay, objections).
- **Need Depth Analysis**: competitor gap analysis + TAM/SAM/SOM estimate + pain-to-feature mapping.
- **Idea Scoring**: objective weighted scorecard (`tam`, pain severity, differentiation, feasibility, strategic fit, evidence strength, inverse effort).
- **Ranking output**: `/app/data/discovery/ranked_ideas.json` + weekly digest `/app/data/discovery/weekly_digest.md`.
- **Anomaly detector**: flags top-score shifts between cycles in ranked ideas payload.
- **Category balancing enforcement**: ranking includes balancing bonus/penalty so overloaded categories are deprioritized.
- **Source health**: per-source health file with latency, fail streak, backoff and status at `/app/data/discovery/source_health.json`.

Director auto-pipeline now picks the top-ranked opportunity and only then creates a normal product in `IDEA_RECEIVED`, so the existing main pipeline remains unchanged.

Manual trigger endpoint (admin JWT): `POST /api/admin/discovery/run`.  
Idea queue endpoint (admin JWT): `GET /api/admin/discovery/ideas`.

### Discovery scheduling and retention

Discovery runs continuously via Director scheduler (independent from manual CLI/API trigger):

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_DISCOVERY_INTERVAL_HOURS` | `6` | Scheduled discovery refresh interval |
| `AIFACTORY_DISCOVERY_SIGNAL_TTL_DAYS` | `30` | TTL for old signal rows in `signals.jsonl` |
| `AIFACTORY_DISCOVERY_SIGNAL_MAX_ROWS` | `5000` | Hard cap for signal DB rows after pruning |

Runtime controls implemented in code:
- per-source min interval (rate limit),
- exponential backoff after failures,
- health status (`healthy`/`degraded`/`unhealthy`) from fail streaks.

## Policy audit (finished products vs current rules)

The worker re-evaluates products in **COMPLETED** / **DEPLOYED_PRODUCTION** against **current** marketplace / demo quality (`evaluate_marketplace_quality`). If they no longer qualify, the pipeline sets **BUG_FOUND** and enqueues a **developer** task (same repair path as QA gate failures), bounded by **`AIFACTORY_MAX_QUALITY_LOOPS`**.

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_POLICY_AUDIT_ENABLED` | `1` | Master switch |
| `AIFACTORY_POLICY_AUDIT_INTERVAL_SEC` | `900` | Seconds between audits (`0` = only startup, if enabled) |
| `AIFACTORY_POLICY_AUDIT_ON_START` | `1` | Run once when the worker starts |

Implementation: `web/backend/services/policy_audit.py`, invoked from `pipeline_worker.py`.

## QA browser E2E (Playwright)

QA runs `web/backend/services/browser_preview_e2e.py`: Chromium loads the generated product and performs a **deep crawl** (same-origin BFS), optional **forms/button** probes, and optional **declarative scenarios** for SPA/login flows.

### How the preview is served (not “disk-only”)

| Mode | When | Behavior |
|------|------|----------|
| **static** | Only `index.html` tree (no FastAPI entry) | Local `ThreadingHTTPServer` from `data/code/<product_id>/`. |
| **fastapi** | `AIFACTORY_BROWSER_E2E_SERVE_MODE=auto` (default) and a FastAPI `main.py` is detected | **Uvicorn** on `127.0.0.1` — sessions/cookies and server-rendered routes behave like a real app; same pattern as sandbox live preview. |
| **docker** | `AIFACTORY_BROWSER_E2E_SERVE_MODE=docker`, or `AIFACTORY_BROWSER_E2E_AUTO_DOCKER=1` in **auto** when a `Dockerfile` exists | `docker build` + `docker run -p` for the product image (slower; needs Docker socket). |

Entry URL for FastAPI/Docker defaults to `/` (`AIFACTORY_BROWSER_E2E_ENTRY_PATH`). Map the container port with `AIFACTORY_BROWSER_E2E_DOCKER_CONTAINER_PORT` (default `8000`).

### Crawl limits (large sites)

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_BROWSER_MAX_PAGES` | **100** | Maximum distinct URLs visited in the BFS crawl. |
| `AIFACTORY_BROWSER_MAX_DEPTH` | `10` | Maximum link depth from the **current** start URL (after optional scenarios). |

BFS cannot exhaust arbitrary SPAs; add **`e2e-scenarios.json`** in the product code dir (or `AIFACTORY_BROWSER_SCENARIO_FILE`) for scripted navigation/login — see `web/backend/services/browser_e2e_scenarios.py`. Disable scenarios with `AIFACTORY_BROWSER_SCENARIOS=0`.

**CI guard:** workflow job **`browser-login-e2e`** installs Chromium (`playwright install chromium --with-deps`) and runs **`tests/test_browser_fastapi_login_integration.py`** against **`tests/fixtures/minimal_fastapi_login/`** (uvicorn + cookie login). The default backend pytest job skips that test when browsers are not installed.

### Live Monitor demo replay (embedded video)

Admins can attach a **screen recording** of the landing/pipeline flow for operators:

- **UI:** Admin → **Live Monitor** → **Demo replay**, or **Settings** → **Demo replay** (same controls: toggle, title, external URL, or upload `.webm` / `.mp4` / `.mov`).
- **API:** `GET/PATCH /api/admin/demo-replay`, `POST /api/admin/demo-replay/upload`, streamed uploads at `GET /api/admin/demo-replay/media/<file>` (admin auth).
- **Metrics:** Dashboard + SSE include **`demo_replay`** `{ enabled, title, play_url }` so other clients can mirror the clip.
- **Disk:** `{DATA_ROOT}/config/pipeline_demo_replay.json` and `{DATA_ROOT}/public/pipeline_demo_replay/`. Upload limit **`AIFACTORY_PIPELINE_DEMO_MAX_MB`** (default 120).

Agent workflow guidance lives in **`.cursor/skills/pipeline-demo-video/SKILL.md`** (Playwright `record_video_dir`, upload path).

### Sandbox vs QA

For **live API behind the marketplace iframe**, enable **`AIFACTORY_SANDBOX_PREVIEW_API=1`** on the factory backend so `/api/sandbox/backend/{sandbox_id}/…` proxies to uvicorn (generated FastAPI). That is independent of QA’s E2E serve modes but uses the same preview starter (`sandbox_preview_api`).

When the product repo includes **`docker-compose.yml`** (recommended for full-stack builds), **`AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1`** (default in Compose) runs **`docker compose up -d --build`** for that product’s code dir and exposes the stack at **`/api/sandbox/compose/{sandbox_id}/…`** (reverse-proxy to the published web/API port). Built images must publish ports via env vars such as **`API_HOST_PORT`** / **`WEB_HOST_PORT`** so the host can bind free ports. Set **`AIFACTORY_SANDBOX_COMPOSE_PREVIEW=0`** to skip compose and fall back to uvicorn preview + static file serving.

## Storefront readiness remediation loop

`COMPLETED`/`DEPLOYED_PRODUCTION` products are re-checked against storefront eligibility and can be reopened for `developer -> DEV_FIXING` if they still fail marketplace criteria (missing code artifacts or marketplace quality gates).

This is an iterative convergence loop: products are reworked until they pass storefront gates or exhaust their repair budget.

| Variable | Default in code | Meaning |
|----------|-----------------|---------|
| `AIFACTORY_MAX_QUALITY_LOOPS` | `10` | Maximum remediation cycles for one product before forced `FAILED` |

### Methodologist gate (domain process compliance)

The pipeline includes a first-class **Methodologist Agent** (`methodologist`) that verifies whether a product follows the generally accepted process for its domain, separate from UI polish, code quality, or generic QA.

It runs at two control points:

1. **Post-specification:** PM output is checked before architecture/development. If the spec does not describe the required domain entities, roles, lifecycle, and core capabilities, PM retries with methodology findings as repair hints.
2. **Post-implementation:** QA runs an implementation scan over generated artifacts. If the product does not implement the domain process shape, QA marks the product as needing fixes and the normal `BUG_FOUND -> DEV_FIXING` loop applies.

Each domain pack (schema v2) declares: matching keywords/categories, required entities and their fields, user roles, capabilities, a **lifecycle graph** (states + transitions), acceptance scenarios, expected API surface, KPI formulas, regex/keyword red flags, and reference standards. Packs live in `web/backend/services/domain_methodology/packs/` (one module per domain).

Built-in domain packs currently cover:

- CRM / sales pipeline
- Helpdesk / IT support
- E-commerce
- LMS / education
- HR / recruiting ATS
- Project / task management
- Finance / billing
- Healthcare / wellness
- Analytics / BI
- DevTools / ops platform

Artifacts:

- `data/state/<product_id>/methodology_spec_review.json`
- `data/telemetry/<product_id>/methodology_implementation.json`
- `data/methodology/cases/<product_id>.json` (review history)
- `data/methodology/lessons.jsonl` (operator and auto-promoted lessons)
- `data/methodology/feedback.jsonl` (operator feedback log)
- QA report fields: `methodology_review`, `methodology_gate_passed`

Storefront policy also evaluates methodology by default. A failed methodology gate produces `methodology_review_failed` (plus `methodology:<finding_code>`) and routes the product back to rework through the existing quality remediation loop.

#### Search and learning loop

The methodologist supports search and online learning:

- **Lessons** — operator-supplied red-flag rules that augment built-in packs. Created via admin UI/API; evaluated on every spec/implementation review.
- **Feedback → auto lessons** — when an operator confirms a finding was correct (`POST /api/admin/methodology/feedback` with `promote_finding_code`), the methodologist auto-creates a lesson with the same shape so similar future products fail faster.
- **Case history** — every review writes a `MethodologyCase` (per `product_id`); searchable by free-text query and domain.

Admin endpoints (require admin auth):

```
GET    /api/admin/methodology/domains
GET    /api/admin/methodology/domains/{domain_id}
POST   /api/admin/methodology/domains/match
POST   /api/admin/methodology/review/spec
POST   /api/admin/methodology/review/implementation/{product_id}
GET    /api/admin/methodology/cases/{product_id}
GET    /api/admin/methodology/lessons
POST   /api/admin/methodology/lessons
PATCH  /api/admin/methodology/lessons/{lesson_id}
DELETE /api/admin/methodology/lessons/{lesson_id}
GET    /api/admin/methodology/search?q=...
POST   /api/admin/methodology/feedback
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY` | `1` | Block storefront listing when domain methodology review fails |

### Throughput and backlog controls

These parameters control whether the system keeps creating new products or spends capacity on advancing existing ones:

| Variable | Default in code | Meaning |
|----------|-----------------|---------|
| `AIFACTORY_MAX_RUNNING_TASKS` | `16` | Global cap of simultaneously `running` tasks in the queue |
| `AIFACTORY_TASK_EXECUTOR_CONCURRENCY` | `6` | Parallelism for executing running tasks per worker cycle |
| `AIFACTORY_AUTOPIPELINE_BACKLOG_PAUSE_IDEA_RECEIVED` | `250` | Pause autonomous product creation at/above this `IDEA_RECEIVED` backlog |
| `AIFACTORY_AUTOPIPELINE_BACKLOG_RESUME_IDEA_RECEIVED` | `120` | Resume autonomous product creation only when backlog drops to/below this value |

`PAUSE`/`RESUME` thresholds intentionally use hysteresis (`resume < pause`) to prevent rapid on/off flapping.

### Current docker-compose overrides

`docker-compose.yml` currently overrides some defaults for aggressive recovery:

- `AIFACTORY_MAX_QUALITY_LOOPS=25`
- `AIFACTORY_MAX_RUNNING_TASKS=24`
- `AIFACTORY_TASK_EXECUTOR_CONCURRENCY=12`

If you run without Compose overrides, code defaults above apply.

### Can a product be impossible to fix?

Yes. A product can still end up `FAILED` if:

- repeated remediation cannot satisfy marketplace quality gates,
- generated artifacts remain structurally insufficient for storefront requirements,
- or the product exhausts `AIFACTORY_MAX_QUALITY_LOOPS`.

This is expected behavior to prevent infinite repair loops and unbounded LLM spend.

## Non-bypassable release discipline

- Any production release candidate that fails `release_cockpit` is forced back to `BUG_FOUND` and a `developer/DEV_FIXING` task is queued.
- Any product with `no-go` status is not allowed to remain `COMPLETED` in production mode.
- Missing release artifacts/metrics are treated as `no-go` through `quality_constitution` + `release_cockpit` checks.
- Benchmark gate is now **built-in hard policy** (no env override): latest pass-rate, scorecard freshness, and minimum recent run count are enforced from `web/backend/services/benchmark_gate.py`.

Implementation: `pipeline_worker.py::_release_critic`, `web/backend/services/release_cockpit.py`.

## Batch pipeline (up to 10 ideas per batch)

Bulk ingestion is supported with queue-based draining and concurrency control:

- API: `POST /api/admin/products/create-batch` with payload:
  - `ideas: string[]` (max 10)
  - `mode: continue_on_error | fail_fast`
  - `max_immediate_start`, `active_limit`
- API status: `GET /api/admin/products/batch/{batch_id}`
- CLI: `ai-company create-ideas-batch --ideas-file ...` or repeated `--idea`.

Queue file: `/app/data/state/batch_pipeline_queue.json`.  
Worker drain controls:

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_BATCH_PIPELINE_MAX_START_PER_CYCLE` | `2` | Max queued ideas materialized per worker cycle |
| `AIFACTORY_BATCH_PIPELINE_ACTIVE_LIMIT` | `30` | Stop materializing when active products reach limit |

## Published benchmark metrics (investor-ready)

`GET /api/admin/benchmark/scorecard` now includes `investor_metrics`:

- rolling 24h and 7d pass-rates,
- trend vs 7d average,
- 95% confidence interval,
- production readiness index.

## Periodic market monitoring (COMPLETED products)

For each **COMPLETED** product, the worker may enqueue an **analyst** task (`mode: monitoring`) to compare research/telemetry with the shipped slice. Interval is configurable; **`0`** disables scheduling.

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_MARKET_REVISION_INTERVAL_SEC` | `86400` | Seconds between monitoring tasks per product (`0` = off) |

Implementation: Phase 5 in `pipeline_worker.py`.

## Monitoring → developer refresh (optional)

If the analyst monitoring JSON sets **`request_implementation_refresh`: true** (and **`implementation_refresh_brief`**), the worker can enqueue **developer / DEV_FIXING** so the slice is regenerated, using the same repair budget as QA. Disabled with:

| Variable | Default | Meaning |
|----------|---------|--------|
| `AIFACTORY_MONITORING_DEV_REFRESH_ENABLED` | `1` | Allow monitoring-led developer tasks |

Prompt fields are defined in `agents/analyst.py` (`ANALYST_MONITOR_PROMPT`). The Developer agent adds a short **post-launch market monitoring** note when `monitoring_refresh_trigger` is set (`agents/dev.py`).

## Storefront categories (tabs vs “Other”)

Listing and tab counts use **`marketplace_taxonomy.canonical_marketplace_category`**: the pipeline’s **`product["category"]`** slug wins over a noisy **`category`** field inside marketing JSON; unknown values map with aliases; a light keyword pass uses idea/tags/marketing blurbs before **Other** (`uncategorized`).

Canonical IDs: **`ai_ml`**, **`devtools`**, **`fintech`**, **`saas`**, **`ecommerce`**, **`iot`**, **`security`**, **`productivity`**.

Code: `marketplace_taxonomy.py`, `web/backend/api/products.py`. Autonomous discovery keeps category distribution balanced through `director/discovery_pipeline.py`.

## LLM defaults (agents + new providers)

Shared numeric defaults (context / max output tokens / heavy-agent timeouts) live in **`llm/factory_defaults.py`** and are used by agents and admin provider templates. Provider APIs may still cap lower than requested.

## LLM response cache

Router-level in-memory cache reduces repeated prompt latency/cost for identical request keys:

| Variable | Default | Meaning |
|----------|---------|---------|
| `AIFACTORY_LLM_CACHE_ENABLED` | `1` | Enable cache |
| `AIFACTORY_LLM_CACHE_TTL_SEC` | `300` | Entry TTL in seconds |
| `AIFACTORY_LLM_CACHE_MAX_ENTRIES` | `500` | Maximum cache size before oldest-entry eviction |

Implementation: `llm/router.py`.

## Runtime test execution fallback

When generated artifacts do not include explicit `test_commands`, worker runtime checks now infer practical defaults instead of syntax-only checks:

- Python: per-file syntax checks + `pytest -q --maxfail=1` when tests are present.
- Node/JS: `npm test` when configured, otherwise `node --check` syntax validation.

Implementation: `pipeline_worker.py::_run_runtime_tests` and `_infer_default_test_commands`.

## Pipeline SLO governance loop

Director cycle evaluates pipeline SLO and emits mandatory auto-actions when breached:

- target benchmark pass-rate,
- max benchmark regression,
- mean time to remediation.

If violated, Director triggers benchmark rerun and remediation cycle automatically (no manual bypass path).

## Visual diversity (anti “clone” UIs)

Autonomous and spec-driven builds are steered so **each product’s browser UI** can diverge strongly: Director + market research ask for a concrete art-direction sentence; PM and Architect prompts demand a distinctive **`ui_experience`** (tokens, fonts, `signature_moment`, **`svg_creative_brief`** for planned vector art); the Developer stack rules bind to **`architecture.ui_experience`** first and treat **SVG as unlimited** (patterns, filters, masks, illustrated heroes, backgrounds — not icon-sized clips only). Factory fallback `ui_experience` **rotates** by hash of the product idea (`agents/architect.py` — multiple preset palettes + matching SVG briefs, not one global dark+cyan default).

---

**After changing code or `.env`:** rebuild and restart the app container so the worker and API load the new logic (e.g. `docker compose up --build -d` or `./run-compose.sh --build`).
