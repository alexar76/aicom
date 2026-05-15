# AI-Factory User Guide (“for dummies”)

> **Audience:** operators, product owners, and support staff who use the **storefront** and **admin panel** day to day.  
> **Not covered here:** low-level Python agent code — see `docs/agents.md` and `docs/architecture-orchestrator.md`.

> **Русскоязычным читателям:** этот гид написан по-английски, чтобы совпадать с подписями в UI и с остальной документацией репозитория. Структура ниже — оглавление; технические имена вкладок и URL оставлены как в продукте.

---

## Table of contents

1. [What you are looking at](#what-you-are-looking-at)
2. [Five ideas before you click anything](#five-ideas-before-you-click-anything)
3. [Your first 10 minutes](#your-first-10-minutes)
4. [Public storefront (no login)](#public-storefront-no-login)
5. [Public documentation site `/docs`](#public-documentation-site-docs)
6. [Admin login and safety](#admin-login-and-safety)
7. [After login: onboarding strip](#after-login-onboarding-strip)
8. [New Product — guided wizard & templates](#new-product--guided-wizard--templates)
9. [Workshop — board, diffs, canvas, patterns, Web Push](#workshop--board-diffs-canvas-patterns-web-push)
10. [Pipeline — where truth lives](#pipeline--where-truth-lives)
11. [LLM Providers & LLM Logs](#llm-providers--llm-logs)
12. [Settings](#settings)
13. [When something breaks (actionable errors)](#when-something-breaks-actionable-errors)
14. [Iteration Hub API (for power users)](#iteration-hub-api-for-power-users)
15. [Screenshots reference](#screenshots-reference)
16. [Related handbooks](#related-handbooks)

---

## What you are looking at

**AI-Factory** is a single packaged “factory” that:

- Accepts a **plain-language idea** (from a guest on the storefront, from you in **Admin → New product**, or from automation).
- Runs a **fixed multi-agent pipeline** (analyst → PM → architect → developer → QA → …) with quality gates.
- Produces **artifacts on disk** (spec, architecture, code, marketing copy) and optional **sandbox previews**.

You interact through:

| Surface | URL | Typical role |
|--------|-----|----------------|
| Storefront | `/` | Buyers, demos, marketing |
| Product detail | `/product/{id}` | Status + links for one run |
| Admin | `/admin` | Factory operators |
| In-app docs | `/docs` | Same content as this guide, lighter |

---

## Five ideas before you click anything

1. **Product** = one pipeline row with an `id` like `prod-xxxxxxxx`. Everything hangs off that id.
2. **State** = where the pipeline is (e.g. idea received → shipped). Not the same as “visible on storefront”.
3. **Delivery profile** = `full_software` (full build) vs `marketing_landing` (landing-only fast path) vs `infer` (legacy auto pick).
4. **Sandbox** = optional live preview of generated static or API-backed demo under `/api/sandbox/...`.
5. **LLM Providers** must be configured or agents will fail — the UI now surfaces **actionable error cards** with links to Providers / Settings.

---

## Your first 10 minutes

1. Open the **storefront** `/` and read the hero — that is the default public story.
2. Open **`/docs`** in the same deployment — it mirrors marketing + deep links.
3. Sign in to **`/admin/login`** with your admin password (rotate on day one).
4. If you see the **blue onboarding card** at the top of Admin, read it once, then dismiss — you can always read this file.
5. Open **New product**, use a **Quick-start template** chip or type your own idea, walk **Idea → Options → Review**, submit.
6. Open **Pipeline**, find your `prod-…`, expand the card, watch states change when the worker runs.

---

## Public storefront (no login)

**Try this:** describe a short product in the guest flow (if enabled on your skin). You receive a product id and a public URL.

**Screenshot (homepage):**

![Storefront home](./assets/screenshots/public-home.png)

---

## Public documentation site `/docs`

Next.js route **`/docs`** is the in-app documentation hub (icons, quick start, admin screenshots). It is safe to share with stakeholders who do not have git access.

**Screenshot:**

![Public documentation](./assets/screenshots/public-docs.png)

---

## Admin login and safety

1. Use **`/admin/login`** — username **`admin`**.
2. **First install:** password is **not** `admin123`. With a terminal attached (`./run.sh` or `docker compose run -it app`), the entrypoint **asks for a password** in the console. Headless `docker compose up -d` writes a one-time password to **`data/secrets/bootstrap_admin.txt`**. Details: **[security.md](./security.md)**.
3. Prefer **HTTPS** in production; JWT is stored in browser storage — treat workstations as sensitive.
4. Enable **2FA** from auth settings when available.
5. After login, rotate passwords and remove demo banners if shown.

**Screenshot:**

![Admin login](./assets/screenshots/admin-login.png)

---

## After login: onboarding strip

A dismissible card may appear at the top of Admin summarizing:

- Dashboard for health
- New product for queueing work
- Providers + Settings for model routing

**Screenshot (dashboard context):**

![Admin dashboard](./assets/screenshots/admin-dashboard.png)

**Full navigation column:**

![Admin sidebar full height](./assets/screenshots/admin-sidebar.png)

---

## New Product — guided wizard & templates

**Path:** Admin → **New product** (`/admin?tab=new-product`).

What changed (UX):

- **Progress bar** + step chips (Idea → Options → Review).
- **Left column (desktop):** per-step checklist + **Quick-start templates** (three curated presets that fill idea + options).
- **First-visit intro** (dismissible) explains templates and error recovery.
- **Cloud templates** — saved on the server under the factory data directory (same storage as the deployment), listed separately from **local browser** templates.
- **AI prefill** — optional; requires explicit **consent checkbox** before any LLM call.
- **Create product** uses authenticated API (Bearer token) — failures show a red **Actionable failure** panel with **Retry** and deep links (Providers, Pipeline, Settings).

**Screenshot:**

![New product wizard](./assets/screenshots/admin-new-product.png)

### Example walkthrough (copy/paste style)

1. **Step 1 — Idea:**  
   `A waitlisted B2B tool for freelancers to send scoped proposals with e-sign.`  
   Click **Next**.
2. **Step 2 — Options:**  
   Choose **Full product**, **prototype**, set **Landing & UI copy language** (e.g. **Auto** or **Russian** for a Russian brief), add instructions `TypeScript + Postgres; no PCI scope.`  
   Click **Save current to cloud** if you want this preset on another browser.
3. **Step 3 — Review:** confirm counts, click **Start building**.  
4. **Pipeline:** open from the success links; search for the new `prod-…`.

---

## Workshop — board, diffs, canvas, patterns, Web Push

**Path:** Admin → **Workshop** (`/admin?tab=workshop`).

Capabilities:

- **Board** — recent products by pipeline state; **Use ID** copies id into canvas / lab fields.
- **Material diff** — side-by-side JSON for **specification** or **architecture** files for two product ids.
- **Iteration canvas** — lightweight graph (nodes/edges) stored per product via **Iteration Hub** API; branch color + merge edges.
- **Multi-device lab** — three iframes refresh the same sandbox viewer URL on a timer (simulated co-viewing; not WebRTC).
- **Cloud pattern library** — JSON documents stored server-side for reusable workshop snippets.
- **Web Push** — subscribe in-browser; test push; optional broadcast after Telegram notify (if configured).

Dismissible **Workshop tips** card explains the flow.

**Screenshot:**

![Workshop tab](./assets/screenshots/admin-workshop.png)

---

## Pipeline — where truth lives

**Path:** Admin → **Pipeline**.

Use this tab to:

- Filter and search `prod-…` ids.
- Inspect **state**, **errors**, and **stage** details.
- Control storefront visibility where policy allows (see `docs/admin-guide.md` and `docs/owner-guide.md`).

**Screenshot:**

![Pipeline](./assets/screenshots/admin-pipeline.png)

---

## LLM Providers & LLM Logs

**Providers** — API keys, routing rules, health.

**Screenshot:**

![LLM Providers](./assets/screenshots/admin-providers.png)

**LLM Logs** — recent model calls for debugging “why did the agent stop?”.

**Screenshot:**

![LLM Logs](./assets/screenshots/admin-llm-logs.png)

---

## Settings

**Path:** Admin → **Settings**.

Factory-wide options: theme, integrations, Director, demo replay, etc. Exact flags evolve — see `docs/configuration.md`.

**Screenshot:**

![Settings](./assets/screenshots/admin-settings.png)

---

## When something breaks (actionable errors)

Symptoms map to **what you should do** (the UI encodes this in red panels + buttons):

| Symptom | Typical cause | UI action |
|--------|----------------|-----------|
| “Could not reach the server”, timeout | Network / container down | Retry; open **Settings**; check reverse proxy |
| HTTP 401 | Session expired | **Sign in again** link |
| HTTP 403 | RBAC | Ask `super_admin` for role change (`docs/admin-panel-rbac.md`) |
| HTTP 404 on spec/architecture | Artifact not generated yet | Pick another product or wait for pipeline stage |
| LLM / provider / model errors | Keys or routing | **Open LLM Providers** + **LLM Logs** |
| Web Push / VAPID | Missing dependency or keys | Check server logs; `pywebpush` in requirements; env `AIFACTORY_VAPID_CONTACT` |
| AI prefill “consent” | Checkbox | Enable consent before running LLM |

---

## Iteration Hub API (for power users)

Authenticated admin routes under **`/api/admin/iteration-hub`**:

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST/DELETE | `/user-templates` | Cloud product-creation templates |
| GET/PUT | `/products/{id}/iteration-canvas` | Persisted workshop canvas JSON |
| GET/POST/DELETE | `/patterns` | Cloud pattern library |
| POST | `/prefill-from-idea` | LLM assist (`consent: true` required) |
| GET/POST | `/web-push/*` | VAPID public key, subscribe, test send |

Full technical narrative: `docs/admin-guide.md` (update if you add tabs).

---

## Screenshots reference

All files live in **`docs/assets/screenshots/`** and are copied to **`web/frontend/public/docs-screenshots/`** for `/docs`.

| File | Description |
|------|-------------|
| `public-home.png` | Storefront `/` |
| `public-docs.png` | Documentation `/docs` |
| `admin-login.png` | Login form |
| `admin-dashboard.png` | Dashboard |
| `admin-sidebar.png` | Full-height sidebar |
| `admin-pipeline.png` | Pipeline |
| `admin-new-product.png` | New product wizard |
| `admin-workshop.png` | Workshop |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery |
| `admin-settings.png` | Settings |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |

**Refresh command** (app must be reachable):

```bash
cd web/frontend
npm run capture-docs-screenshots
```

Environment variables: `DOCS_SCREENSHOT_BASE_URL`, `ADMIN_PASSWORD` (see `docs/assets/screenshots/README.md`).

---

## Related handbooks

| Document | When to read |
|----------|----------------|
| [owner-guide.md](./owner-guide.md) | You operate a live deployment (Mermaid, pitfalls) |
| [admin-guide.md](./admin-guide.md) | Every admin tab, API touchpoints |
| [api-integration-guide.md](./api-integration-guide.md) | REST integration |
| [admin-panel-rbac.md](./admin-panel-rbac.md) | Roles: viewer / operator / admin / super_admin |
| [README.md](./README.md) | Doc index |

---

*Document version: aligned with AI-Factory v2.1 admin UX (onboarding, actionable errors, New product wizard, Workshop, Iteration Hub). Regenerate screenshots after major UI changes.*
