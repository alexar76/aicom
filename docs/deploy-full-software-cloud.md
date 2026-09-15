# Deploying full_software products to the cloud

Static auto-publish (Vercel / Netlify / Cloudflare Pages) fits **marketing landings**. **`full_software`** stacks need a **database**, **long-lived backend**, and **secrets** — plan explicitly.

## Recommended first integration (Docker-first)

**Railway**, **Fly.io**, **Render**, or **Google Cloud Run** + managed Postgres (Neon, Supabase, RDS, Aiven) are typical fits.

### Outline

1. **Database** — provision Postgres (or use SQLite only for tiny demos). Capture `DATABASE_URL`.
2. **Backend image** — build from generated `Dockerfile` / compose service `api`.
3. **Migrations** — run Alembic/Prisma migrate as a **release command** or container entrypoint **before** accepting traffic.
4. **Frontend** — build static assets to CDN or serve SSR behind the same hostname with `/api` routed to the backend.
5. **Env** — inject `DATABASE_URL`, `JWT_SECRET`, `SANDBOX_DEMO_*` if using prefilled demo login, CORS origins.

### Railway (example sketch)

- Create project → **deploy from GitHub** or **Dockerfile** path `backend/Dockerfile`.
- Add **Postgres** plugin → Railway injects `DATABASE_URL`.
- Set **start command** e.g. `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Frontend: second service or static hosting with `VITE_API_URL` pointing to Railway URL.

CI can call Railway’s **[GraphQL API](https://docs.railway.app/guides/public-api)** (`https://backboard.railway.com/graphql/v2`) — keep tokens in **secrets**, not in generated repos.

### GitHub Actions redeploy (this repo)

1. Add repo secrets: **`RAILWAY_TOKEN`**, **`RAILWAY_SERVICE_ID`**, **`RAILWAY_ENVIRONMENT_ID`** (UUIDs from the Railway dashboard — Ctrl/Cmd+K → copy IDs).
2. Run workflow **Railway deploy** (`.github/workflows/railway-deploy.yml`) via **Actions → Railway deploy → Run workflow**.
3. Optional input **`product_id`** — if you commit **`data/state/<product_id>/railway_deploy.json`** from the factory, the script reads **`railway_service_id`** (and **`railway_environment_id`** if present) from that file.

Local / other CI:

```bash
RAILWAY_TOKEN=... RAILWAY_SERVICE_ID=... RAILWAY_ENVIRONMENT_ID=... \
  python scripts/railway_deploy_trigger.py
# or: python scripts/railway_deploy_trigger.py --product-id prod-xxxx
```

The script calls GraphQL **`serviceInstanceRedeploy`**. For **project tokens**, use header **`Project-Access-Token`** instead of `Authorization: Bearer` — see Railway docs.

## Factory-side hook (Admin → Settings)

1. In **Admin → Settings**, open **Railway (full_software)**.
2. Set **Railway project ID** (and optional environment / service ID) — these are stored in `config.yaml` under `general.railway_*` (not secrets).
3. Set **`RAILWAY_TOKEN`** in the factory environment (`.env` or container secrets). The UI shows whether it is configured.
4. Enable **Record Railway deploy intent after DevOps**. When DevOps succeeds and `data/specs/<product_id>/specification.json` has `"delivery_profile": "full_software"`, the worker writes **`data/state/<product_id>/railway_deploy.json`** with project metadata and a timestamp. Pair that file with your **CI step** (GitHub Action calling Railway’s API, or deploy-on-push from Git).

The factory does not push to Railway by itself; use **`scripts/railway_deploy_trigger.py`** or the **Railway deploy** GitHub Action. DevOps agent instructions still expect **migration + OpenAPI** artifacts so deploys stay deterministic.

### Config keys (`config.yaml` → `general`)

| Key | Purpose |
|-----|--------|
| `railway_deploy_enabled` | Master switch for the post-DevOps hook. |
| `railway_project_id` | Railway project UUID (display / metadata for CI). |
| `railway_environment` | e.g. `production` (optional display name). |
| `railway_environment_id` | Environment UUID for **`serviceInstanceRedeploy`** (optional; can also use CI secret). |
| `railway_service_id` | Service UUID (optional; also written to `railway_deploy.json`). |

Secret: **`RAILWAY_TOKEN`** only in the factory process environment (see **`.env.example`**), never in YAML.

**Artifact written:** `data/state/<product_id>/railway_deploy.json` (JSON with product id, ids above, `requested_at`, and a short note). Pair with your own GitHub Action or Railway Git deploy.
