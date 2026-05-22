# Production domain — modelmarket.dev

Canonical public origin for the **AIMarket Federation Hub**: **`https://modelmarket.dev`**.

## DNS

Point **A/AAAA** records for `modelmarket.dev` and `www.modelmarket.dev` to the host running nginx (this fleet: `5.129.212.122`).

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
- [`aimarket-hub/README.md`](../aimarket-hub/README.md) — hub operations
- [`docs/production-domain.md`](./production-domain.md) — magic-ai-factory.com TLS
