# Production domain — magic-ai-factory.com

Canonical public origin for this deployment: **`https://magic-ai-factory.com`**. During first bring-up you may briefly use **`http://`** in `NEXT_PUBLIC_SITE_URL`; switch to **`https://`** as soon as TLS is live and **rebuild** the `app` image.

## Environment

In the project root `.env` (not committed), set:

```bash
# Canonical URL for Open Graph, sitemap, and server-side metadata (baked at `docker compose build`).
NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com

# Public demo: passwordless admin + readonly guard — block backup, restore, settings save (required).
AIFACTORY_DEMO_READONLY=1
```

> **Disclaimer:** Anyone can open the shared admin as `admin` with **no password** (click **Enter admin demo**). `AIFACTORY_DEMO_READONLY=1` prevents visitors from changing platform settings or running factory backup/restore onto the shared catalog. Details: [security.md](./security.md#public-demo-mode-aifactory_demo_readonly1).

If nginx serves **HTTP on port 80** only, use:

```bash
NEXT_PUBLIC_SITE_URL=http://magic-ai-factory.com
```

Then rebuild the app image so the Next.js bundle picks up the value:

```bash
docker compose build app --no-cache
docker compose up -d
```

## Reverse proxy (nginx)

The Compose stack still publishes the UI on host **`9080`** by default. Nginx terminates TLS (optional) and proxies to that port.

Checked-in copy (keep in sync with `/etc/nginx`): **`deploy/nginx/magic-ai-factory.com.conf`**.

Example — HTTP on port 80 (same content as the file above):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name magic-ai-factory.com www.magic-ai-factory.com;

    location / {
        proxy_pass http://127.0.0.1:9080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Enable and reload:

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### TLS with Certbot (Let’s Encrypt)

Prerequisites: **A/AAAA records** for `magic-ai-factory.com` and `www.magic-ai-factory.com` point to this host; nginx answers on **:80** for the HTTP vhost above.

Issue a certificate, install it into nginx, and **redirect HTTP → HTTPS**:

```bash
sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

Replace `YOUR_EMAIL@example.com` with a working address (Let’s Encrypt account / expiry notices).

Certbot **rewrites** `/etc/nginx/sites-enabled/magic-ai-factory.com` (adds `:443 ssl` and adjusts `:80`). The file under **`deploy/nginx/magic-ai-factory.com.conf`** in git stays as a **pre-TLS** template for new installs; after Certbot, treat the live nginx file as the source of truth on the server.

### Automatic renewal (required on Ubuntu)

The `certbot` package ships a **systemd timer** that runs `certbot renew` **twice daily** and reloads nginx when a cert is renewed (nginx plugin).

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
sudo systemctl status certbot.timer --no-pager
```

Sanity-check renewals (no write to live certs):

```bash
sudo certbot renew --dry-run --cert-name magic-ai-factory.com
```

Optional: list all timers:

```bash
systemctl list-timers 'certbot*'
```

After HTTPS works, set **`NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com`** in `.env` and **`docker compose build app && docker compose up -d`** so Next.js metadata and OG URLs use `https`.

### Alien Monitor (`/monitor/`)

Public demo: **https://magic-ai-factory.com/monitor/** — 3D ecosystem visualizer (LIVE mode against this host’s Hub/Factory/Prometheus).

Deploy or refresh:

```bash
./scripts/deploy_alien_monitor.sh
```

Nginx snippet (also in `deploy/nginx/snippets/alien-monitor.conf`): proxies `/monitor/` → `127.0.0.1:9100`. The deploy script patches the live Certbot vhost if the block is missing.

## Related

- Compose port overrides: `AICOM_PORT_FRONTEND`, `AICOM_PORT_API` in `.env.example`
- Marketing / SSR base: `NEXT_PUBLIC_SITE_URL` in `docker-compose.yml` and Dockerfile build `ARG`
