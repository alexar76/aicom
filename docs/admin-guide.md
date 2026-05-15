# Admin Panel — complete guide

> **New to the UI?** Read **[docs/USER_GUIDE.md](./USER_GUIDE.md)** first — illustrated “for dummies” flow (storefront, New product wizard, Workshop, actionable errors). This file is the **full tab-by-tab reference**.

This document covers **every** left-menu section of the AI-Factory v2.1 admin UI: purpose, main actions, and how they relate to APIs/data. Header icons match the sidebar ([Lucide](https://lucide.dev/), same assets in [`assets/icons/`](./assets/icons/)).

> **Login:** `/admin/login` — user **`admin`**. There is **no** default password `admin123`. On first install see **[security.md](./security.md)** (console prompt, `data/secrets/bootstrap_admin.txt`, or `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` for dev). After authentication all sections are available in one SPA (`/admin`).

![Admin login page](./assets/screenshots/admin-login.png)

---

<a id="layout"></a>
## Layout overview

![Sidebar and content (full page height)](./assets/screenshots/admin-sidebar.png)

| Area | Purpose |
|------|---------|
| Top bar | **Admin Panel** logo (<img src="./assets/icons/cpu.svg" width="16" height="16" alt="" /> same as storefront), collapse menu on mobile |
| Left navigation | Switch tabs without full page reload |
| Main area | Active tab content (`GlassCard`, dark background, grid) |
| Logout | End session (bottom of sidebar) |

---

<a id="dashboard"></a>
## Dashboard

<img src="./assets/icons/layout-dashboard.svg" width="22" height="22" alt="" /> Menu item **Dashboard**

**Purpose:** static snapshot of factory health after page load (single `GET /api/admin/dashboard` on mount).

![Dashboard](./assets/screenshots/admin-dashboard.png)

| Block | Shows |
|-------|--------|
| Four KPI cards | **Total Products**, **Active Pipeline**, **Completed**, **Failed** — aggregates from `pipeline` |
| Pipeline Metrics | **Completion Rate** progress, **Pending / Running / Timed Out** task counts |
| System Resources | **CPU**, **Memory**, **Disk** bars (`resources.*_percent`) |
| Revenue | Revenue for 24h / 7d / 30d, optional all-time and order counters |
| Security | Status and **Failed Logins** in the last 15 minutes |

Live streaming is concentrated in **Live Monitor** (Dashboard remains snapshot-first).

> Note: Dashboard `Completed` is a pipeline lifecycle counter, not storefront visibility.  
> Marketplace listing applies additional filters (state + code artifacts + marketplace quality gates), so it can be lower than Dashboard `Completed`.

---

<a id="live-monitor"></a>
## Live Monitor

<img src="./assets/icons/radio.svg" width="22" height="22" alt="" /> Menu item **Live Monitor**

**Purpose:** live monitoring via streaming metrics:
- **SSE**: `GET /api/admin/metrics/stream` (current UI path)
- **WebSocket**: `/api/admin/ws/metrics` (available for realtime clients/integrations)

| Element | Function |
|---------|----------|
| Connection status | Connecting / Connected / Error with auto-reconnect (~5 s) |
| Pause | Pause SSE handling (useful when debugging) |
| Ring indicators | Pipeline load and resource visualization |
| Agent metrics | Per-agent counters from dashboard/stream |
| Director status | Director AI summary |
| Escalations | Filter by agent type, list recent escalations |
| Activity feed | Mix of escalation entries and agent logs |
| **Demo replay** | Embedded clip when enabled: toggle, title, external URL, or upload `.webm` / `.mp4` / `.mov`. Same controls appear under **Settings** (before Theme) so you can preview or enable replay without leaving Settings; **`adminCfg.play_url`** updates immediately after save so Live Monitor picks up re-enabled replay without a full dashboard refresh. |

On first load `getEscalations` and `getAgentLogs` are also fetched for an initial feed.

See **[docs/pipeline-operations.md](pipeline-operations.md)** (Live Monitor demo replay) for API paths, disk layout, and **`demo_replay`** in metrics.

---

<a id="pipeline"></a>
## Pipeline

<img src="./assets/icons/activity.svg" width="22" height="22" alt="" /> Menu item **Pipeline**

**Purpose:** monitor all pipeline products (`GET /api/admin/pipeline/products`), filter by category (`GET` categories).

![Pipeline Monitor — product cards and stage strip](./assets/screenshots/admin-pipeline.png)

| Feature | Description |
|---------|-------------|
| **Pipeline Monitor** title | List of product cards |
| Category filter | Dropdown with layers icon — **All** or a category (AI/ML, DevTools, …) |
| Product card | Name from spec / idea, **ID**, category and state badges (`Badge`: completed / failed / active) |
| **Spec** button | Modal with specification (`GET /api/admin/products/{id}/spec`) |
| Stage strip | Agent sequence: analyst → pm → architect → developer → qa → security → devops → marketing → sales with task status colors; **click a square** opens the full task modal (queue time, agent work, metrics, `input_data` / `output_data`, errors) |
| Expanded tasks | Task details, durations, errors |

Use this view to find stuck stages and read specs without SSH.

---

<a id="storefront-operator"></a>
## Storefront & marketplace (operator)

On **Pipeline** cards for products in **COMPLETED** or **DEPLOYED_PRODUCTION**, expand the **Storefront** panel:

| Control | What it does |
|---------|----------------|
| **Manual follow-up** | `Not pursuing storefront listing` persists a reason and **removes** the product from the public catalog and **GET /api/products/{id}** (404 for shoppers). It also clears any admin force-list override. |
| **Public storefront guard** | **Hide from public storefront** sets an admin-only flag with the same public effect without changing follow-up labels. |
| **Force public storefront** | Lists the product even when automatic marketplace quality gates fail; still requires generated code on disk. Cannot be enabled while admin hide is active. Justification text is required. |
| **Marketplace copy** | Saves listing/detail text into `data/state/<product_id>/marketing_content.json` under `marketing` (name, tagline, short/selling/long descriptions). |

**Dashboard “Completed”** can be higher than storefront-visible SKUs: listing adds filters (code artifacts, quality gates, hide / not pursuing).

Operator-focused narrative + diagrams: **[owner-guide.md](./owner-guide.md)**.

---

<a id="new-product"></a>
## New Product

<img src="./assets/icons/plus.svg" width="22" height="22" alt="" /> Menu item **New Product**

**Purpose:** manually create a product idea and enqueue it in the pipeline.

| Field / action | Description |
|----------------|-------------|
| Idea text | Short product description |
| Instructions | Extra guidance for the orchestrator |
| **Landing & UI copy language** | `Auto` (match brief + admin UI language) or force a locale (`ru`, `en`, `es`, `de`, …). See [security.md § Landing language](./security.md#landing--ui-copy-language). |
| Sidebar language | **en / ru / es** (bottom of sidebar) — sent as `interface_locale` when creating a product. |
| Submit | Calls product-create API; on success prompts you to watch **Pipeline** |
| Deep link | Open **`/admin?tab=new-product`** to land on this tab. Optional **`?idea=…`** (URL-encoded phrase) pre-fills **Idea**. The public homepage can also stash text in **`sessionStorage`** key `aicom_prefill_idea` before navigating here (same tab survives login). |

Use when autonomous Director mode is off or you need a one-off task off-schedule.

---

<a id="files"></a>
## Files

<img src="./assets/icons/file-text.svg" width="22" height="22" alt="" /> Menu item **Files**

**Purpose:** browse artifact files (git-like tree via API): navigate paths, view selected product/repo files.

Use for quick checks of generated code and configs without cloning to your machine.

---

<a id="agents"></a>
## Agents

<img src="./assets/icons/bot.svg" width="22" height="22" alt="" /> Menu item **Agents**

**Purpose:** status table for specialized agents (PM, Architect, Developer, QA, …): activity, recent actions, errors.

Helps see which agent is busy or lagging before diving into **Agent Logs**. There is no separate “Designer” row in this table: UI direction is carried in **Architect** artifacts as `ui_experience` inside `data/arch/<product_id>/architecture.json`, then implemented by **Developer** (see [Product concept § Designer / UX layer](./product-concept.md#designer--ux-layer-for-investors-and-buyers)) and the **Design** step on the public homepage pipeline.

---

<a id="llm-providers"></a>
## LLM Providers

<img src="./assets/icons/cpu.svg" width="22" height="22" alt="" /> Menu item **LLM Providers**

**Purpose:** manage LLM connections (OpenAI-compatible, etc.).

![LLM Providers](./assets/screenshots/admin-providers.png)

| Capability | Details |
|------------|---------|
| Card list | Provider name, status (online / degraded / offline), **heavy** and **light** models |
| **Add Provider** | New connection (base URL, key via env, priority) |
| **Routing Rules** | Routing rules panel |
| Test (flask) | Availability and latency check for **heavy** model |
| Edit | Pencil icon — full config edit |
| On/off | Activity toggle |
| Delete | With confirmation |
| **Default** | Set default provider (star) |

API keys are not shown in plain text — set via server environment variables.

---

<a id="llm-logs"></a>
## LLM Logs

<img src="./assets/icons/scroll-text.svg" width="22" height="22" alt="" /> Menu item **LLM Logs**

**Purpose:** LLM call log (`GET /api/admin/llm/logs`) from `llm_calls.jsonl`.

![LLM Call Logs](./assets/screenshots/admin-llm-logs.png)

| Element | Description |
|---------|-------------|
| **All Providers** filter | Filters rows by `provider` |
| Refresh | Reload |
| List | Rows sorted **newest first** |
| Row | Provider, model, latency, tokens, prompt/response preview in `<details>` |
| Left indicator | Green — success, red — error |

Use for cost, timeout, and response-quality debugging.

---

<a id="agent-logs"></a>
## Agent Logs

<img src="./assets/icons/list.svg" width="22" height="22" alt="" /> Menu item **Agent Logs**

**Purpose:** JSONL agent logs (`GET /api/admin/agent/logs`) with agent-type filter and row limit.

Good for tracing pipeline decisions and searching error text in agent messages.

---

<a id="security"></a>
## Security

<img src="./assets/icons/shield.svg" width="22" height="22" alt="" /> Menu item **Security**

**Purpose:** security overview: audit logs, failed logins, product reports (depending on API implementation).

Cross-check with **Security** on the Dashboard: if failed logins spike, inspect details here.

---

<a id="sandbox"></a>
## Sandbox

<img src="./assets/icons/terminal.svg" width="22" height="22" alt="" /> Menu item **Sandbox**

**Purpose:** manage isolated environments per product: start/stop sandbox, status, **Git** ops (init, push, status), list of products that can run a sandbox.

Typical flow: generated code runs in a container; this section is used to verify sandbox URLs and push to a remote.

---

<a id="director-ai"></a>
## Director AI

<img src="./assets/icons/bar-chart-3.svg" width="22" height="22" alt="" /> Menu item **Director AI**

**Purpose:** control center for **Director**: reports, analytics, decisions requiring a human.

| Block | Description |
|-------|---------------|
| Badges | Report count; **pending** decisions count |
| **Pending Decisions** | Cards with action, goal, rationale — **Approve** / **Reject** |
| Reports | Director report files and contents |
| Analysis | Aggregated analysis data (`getDirectorAnalysis`) |

Director generates reports on an interval (shown in UI); extra analysis can be triggered from **Settings**.

---

<a id="settings"></a>
## Settings

<img src="./assets/icons/settings.svg" width="22" height="22" alt="" /> Menu item **Settings**

**Purpose:** global platform settings.

| Section | Settings |
|---------|----------|
| **Demo replay** | Same embedded-video controls as **Live Monitor** → Demo replay (enable, title, URL or upload). Persisted with admin settings; secrets/adjacent config elsewhere unchanged. |
| **Theme** | Theme selection for storefront and admin; CSS variables |
| **AI Director & pipeline mode** | **Autonomous development** (timer-driven pipeline), interval in minutes, manual **Trigger Director**. **Local high-throughput mode** (powerful local host): raises pipeline parallelism; see **[pipeline-operations.md](pipeline-operations.md)** (“Local high-throughput preset”). The UI shows an **effective throughput** readout (config + env on this host) and **Refresh** without saving other fields. |
| **Git / Docker / registry** | Remote Git, Docker Registry (deploy artifacts) |
| **Auto-publish** | Static deploy after DevOps (Vercel / Netlify / Cloudflare Pages); CLI + env tokens — **[auto-publish.md](./auto-publish.md)** |
| **Railway (full_software)** | `general.railway_*` including optional **environment** and **service** UUIDs; **`RAILWAY_TOKEN`** in factory env; after DevOps, **`full_software`** specs write **`data/state/<product_id>/railway_deploy.json`** — pair with **[deploy-full-software-cloud.md](./deploy-full-software-cloud.md)** and **`scripts/railway_deploy_trigger.py`** / **`.github/workflows/railway-deploy.yml`** |
| **Site badge** | Optional “Built with AI-Factory” link injected into generated HTML |
| **Head snippet (generated sites)** | **`general.published_site_head_html`**: raw HTML/scripts inserted before `</head>` in each generated `*.html` when **Developer** completes (GA4 gtag, Yandex Metrica, site-verification `meta`, etc.). Empty = disabled. Does not rewrite already-built pages until the next Developer run (or manual file edit). |
| **Corporate Chat / standup** | Director standup schedule (time, timezone, on/off) — mirrors chat settings |
| **Telegram** | Bot token and chat ID can be set here or via **`TELEGRAM_BOT_TOKEN`** / **`TELEGRAM_CHAT_ID`** in env; values saved from admin are stored under **`data/secrets/telegram.yaml`** (not in committed `config.yaml`). |

Saving goes through `updateAdminSettings` / `updateChatSettings` (see `web/frontend/lib/api.ts`).

---

<a id="users-access"></a>
## Users & access

<img src="./assets/icons/shield.svg" width="22" height="22" alt="" /> Menu item **Users & access** (shown only for **`super_admin`**)

**Purpose:** manage human accounts that can sign in to this admin panel (username, password, enabled flag, **role**).

| Action | Description |
|--------|-------------|
| Refresh | Reload user list |
| Add user | Create account (password min 12 characters); choose **role** from dropdown |
| Role | Per-user `viewer`, `operator`, `admin`, or `super_admin` |
| Active / Disabled | Toggle `enabled` without deleting the row |
| Delete | Remove account |

**Roles** limit what each user can call on `/api/admin/*` (RBAC). Full matrix, file paths, and `GET /api/admin/users/roles/meta` are documented in **[admin-panel-rbac.md](./admin-panel-rbac.md)**.

---

<a id="corporate-chat"></a>
## Corporate Chat

<img src="./assets/icons/message-circle.svg" width="22" height="22" alt="" /> Menu item **Corporate Chat**

**Purpose:** persistent corporate channel: Owner, Director, and agent-role messages.

![Corporate Chat](./assets/screenshots/admin-corporate-chat.png)

| Feature | Description |
|---------|-------------|
| Feed | Chronological messages with role badges (**Owner**, **Director**, agent type) |
| Input | Text as Owner; Enter sends, Shift+Enter newline (if implemented) |
| Display name | **Owner** display name (`chat_username`) |
| **Run standup now** | Manual Director standup without waiting for schedule |
| Delete | Remove a message from the feed (API `delete`) |

Daily standup schedule is under **Settings** (time, `director_standup_timezone`). For differences vs Brainstorming see [corporate-chat-vs-discussions.md](./corporate-chat-vs-discussions.md).

---

<a id="brainstorming"></a>
## Brainstorming

<img src="./assets/icons/brain-circuit.svg" width="22" height="22" alt="" /> Menu item **Brainstorming**

**Purpose:** **Brainstorming & Discussions** — separate sessions with rounds, agent selection, and outputs (ideas, promote to pipeline).

![Brainstorming & Discussions](./assets/screenshots/admin-brainstorming.png)

An info banner explains this mode does **not** replace Corporate Chat (no daily standup or Owner/Director “office” channel).

| Action | Description |
|--------|-------------|
| New Session | Create session with topic and type |
| Session list | Status, participants, open details |
| Session messages | Rounds, agent replies, human can intervene |
| Promote idea | Move an idea into product/pipeline (when API supports it) |

---

<a id="discovery-queue"></a>
## Discovery Queue

<img src="./assets/icons/activity.svg" width="22" height="22" alt="" /> Menu item **Discovery**

**Purpose:** inspect ranked opportunities produced by the pre-pipeline Discovery layer and optionally enqueue the top candidate into the main pipeline.

![Discovery Queue](./assets/screenshots/admin-discovery.png)

| Action | Description |
|--------|-------------|
| Refresh | Reloads ranked ideas and source-health payload |
| Queue top idea | Triggers discovery run with product creation enabled |
| Ranked table | Shows idea, category, weighted score, confidence, and validation notes |
| Source health | Displays per-source runtime state (healthy/degraded, backoff/failure streak) |

API linkage:
- `GET /api/admin/discovery/ideas`
- `POST /api/admin/discovery/run`

---

<a id="batch-pipeline"></a>
## Batch pipeline operations

Bulk idea creation and retries are handled via Admin API and surfaced in tab workflows:

| Endpoint | Use |
|----------|-----|
| `POST /api/admin/products/create-batch` | Enqueue up to 10 ideas |
| `GET /api/admin/products/batch/{batch_id}` | Fetch batch progress/errors |
| `POST /api/admin/products/batch/{batch_id}/retry-failed` | Requeue failed items |

Use this path when running high-throughput GTM batches (for example, rapid landing campaign sets).

---

## Related docs

- [Documentation index](./README.md)
- [Corporate Chat vs Brainstorming](./corporate-chat-vs-discussions.md)
- [Root README](../README.md) — ports, environment variables, safety

---

## Verification log (2026-05-07)

- Browser smoke: login + tab navigation for Dashboard, Pipeline, Providers, LLM Logs, Corporate Chat, Brainstorming (Playwright capture flow) — passed.
- Screenshots: all currently embedded screenshot links are valid and resolve to files in `docs/assets/screenshots/`.
- Note: Discovery tab and new public growth pages are documented; dedicated PNG capture is tracked in `docs/assets/screenshots/MISSING.md`.
- Backend regression subset (container): async SQLite/state-machine/worker/rate-limit/director-timeout tests — passed (`5 passed`).
