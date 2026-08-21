# Auto-publish (Vercel / Netlify / Cloudflare Pages)

After the **DevOps** stage completes successfully, the pipeline worker can deploy `data/code/<product_id>/` to a static host so every build gets a **shareable HTTPS URL**.

> **Not for full API + database stacks:** marketing landings and static frontends only. For **`delivery_profile: full_software`** (Postgres, auth, long-running API), use **[deploy-full-software-cloud.md](deploy-full-software-cloud.md)** (Railway-style hook and CI).

## Admin → Settings

- **Enable auto-publish** — master switch  
- **Provider** — `none` | `vercel` | `netlify` | `cloudflare_pages`  
- **Netlify site ID** — optional; pin deploys to an existing site  
- **Cloudflare Pages project name** — optional; default `aifactory-<12-char-id>`

Settings are stored in `general.*` inside `/app/config.yaml` (same file as Git/Telegram).

## Secrets (environment variables)

| Provider | Required | Optional |
|----------|----------|----------|
| **Vercel** | `VERCEL_TOKEN` | `VERCEL_ORG_ID` |
| **Netlify** | `NETLIFY_AUTH_TOKEN` | site id in Settings |
| **Cloudflare Pages** | `CLOUDFLARE_API_TOKEN` | `CLOUDFLARE_ACCOUNT_ID`, project name in Settings |

Install the matching CLI on the **same machine as the pipeline worker** (`vercel`, `netlify`, or `wrangler`) and ensure it is on `PATH`.

## Results on disk

Each attempt writes:

`data/state/<product_id>/auto_publish.json`

with stdout/stderr tails and `published_url` when detected.

Successful runs also set `published_url` on the product row when state is saved.

## Manual deploy

```bash
# From repo root, with venv activated:
python3 scripts/publish_product_now.py prod-xxxxxxxxxxxx
```

Uses current `config.yaml` toggles and the same provider logic as the worker.
