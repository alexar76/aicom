# Production domain — modelmarket.dev

Canonical public origin for the **AIMarket Federation Hub**: **`https://modelmarket.dev`**.

## DNS

Point **A/AAAA** records for `modelmarket.dev` and `www.modelmarket.dev` to the host running nginx (this fleet: `modeldev.modelmarket.dev`).

### Ecosystem landing — `modeldev.modelmarket.dev`

Public ecosystem map (`ecosystem-landing/`) plus **SEO landings** (`/learn/`, `/oracles/`, `/guides/`, `/encyclopedia/`, `sitemap.xml`). Built by `./scripts/build_ecosystem_landing.sh` before deploy. See [`seo-landings/README.md`](../seo-landings/README.md).

DNS at **Timeweb**:

| Host | Type | Value |
|------|------|-------|
| `modeldev` | A | `<origin-ip>` |

One-shot (root):

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modeldev-ecosystem-landing.sh
```

Routine refresh after editing `ecosystem-landing/` (also runs automatically from `./scripts/deploy_ecosystem.sh`):

```bash
sudo ./scripts/deploy_ecosystem_landing.sh
```

Verify:

```bash
curl -sI https://modeldev.modelmarket.dev/ | head -5
curl -s https://modeldev.modelmarket.dev/ | grep -o '<title>[^<]*</title>'
curl -sI https://modeldev.modelmarket.dev/sitemap.xml | head -3
curl -sI https://modeldev.modelmarket.dev/oracles/platon/ | head -3
./scripts/verify_seo_landings.sh
```

### Provenance verifier — `verify.modelmarket.dev`

Static client-side receipt verifier (`docs/verifier/` — Ed25519 via tweetnacl, no backend). Served by the **factory host** (same fleet as modeldev). Receipts' `verify_url` (`AIMARKET_VERIFY_DOMAIN`) points here.

| Subdomain | Type | Value |
|-----------|------|-------|
| `verify` | A | `<origin-ip>` |

Deploy (on the factory host):

```bash
rsync -a --delete docs/verifier/ /var/www/verify.modelmarket.dev/
sudo cp deploy/nginx/verify.modelmarket.dev.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/verify.modelmarket.dev.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d verify.modelmarket.dev
sudo nginx -t && sudo systemctl reload nginx
```

Verify:

```bash
curl -sI https://verify.modelmarket.dev/ | head -5
curl -s https://verify.modelmarket.dev/ | grep -o '<title>[^<]*</title>'
```

### Platon oracle — `oracles.modelmarket.dev`

**Platon Shadow Oracle** runs on **`oracles.modelmarket.dev`**. DNS at **Timeweb** points the subdomain **directly** to that host (no factory nginx proxy).

> **Note:** `oracles/` and `platon/` in this monorepo are **archival mirrors** of the external oracle stack. They are **not** deployed by `./scripts/deploy_ecosystem.sh` — run setup on the Platon host only.

| Host | Type | Value |
|------|------|-------|
| `oracles` | A | `<origin-ip>` |

After DNS propagates, on **the Platon server** (`oracles.modelmarket.dev`, root):

```bash
# Platon app: PUBLIC_URL=https://oracles.modelmarket.dev, listen 127.0.0.1:8080
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

From the factory host, register in federation:

```bash
./scripts/announce-platon-oracles.sh
```

Verify:

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

## Stack layout

| Service | Host port | Notes |
|---------|-----------|--------|
| AIMarket Hub (Docker) | `127.0.0.1:9083` → container `9080` | `modelmarket-hub` container |
| nginx | `:80` / `:443` | TLS termination, proxy to hub |

AI-Factory UI remains on **magic-ai-factory.com** (`:9080`). The hub seeds federation from  
`https://magic-ai-factory.com/.well-known/ai-market.json`.

## One-shot setup (root)

```bash
sudo CERTBOT_EMAIL=you@example.com /path/to/aicom/scripts/setup-modelmarket-ssl.sh
```

Or manually:

```bash
sudo cp deploy/nginx/modelmarket.dev.conf /etc/nginx/sites-available/modelmarket.dev
sudo ln -sf /etc/nginx/sites-available/modelmarket.dev /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

docker build -f aimarket-hub/Dockerfile -t modelmarket-hub:latest .
docker run -d --name modelmarket-hub --restart unless-stopped \
  -p 127.0.0.1:9083:9080 \
  -e AIMARKET_HUB_NAME=modelmarket.dev \
  -e AIMARKET_HUB_URL=https://modelmarket.dev \
  -e AIMARKET_SEED_LIST=https://magic-ai-factory.com/.well-known/ai-market.json \
  -v modelmarket_hub_data:/app/data \
  modelmarket-hub:latest

sudo certbot --nginx -d modelmarket.dev -d www.modelmarket.dev \
  --non-interactive --agree-tos --redirect -m you@example.com
```

## Automatic renewal

Ubuntu **`certbot.timer`** runs `certbot renew` twice daily and reloads nginx when a cert is renewed.

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
sudo certbot renew --dry-run --cert-name modelmarket.dev
```

## Hub environment

| Variable | Example |
|----------|---------|
| `AIMARKET_HUB_NAME` | `modelmarket.dev` |
| `AIMARKET_HUB_URL` | `https://modelmarket.dev` |
| `AIMARKET_SEED_LIST` | `https://magic-ai-factory.com/.well-known/ai-market.json` |

## Related

- [`deploy/nginx/modelmarket.dev.conf`](../deploy/nginx/modelmarket.dev.conf) — nginx template (pre-certbot; live file is certbot-managed on server)
- [`aimarket-hub/README.md`](https://github.com/alexar76/aimarket-hub/blob/main/README.md) — hub operations
- [`docs/production-domain.md`](./production-domain.md) — magic-ai-factory.com TLS
