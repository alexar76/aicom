# Deployment

## Docker Compose (default)

```bash
cp -n .env.example .env
docker compose up -d --build
```

Persistent state: host directory **`./data` → `/app/data`** (products, pipeline DB, secrets, LLM logs).

## Production script

[`scripts/deploy.sh`](http://5.129.212.122/Superowner/aicom/src/branch/main/scripts/deploy.sh):

```bash
./scripts/deploy.sh --public-url https://magic-ai-factory.com
```

For **magic-ai-factory.com**, ensure `.env` contains **`AIFACTORY_DEMO_READONLY=1`** (append-only via `fill_production_env.py` when using `--public-url`, or set manually). See [[Public-Demo]].

Uses [`scripts/fill_production_env.py`](http://5.129.212.122/Superowner/aicom/src/branch/main/scripts/fill_production_env.py) to append **only missing** keys:

- `NEXT_PUBLIC_SITE_URL`, `AIFACTORY_CORS_ORIGINS`
- `AIFACTORY_FIREWALL_RULES_FERNET_KEY` (when possible)
- `AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION=1` default

Then `docker compose build` + `up -d app`.

## Public hostname (this fleet)

Production: **magic-ai-factory.com** — nginx → Compose **9080**.

Full notes: [`docs/production-domain.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/production-domain.md)

## Static storefront deploy (optional)

After DevOps stage: Vercel / Netlify / Cloudflare Pages tokens in `.env` and `data/state/.../auto_publish.json`.

Guide: [`docs/auto-publish.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/auto-publish.md)

## Full-stack cloud backends

Railway / Fly / Cloud Run layout for `full_software` products:

[`docs/deploy-full-software-cloud.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/deploy-full-software-cloud.md)

## Configuration layers

YAML fragments + admin overlay — see [`docs/configuration.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/configuration.md) and wiki [[Documentation-Index]].

## Health check

```bash
curl -s http://127.0.0.1:9081/api/health
docker compose ps app
```

Entrypoint watchdog restarts uvicorn on zombie/dead health failures.
