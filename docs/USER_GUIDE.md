# AI-Factory User Guide (detailed)

> **Audience:** operators, product owners, and support using the **storefront** and **admin panel**.  
> **Русская версия (подробнее, те же скриншоты):** [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · **FAQ:** [FAQ.md](./FAQ.md) · [FAQ.ru.md](./FAQ.ru.md)

> **Screenshots** live in [`docs/assets/screenshots/`](./assets/screenshots/). If PNGs are missing in your clone, start the stack and run:
>
> ```bash
> cd web/frontend
> DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='your-admin-password' npm run capture-docs-screenshots
> ```

---

## Table of contents

1. [What you are looking at](#what-you-are-looking-at)
2. [Where to look — situation cheat sheet](#where-to-look--situation-cheat-sheet)
3. [Five ideas before you click anything](#five-ideas-before-you-click-anything)
4. [Your first 15 minutes](#your-first-15-minutes)
5. [Public storefront (no login)](#public-storefront-no-login)
6. [Public documentation `/docs`](#public-documentation-docs)
7. [Admin login and safety](#admin-login-and-safety)
8. [Admin navigation map](#admin-navigation-map)
9. [Dashboard](#dashboard)
10. [Live Monitor](#live-monitor)
11. [New Product — wizard & templates](#new-product--wizard--templates)
12. [Pipeline Monitor — source of truth](#pipeline-monitor--source-of-truth)
13. [Workshop](#workshop)
14. [Discovery](#discovery)
15. [LLM Providers & LLM Logs](#llm-providers--llm-logs)
16. [Settings](#settings)
17. [Scenario playbooks](#scenario-playbooks)
18. [Actionable errors in the UI](#actionable-errors-in-the-ui)
19. [Screenshots index](#screenshots-index)
20. [Related handbooks](#related-handbooks)

---

## What you are looking at

**AI-Factory** accepts a **plain-language idea** and runs a **fixed multi-agent pipeline** with quality gates, saving artifacts under `/app/data` (spec, architecture, code, marketing).

| Surface | URL | Role |
|---------|-----|------|
| Storefront | `/` | Buyers, demos |
| Product page | `/product/{id}` | One run’s public status |
| Admin | `/admin` | Operators |
| In-app docs | `/docs` | Same guides, embedded images |

---

## Where to look — situation cheat sheet

| Situation | Go here first | What to inspect | Screenshot |
|-----------|---------------|-----------------|------------|
| Site won’t load | Host health, `docker compose ps`, `:9081/api/health` | Container `app` healthy | — |
| Can’t log in | `/admin/login`, [security.md](./security.md) | Bootstrap password, not `admin123` | ![Login](./assets/screenshots/admin-login.png) |
| Created a product — where is it? | **Pipeline** | Search `prod-…`, sort *shipped first* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Pipeline shows “try N of 8” | **Pipeline** (wait; up to 5 min per attempt) | *Connection phase* = HTTP retries; then *X / total* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Product stuck on a stage | **Pipeline** → click stage tile | Task `running` / `failed`, errors | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| LLM / model errors | **LLM Providers** → **LLM Logs** | Keys, routing, timeouts | ![Providers](./assets/screenshots/admin-providers.png) |
| COMPLETED but not on storefront | **Pipeline** card | `storefront_gate_reasons` | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Fast landing only | **New product** → landing-only | `marketing_landing` | ![New product](./assets/screenshots/admin-new-product.png) |
| Compare two specs | **Workshop** diff | Two product ids | ![Workshop](./assets/screenshots/admin-workshop.png) |
| Autonomous ideas | **Discovery** | Ranked queue, auto-enqueue in Settings | ![Discovery](./assets/screenshots/admin-discovery.png) |
| Quick health snapshot | **Dashboard** | KPI, task counts | ![Dashboard](./assets/screenshots/admin-dashboard.png) |
| First-time setup / public URL | **Setup wizard** | Instance checklist | ![Setup](./assets/screenshots/admin-setup.png) |
| Live metrics / demo video | **Live Monitor** | SSE, demo replay | ![Live Monitor](./assets/screenshots/admin-live-monitor.png) |
| Session expired | **/admin/login** | 401 | ![Login](./assets/screenshots/admin-login.png) |
| Permission denied | [admin-panel-rbac.md](./admin-panel-rbac.md) | Your role | — |

More Q&A: **[FAQ.md](./FAQ.md)** · **[FAQ.ru.md](./FAQ.ru.md)**

---

## Five ideas before you click anything

1. **Product** = one pipeline row (`prod-xxxxxxxx`).
2. **State** = pipeline stage — not the same as storefront visibility.
3. **Delivery profile** = `full_software` | `marketing_landing` | `infer`.
4. **Sandbox** = preview under `/api/sandbox/…`.
5. **LLM Providers** must work or agents fail — UI links you there from error cards.

---

## Your first 15 minutes

1. Open `/` and `/docs`.
2. Sign in at `/admin/login` (see [security.md](./security.md) for password).
3. Dismiss the blue **Get oriented** card after reading it.
4. **New product** → template or custom idea → submit.
5. **Pipeline** → find your id → watch the stage strip.

---

## Public storefront (no login)

**Case — guest submits an idea**

1. Hero form on `/` (if enabled).
2. Receive `prod-…` and `/product/{id}`.
3. Operator finds the same id in **Pipeline**.

![Storefront home](./assets/screenshots/public-home.png)

**Case — buyer browses catalog**

Only products passing **marketplace gates** appear (may be fewer than Dashboard **Completed**).

---

## Public documentation `/docs`

Share `/docs` with stakeholders — includes quick start and the same screenshot set as this file.

![Public docs](./assets/screenshots/public-docs.png)

---

## Admin login and safety

1. `/admin/login` — user **`admin`**.
2. **No default `admin123`.** First install: console password or `data/secrets/bootstrap_admin.txt`.
3. Use **HTTPS** in production; rotate password day one.
4. Enable **2FA** when available.

![Admin login](./assets/screenshots/admin-login.png)

---

## Admin navigation map

![Sidebar](./assets/screenshots/admin-sidebar.png)

| Tab | Operator use |
|-----|----------------|
| Dashboard | Snapshot KPIs |
| Live Monitor | Streaming metrics, demo replay |
| Pipeline | All products, tasks, storefront hints |
| New product | Enqueue work |
| Workshop | Diffs, canvas, patterns |
| LLM Providers / LLM Logs | Models and debugging |
| Discovery | External signals → ideas |
| Settings | Factory-wide flags |
| Corporate Chat / Brainstorming | Discussions (not pipeline agents) |

Full tab reference: [admin-guide.md](./admin-guide.md).

---

## Dashboard

**When:** quick morning check, after deploy.

| Block | Meaning |
|-------|---------|
| Product KPIs | Scale of pipeline |
| Task pending/running | Worker backlog |
| Resources | Host CPU/RAM/disk |

**Note:** Dashboard **Completed** ≠ storefront listing count.

![Dashboard](./assets/screenshots/admin-dashboard.png)

---

## Live Monitor

**When:** demos, autonomous Director, live escalations.

![Live Monitor](./assets/screenshots/admin-live-monitor.png)

- SSE connection indicator.
- **Demo replay** video (configure in Settings) — see [pipeline-operations.md](./pipeline-operations.md).

**Setup wizard** (first install): ![Setup](./assets/screenshots/admin-setup.png) — public URL, LLM key, checks before autonomous mode.

---

## New Product — wizard & templates

Path: `/admin?tab=new-product`

![New product](./assets/screenshots/admin-new-product.png)

| Step | Tips |
|------|------|
| Idea | One clear sentence |
| Options | **Full product** vs **Marketing landing page only**; set copy language |
| Review | **Start building** — copy `prod-…` |

- **Cloud templates** — saved on server.
- **AI prefill** — requires **consent** checkbox.
- Failures show **Actionable failure** with **Retry** and links to Providers / Pipeline.

---

## Pipeline Monitor — source of truth

Path: `/admin?tab=pipeline`

![Pipeline](./assets/screenshots/admin-pipeline.png)

### Catalog loading (important)

1. **Cold start** (no `localStorage` snapshot for this sort): you may see *Fetching first catalog page…* and *Server request N / M*.
2. Each **N** is a real **HTTP attempt** (up to 8 on first page). Previous attempts failed or timed out — client retries with backoff.
3. **Per-attempt timeout:** up to **5 minutes** (`300_000` ms).
4. **Connection phase** progress bar ≈ retry index; **catalog %** appears in the header as **X / total** after rows return.
5. **Cache:** after success, a slim catalog is stored in **localStorage** (`aicom_pipeline_catalog_v2_*`) — next visit paints immediately, then refreshes in background.

### Card anatomy

| UI | Purpose |
|----|---------|
| Stage strip (Anl, Pm, Dev, Qa…) | Per-agent task status; **click** for task modal |
| Spec / Dev handoff | PM spec and developer handoff JSON |
| Filters | Sort, category, state, storefront, dates |
| Storefront / follow-up | Listing gates and manual labels |

### Filters worth knowing

- **Sort: shipped first** — completed work at the top.
- **Search** — id, title, description, follow-up text.

---

## Workshop

![Workshop](./assets/screenshots/admin-workshop.png)

Board, material diff (spec/arch), iteration canvas, pattern library, Web Push lab — see [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) for scenario detail.

---

## Discovery

![Discovery](./assets/screenshots/admin-discovery.png)

Ranked external ideas; auto-enqueue only when explicitly enabled ([configuration.md](./configuration.md)).

---

## LLM Providers & LLM Logs

![Providers](./assets/screenshots/admin-providers.png)

![LLM Logs](./assets/screenshots/admin-llm-logs.png)

First stop for any agent failure mentioning models, tokens, or timeouts.

---

## Settings

![Settings](./assets/screenshots/admin-settings.png)

Autonomous mode, demo replay, auto-publish, Railway, CORS — see [configuration.md](./configuration.md).

---

## Scenario playbooks

### 1 — First product end-to-end

Providers (keys) → New product → Pipeline watch stages → sandbox URL → check storefront gates if listing matters.

### 2 — Pipeline catalog slow or retrying

Check `/api/health` → wait for current attempt (up to 5 min) → DevTools Network on `pipeline/products?light=1` → increase proxy timeout if 502 → see [FAQ.md](./FAQ.md).

### 3 — Investor demo in five minutes

Pre-bake one green **Pipeline** card + sandbox; enable **demo replay** on Live Monitor; Dashboard KPIs.

### 4 — Product failed QA

Pipeline → failed **Qa** tile → task error → QA report under `data/bugs/{id}/` on server.

### 5 — Policy audit reopened old products

Products may show repair states while staying listed — [pipeline-operations.md](./pipeline-operations.md).

---

## Actionable errors in the UI

| Symptom | UI actions | Also check |
|---------|------------|------------|
| Network / timeout | Retry, Settings | Compose, proxy |
| 401 | Sign in again | JWT expiry |
| 403 | — | RBAC |
| LLM errors | Providers, LLM Logs | Keys |
| Partial catalog | Retry catalog | FAQ “try N of 8” |
| Prefill blocked | Consent checkbox | New product |

---

## Screenshots index

| File | Content |
|------|---------|
| `public-home.png` | Storefront `/` |
| `public-docs.png` | `/docs` |
| `admin-login.png` | Login |
| `admin-dashboard.png` | Dashboard |
| `admin-sidebar.png` | Full sidebar |
| `admin-setup.png` | Setup wizard |
| `admin-live-monitor.png` | Live Monitor |
| `admin-pipeline.png` | Pipeline Monitor |
| `admin-new-product.png` | New product wizard |
| `admin-workshop.png` | Workshop |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery |
| `admin-settings.png` | Settings |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |

Refresh: `cd web/frontend && npm run capture-docs-screenshots` — details in [assets/screenshots/README.md](./assets/screenshots/README.md).

---

## Related handbooks

| Document | When |
|----------|------|
| [FAQ.md](./FAQ.md) / [FAQ.ru.md](./FAQ.ru.md) | Frequent questions |
| [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) | Full Russian walkthrough |
| [owner-guide.md](./owner-guide.md) | Production owner |
| [admin-guide.md](./admin-guide.md) | Every admin tab |
| [admin-panel-rbac.md](./admin-panel-rbac.md) | Roles |
| [pipeline-operations.md](./pipeline-operations.md) | Worker behavior |
| [configuration.md](./configuration.md) | Environment variables |

---

*AI-Factory v2.1 — detailed user guide with situational index and FAQ links. Regenerate screenshots after major UI changes.*
