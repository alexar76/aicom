# FAQ — AI-Factory (detailed)

> Illustrated guide: [USER_GUIDE.md](./USER_GUIDE.md) · **Русский:** [FAQ.ru.md](./FAQ.ru.md) · [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · **Español:** [FAQ.es.md](./FAQ.es.md) · [USER_GUIDE.es.md](./USER_GUIDE.es.md)

---

## General

**What is AI-Factory?**  
A self-hosted system that runs a **fixed multi-agent pipeline** from a plain-language idea to specs, code, QA gates, and optional storefront listing.

**Storefront vs Admin?**  
Storefront (`/`) shows **filtered** marketplace-ready products. **Admin → Pipeline** is the **source of truth** for every `prod-…` row, tasks, and errors.

**Where is the “real” product state?**  
**Pipeline Monitor** (`/admin?tab=pipeline`). Dashboard is a snapshot on load; Live Monitor is streaming metrics.

---

## Access & install

**Default admin password?**  
There is **no** shipped default. First boot: console prompt or `data/secrets/bootstrap_admin.txt`. See [security.md](./security.md).

**Public demo ([magic-ai-factory.com](https://magic-ai-factory.com))?**  
**Passwordless:** username `admin`, click **Enter admin demo** (no password field). `AIFACTORY_DEMO_READONLY=1` still blocks destructive admin ops. See [security.md § Public demo](./security.md#public-demo-mode-aifactory_demo_readonly1).

**Cannot log in?**  
Check username `admin`, bootstrap password file, JWT clock skew, HTTPS/cookies, and that you use the correct host/port (often UI **9080**, API **9081**).

**Roles (viewer / operator / admin / super_admin)?**  
[admin-panel-rbac.md](./admin-panel-rbac.md).

---

## New product & queue

**How long does a full run take?**  
Typically **minutes to hours** for `full_software`; **marketing_landing** is faster.

**full_software vs marketing_landing?**  
Full stack (API/DB/CRUD) vs brochure-style landing; different stage depth and deploy paths.

**Where is my product id?**  
Wizard success screen, **Pipeline** search, or `/product/{id}` when public.

---

## Pipeline Monitor

**Why “try 4 of 8” / “Server request 4 / 8”?**  
That is the **fourth HTTP attempt** for the same catalog request — previous attempts failed or timed out. The client retries with backoff (`pipelineCatalogFetch.ts`). It does **not** mean the browser cannot reach the API.

**How long per attempt?**  
Up to **5 minutes** per request (`clientTimeoutMs` = 300_000). Backoff between attempts (first page cap ~8s).

**Progress bar not moving?**  
During **Connection phase**, the bar reflects **retry index**, not catalog rows. After rows arrive, use header **X / total** and the green hydration bar.

**Where is the Pipeline Monitor cache?**  
Browser **localStorage**: `aicom_pipeline_catalog_v2_{sort}` plus a 2-row peek. Cold start (new sort, cleared storage) shows retries again.

**Where is the public storefront catalog cache?**  
Home **`#products`**: `aicom_storefront_catalog_v1_{category}` (`all` or taxonomy slug). Cache-first paint, then background `GET /api/products` + categories. See [marketing.md](./marketing.md#homepage-catalog-products).

**Why is my product in “Full products” on `/` but I wanted a landing?**  
Storefront sections use API `delivery_profile`. Only exact **`marketing_landing`** goes to the landing grid; aliases like `landing` are normalized server-side — set profile explicitly in **New product** or spec. Seeded demos PulseDeck/Harborline are landings by design.

**COMPLETED but not on storefront?**  
Read `storefront_gate_reasons` on the Pipeline card — quality gates, missing code, manual hide, etc.

**Stuck product?**  
Pipeline stage strip → click failed/running tile → task modal; **LLM Logs**; worker logs under `data/logs/`.

---

## LLM

**All agents fail with LLM errors?**  
**LLM Providers** (keys, routing) → **LLM Logs** → `data/config/model_providers.yaml` on the data volume.

---

## Storefront & discovery

**Fewer products on `/` than Dashboard Completed?**  
Storefront applies **extra eligibility filters**.

**Product stuck at `HUMAN_REVIEW_PENDING` with no new tasks?**  
Expected for **`full_software`** after DevOps: **post-DevOps human gate** blocks Sales until an operator **Approves** or **Rejects** on the Pipeline card (`HumanReviewGatePanel`). Landings skip this gate. Env: `AIFACTORY_POST_DEVOPS_HUMAN_GATE`, `AIFACTORY_HUMAN_REVIEW_REQUIRED` — see [configuration.md](./configuration.md#pipeline-and-storefront-policy).

**Discovery auto-ideas?**  
Only if autonomous mode and `AIFACTORY_DISCOVERY_AUTO_ENQUEUE` (or equivalent Settings) are enabled.

---

## Data

**Where is data stored?**  
Host bind mount `./data` (or `~/aicom-data`) — never rely on anonymous Docker volumes for production.

**Lost data after container recreate?**  
Often wrong volume type — see README bind-mount section.

---

## Performance

**Slow catalog API?**  
Use `light=true` (default in UI). Ensure SQLite pagination optimizations are deployed. Check reverse-proxy timeouts.

---

## Screenshots

**Broken images in docs?**  
Run from `web/frontend`:

```bash
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

See [assets/screenshots/README.md](./assets/screenshots/README.md).

---

## Escalation

| Role | Doc |
|------|-----|
| Operator | [USER_GUIDE.md](./USER_GUIDE.md), [FAQ.ru.md](./FAQ.ru.md) |
| Owner | [owner-guide.md](./owner-guide.md) |
| Config | [configuration.md](./configuration.md) |
| Security | [SECURITY.md](../SECURITY.md) |

---

*Extend this file when the same question appears twice in support.*
