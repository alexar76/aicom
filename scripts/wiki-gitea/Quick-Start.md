# Quick Start

## Requirements

- Docker + Docker Compose
- LLM API keys (DeepSeek, OpenAI, Anthropic, etc.) — configure in **Admin → LLM Providers**
- ~4 GB RAM minimum; bind mount for `data/` recommended

## Install

```bash
git clone http://5.129.212.122/Superowner/aicom.git
cd aicom
cp -n .env.example .env
# Edit .env: at least one LLM provider key
docker compose up -d --build
```

| URL | Purpose |
|-----|---------|
| `http://localhost:9080/` | Storefront |
| `http://localhost:9080/admin/login` | Admin UI |
| `http://localhost:9081/api/health` | API health (direct) |
| `http://localhost:9081/api/docs` | Swagger |

## First login

There is **no** default password in the repo.

| Mode | Password |
|------|----------|
| Interactive (`docker compose run -it app`) | Console prompt |
| Detached (`up -d`) | `data/secrets/bootstrap_admin.txt` |
| Dev only | `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` in `.env` |

See [[Security]].

## First product

1. Log in as `admin`
2. **New product** tab — enter a one-line idea
3. Choose **marketing_landing** (faster) or **full_software**
4. Watch **Pipeline** tab — stages advance automatically

CLI shortcut (after bootstrap):

```bash
export DEMO_ADMIN_PASSWORD='your-bootstrap-password'
./demo.sh "SaaS for remote team standups"
```

## Production URL

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh --public-url https://your-factory.example.com
```

Fills **missing** `.env` keys only; never overwrites existing secrets. Details: [[Deployment]].

## Full reference

- [`README.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/README.md)
- [`docs/USER_GUIDE.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.md) — illustrated walkthrough
