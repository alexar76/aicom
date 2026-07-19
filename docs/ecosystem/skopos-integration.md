# SKOPOS — ecosystem integration

**SKOPOS** ([`skopos/`](../../skopos/)) is the fleet **observability satellite** of AICOM — nginx & Apache analytics over SSH, Security Center, scan history, and an AI analyst. Self-hosted; PostgreSQL recommended for production.

> 🌐 Languages: **English** · [Русский](./skopos-integration-ru.md) · [Español](./skopos-integration-es.md)

---

## Live surfaces

| Surface | URL | Role |
|---------|-----|------|
| **Dashboard** | [skopos.modelmarket.dev](https://skopos.modelmarket.dev) | Streamlit UI (password-protected in production) |
| **Public status** | `GET /healthz` | Non-secret JSON for Alien Monitor & probes |
| **Alien Monitor** | [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) | 3D graph node — click **SKOPOS** sphere |

---

## Alien Monitor node

| Env | Purpose |
|-----|---------|
| `ALIEN_SKOPOS_URL` | Poll `GET /healthz` (default `https://skopos.modelmarket.dev`) |
| `ALIEN_PUBLIC_SKOPOS_URL` | Panel link — dashboard URL |
| `ALIEN_SKOPOS_GITHUB_URL` | GitHub link in panel (default `https://github.com/alexar76/skopos`) |

**Health response (non-secret):**

```json
{
  "ok": true,
  "service": "skopos",
  "version": "0.1.0",
  "database": "postgresql",
  "log_parsers": ["nginx", "apache"],
  "servers_monitored": 1,
  "requests_total": 4035,
  "security_score": 87
}
```

**Graph position:** west shelf near Metis (`skopos` @ `-11.5, -3.5, 1.5`).  
**Edges:** `factory → skopos` (traffic telemetry), `skopos → metis` (host fleet), `skopos → hub` (ecosystem posture).

Click the sphere → **Open SKOPOS dashboard**, GitHub, docs, integration guide. Metrics show servers monitored, total parsed requests, and security score — no secrets.

---

## Deploy on Metis node

Production test stack: [`metis/deploy/skopos-test/`](../../metis/deploy/skopos-test/).

```bash
cd metis/deploy/skopos-test
./remote-sync.sh
```

Nginx vhost `skopos.modelmarket.dev` is in [`metis/deploy/nginx.conf`](../../metis/deploy/nginx.conf) — proxy `:8501` (UI) and `:8502` (`/healthz`).

TLS (once DNS points to the Metis host):

```bash
docker run --rm -v /opt/metis/deploy/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot certbot/certbot certonly --webroot \
  -w /var/www/certbot -d skopos.modelmarket.dev --agree-tos -m you@example.com
docker restart metis-nginx
```

---

## Monorepo paths

| Path | Role |
|------|------|
| `skopos/` | Application source |
| `metis/deploy/skopos-test/` | Docker Compose + `servers.yaml` for Metis host |
| `alien-monitor/backend/skopos_*.py` | Graph node + live poll |
| `docs/ecosystem/skopos-integration.md` | This file |

Satellite repo: [alexar76/skopos](https://github.com/alexar76/skopos) — publish via `./scripts/publish_all_repos.sh --satellite skopos`.

**Landing:** [skopos.modelmarket.dev](https://skopos.modelmarket.dev) (live) · [alexar76.github.io/skopos](https://alexar76.github.io/skopos/) (GitHub Pages, EN/RU/ES). Source: `skopos/docs/landing/index.html`. Workflow: `skopos/.github/workflows/pages.yml`.

---

## Independence

SKOPOS does not require Factory, Hub, or Metis at runtime. Alien Monitor degrades gracefully when `/healthz` is unreachable (node shows `offline`).

---

## AIMarket economy (optional supply side)

SKOPOS can **sell fleet intelligence** to other AI agents via the [AIMarket Protocol v2](../../aimarket-protocol/spec.md) — same pattern as Metis `/aimarket/invoke`.

**Off by default.** Enable only when you want SKOPOS in the federated agent economy:

```bash
SKOPOS_AIMARKET_ENABLED=1
SKOPOS_AIMARKET_PUBLIC_URL=https://skopos.modelmarket.dev
# Optional: protect invoke with API key
SKOPOS_AIMARKET_API_KEY=your-secret
# Optional: auto-register capabilities on Hub at startup
SKOPOS_HUB_URL=https://modelmarket.dev
SKOPOS_AIMARKET_AUTO_REGISTER=1
SKOPOS_AIMARKET_PUBLISH_TOKEN=...
```

| Endpoint | Role |
|----------|------|
| `GET /.well-known/ai-market.json` | Discovery |
| `GET /ai-market/v2/manifest` | Capability catalog |
| `POST /aimarket/invoke` | Hub invoke contract `{input, product_id, capability_id}` → `{result}` |

### Billable capabilities

| ID | What it sells | ~USD/call |
|----|----------------|-----------|
| `skopos.fleet.status@v1` | Heartbeat + security score | $0.01 |
| `skopos.security.posture@v1` | Fleet score, alerts, remarks | $0.08 |
| `skopos.traffic.summary@v1` | 24h traffic aggregates | $0.05 |
| `skopos.briefing@v1` | Human fleet briefing (rules / LLM) | $0.15 |

ARGUS, Factory, or Alien Monitor can **buy** posture context without SSH access to your fleet.

### Consumer mode (optional)

Set `SKOPOS_HUB_URL` so SKOPOS can **discover** Hub capabilities (free search). Paid invokes from SKOPOS to oracles require a wallet integration (future); standalone mode ignores missing Hub.

Nginx on Metis should proxy port **8502** for `/healthz`, `/.well-known/*`, `/ai-market/*`, and `/aimarket/invoke` (see `metis/deploy/nginx.conf`).
