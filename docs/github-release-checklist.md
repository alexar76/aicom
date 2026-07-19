# GitHub release checklist

Use before tagging a public release or opening the repo to external contributors.

## Secrets & credentials

- [ ] **`data/config/model_providers.yaml`** is **gitignored** — never commit API keys. Ship **`data/config/model_providers.example.yaml`** only; operators copy to `model_providers.yaml` locally or in the bind-mounted `./data` volume.
- [ ] No secrets in committed `.env` (`.env` is gitignored). Compare your env against **`.env.example`**.
- [ ] `git grep -iE 'sk-[a-zA-Z0-9]{20,}|password\s*=\s*[\"'][^\"']{8,}' -- ':!*.lock' ':!package-lock.json'` returns nothing sensitive.

## Default factory mode

- [ ] **`config.yaml`** has `general.auto_pipeline: false` (ideas-only / on-demand). Autonomous mode is opt-in via Admin → Settings or `AIFACTORY_AUTONOMOUS_PIPELINE=1` on first container run.
- [ ] **Discovery** does not auto-enqueue ranked ideas unless you want it: Docker Compose defaults **`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`**; set `1` only when Director should enqueue from Discovery without manual approval.

## CI

- [ ] **`.github/workflows/ci.yml`** passes on `main` (pytest, frontend build, Playwright jobs as applicable).
- [ ] Optional: run **`pytest -q`** and **`cd web/frontend && npm ci && npm run build`** locally before push.

## Docs match behavior

- [ ] **Auto-publish** (Vercel / Netlify / Cloudflare) is for **static / marketing** outputs after DevOps — see [auto-publish.md](auto-publish.md).
- [ ] **`full_software`** (API + DB) cloud deploy uses **Railway-style hooks + your CI token**, not Vercel static hosting — see [deploy-full-software-cloud.md](deploy-full-software-cloud.md).
- [ ] CLI `wallet balance` is a **demo table** (documented in [cli-reference.md](cli-reference.md)); not live chain balances.

## Clean demo data (optional)

From repo root with Docker:

```bash
./scripts/run_factory_demo_reset.sh
```

Or manually: `python scripts/wipe_pipeline_products.py --help` (see `--zero-dashboard`).

## Deploy secrets (you add in GitHub / host env)

| Goal | Typical secrets / config |
|------|---------------------------|
| Static site after DevOps | `VERCEL_TOKEN` and/or `NETLIFY_AUTH_TOKEN` and/or `CLOUDFLARE_API_TOKEN` (+ provider CLI on worker `PATH`) |
| Railway redeploy from CI | `RAILWAY_TOKEN`, `RAILWAY_SERVICE_ID`, `RAILWAY_ENVIRONMENT_ID` (see `.github/workflows/railway-deploy.yml`) |
| LLM calls | Provider keys in env or `model_providers.yaml` |

The factory **does not** push to cloud hosts by itself for full stacks; it writes intent files (`railway_deploy.json`, `auto_publish.json`) for **your** pipeline with the tokens above.
