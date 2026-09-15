# FAQ — AI-Factory (detailed)

> Illustrated guide: [USER_GUIDE.md](./USER_GUIDE.md) · **Русский:** [FAQ.ru.md](./FAQ.ru.md) · [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · **Español:** [FAQ.es.md](./FAQ.es.md) · [USER_GUIDE.es.md](./USER_GUIDE.es.md) · **Français:** [FAQ.fr.md](./FAQ.fr.md) · **中文:** [FAQ.zh.md](./FAQ.zh.md)

---

## General

### What is AI-Factory in one sentence?

A system that takes a plain-text idea, runs it through a **chain of AI agents** (research → spec → code → QA → …), and saves artifacts to disk, with an admin panel and an optional public storefront.

### What's the difference between the storefront and the admin panel?

| | Storefront `/` | Admin `/admin` |
|---|------------|------------------|
| Login | Usually not required | JWT, username `admin` |
| Purpose | Show finished products, lead forms | Manage the pipeline |
| Source of truth | Filtered API catalog | **Pipeline** — full `prod-…` list |

### Where is the "real" product data?

**Admin → Pipeline** — the full catalog with tasks and errors. Dashboard is only a snapshot at load time. Live Monitor is a stream of metrics.

### Does the operator need a git clone?

No. The URL of the deployed instance and the admin password are enough. Documentation is also served at `/docs`.

---

## Access & install

### What is the default admin password?

**There is no fixed password.** On a first, empty `data/` the password is set in the entrypoint console or written to `data/secrets/bootstrap_admin.txt`. Details: [security.md](./security.md).

### Public demo (magic-ai-factory.com)?

**Passwordless:** username `admin`, click **Enter admin demo** (the password field is hidden). `AIFACTORY_DEMO_READONLY=1` blocks destructive operations in the admin panel. See [security.md § Public demo](./security.md#public-demo-mode-aifactory_demo_readonly1).

### Can't log in — what should I check?

1. Username is exactly **`admin`** (if you haven't created other users).
2. The bootstrap file / password set on the first `up`.
3. Server clock (JWT).
4. HTTPS vs HTTP and the `Secure` cookie.
5. Don't mix up ports: UI is often **9080**, API **9081** with the default Compose setup.

### What are the viewer / operator / admin / super_admin roles?

See [admin-panel-rbac.md](./admin-panel-rbac.md). **Operator** can run the pipeline, but cannot always change Settings and providers.

---

## New product & queue

### How long does a full run take?

From **a few minutes** to **hours** — it depends on `full_software`, LLM load, QA with Playwright, and the number of repair cycles. A landing is usually faster.

**Measured first `full_software` → `COMPLETED` (Aug 2026):** PulseBoard Mini `prod-a25224bcb746` — **~91 min** wall-clock, **~$0.18** LLM (`$0.181` in `pipeline_product_cost.json`). That product later returned to `DEV_FIXING` after a QA reopen; storefront currently shows **3** `COMPLETED` landings, not a lasting eligible `full_software`. Details: [README FAQ](../README.md#faq--scope).

### Product in HUMAN_REVIEW_PENDING, no tasks?

For **`full_software`** there is a **manual gate** after DevOps: you need to **Approve** or **Reject** on the Pipeline card (`HumanReviewGatePanel`). Landings (`marketing_landing`) skip this step. See [admin-guide.md](./admin-guide.md#post-devops-human-review) (EN).

### What's the difference between full_software and marketing_landing?

| | full_software | marketing_landing |
|---|---------------|-------------------|
| Result | API, DB, many pages | Static/simple site |
| Stages | Full chain | Shortened path |
| Deploy | Railway / compose | Vercel/Netlify static |

### Where do I find the product id after creating it?

The success screen in the wizard, **Pipeline** (search by name), or the URL `/product/{id}` if it's already published.

### Can I cancel a product in the queue?

It depends on the state and the worker policy. See admin-guide and the API. Often it's simpler to leave it `FAILED` / not pursuing than to physically delete it.

---

## Pipeline Monitor

### Why does it say "try 4 of 8" / "Server request 4 / 8"?

That's the **fourth attempt of the same HTTP request** to `/api/admin/pipeline/products`. The previous ones ended in an error, a timeout, or a 502. The client **deliberately** retries with backoff (see `pipelineCatalogFetch.ts`). It does **not** mean "the browser can't reach the API".

### How long should one attempt take?

Up to **5 minutes** (`clientTimeoutMs` 300 000 ms) per attempt. Between attempts there's a pause of up to ~8s on the first page.

### Why does the progress bar "not move"?

- During the **Connection phase** the bar shows the **HTTP attempt number**, not the % of the catalog.
- Once rows appear, look at the header: **X / total** and the green bar — that's the **real** progress of page hydration.

### Where is the catalog cache?

**Pipeline Monitor:** in **localStorage** — `aicom_pipeline_catalog_v2_{sort}` plus a 2-row peek. First visit / a different sort / cleared storage → a "cold" start with retries.

**Public storefront (`/`):** `aicom_storefront_catalog_v1_{category}` — cache first, then a background `GET /api/products`. See [marketing.md](./marketing.md).

### Why "All Categories (0)" first, then numbers appear?

Categories are counted from **already loaded** rows; while the catalog is still hydrating, the counters can be incomplete (the `+` suffix on options).

### Product COMPLETED but not on the storefront — why?

Typical reasons in `storefront_gate_reasons`:

- no code on disk;
- didn't pass **marketplace quality**;
- manually hidden (**hidden from storefront**);
- state is not yet in the shipped family.

Check the card in **Pipeline** and [pipeline-operations.md](./pipeline-operations.md).

### How do I find a "stuck" product?

1. Pipeline → filter state **running** / watch for orange stages.
2. Click a stage → a task `running` for a long time without `ended_at`.
3. Live Monitor / LLM Logs.
4. Worker logs: `data/logs/`.

### What does "Updating from server… 2 / 10" mean?

2 catalog rows out of 10 on the server have loaded; the rest are pulled in the background in chunks of 12.

---

## LLM & providers

### Agents are silent / everything FAILED with LLM

1. **LLM Providers** — keys, enabled, model id.
2. **LLM Logs** — the latest errors.
3. `data/config/model_providers.yaml` on the volume (not in git).
4. The provider's rate limits.

### Does the container need internet access?

Yes, for cloud APIs. Ollama on the host — the `docker-compose.host-gateway.yml` overlay.

### What is a heavy / light model?

Routing in Providers: heavy tasks (architect) vs light ones. See admin-guide.

---

## Storefront & buyers

### Why are there fewer products on the home page than Completed in the Dashboard?

The storefront applies **extra filters** (quality, code, hiding). The Dashboard counts every `COMPLETED` in the pipeline.

### Support / Lumen — is that a pipeline agent?

**No.** It's an assistant for marketplace buyers, separate from the **AI Agents** roster.

---

## Discovery & Director

### Ideas appeared on their own — is that normal?

Yes, if **autonomous pipeline** and **discovery auto-enqueue** are enabled. Otherwise ideas come only manually or via the Discovery API.

### How do I turn off auto-enqueueing of ideas?

`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`, `general.auto_pipeline: false` in Settings — see [configuration.md](./configuration.md).

---

## Sandbox & preview

### Sandbox won't open in the iframe

1. `AIFACTORY_SANDBOX_PREVIEW_API`, compose preview.
2. The Docker socket in the app container.
3. CSP / mixed content — HTTPS.
4. Sandbox logs in the API.

### How is sandbox different from auto-publish?

**Sandbox** is a preview on the factory. **Auto-publish** is the static export to Vercel/Netlify after DevOps.

---

## Data & backups

### Where do the products live?

The bind mount **`./data`** (or `~/aicom-data`) — `data/code/`, `data/specs/`, `data/state/pipeline.db`, and configs.

### Data disappeared after docker run

A common mistake: a **named volume** instead of a bind mount. See the README — the section on migrating from a named volume.

### Can I delete all demo products?

`./scripts/run_factory_demo_reset.sh` or `wipe_pipeline_products.py` — careful, it's irreversible.

---

## Performance & CI

### The catalog API is slow

After optimizations the light mode should respond in **seconds** for a small `limit`. If it's minutes again — check the size of `pipeline.db`, the proxy timeout, and don't load `light=0` without need.

### GitHub Actions fails on tests

See `.github/workflows/ci.yml` — pytest + Playwright jobs. Locally: `pytest -q` in the venv.

---

## Security

### Can I show the git remote on a stream?

**No**, if the URL contains a token. See the README — Screen recordings & Git remotes.

### Where is the JWT stored?

The browser's `localStorage` + an httpOnly cookie (see security.md). Not on public machines.

---

## Documentation & screenshots

### How do I update the screenshots in the guide?

```bash
cd web/frontend
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

File list: [assets/screenshots/README.md](./assets/screenshots/README.md).

### Images in markdown are broken in a git clone

The PNGs aren't committed or haven't been captured yet — run the script above against a running instance.

---

## Escalation

| Level | Doc |
|---------|----------|
| UI operator | [USER_GUIDE.md](./USER_GUIDE.md), this FAQ · RU: [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · ES: [USER_GUIDE.es.md](./USER_GUIDE.es.md) |
| Instance owner | [owner-guide.md](./owner-guide.md) |
| DevOps / env | [configuration.md](./configuration.md), [production-domain.md](./production-domain.md) |
| API integration | [api-integration-guide.md](./api-integration-guide.md) |
| Vulnerabilities | [SECURITY.md](../SECURITY.md) |

---

*Extend this FAQ when questions recur in support.*
