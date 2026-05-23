# Deployment Guide

## Docker Compose (recommended for staging)

```bash
export MESH_API_TOKEN=$(openssl rand -hex 24)
export MESH_ADMIN_TOKEN=$(openssl rand -hex 24)
docker compose up -d --build
```

- API: port **8090**
- Dashboard: port **5173** (nginx static)

## Environment

Copy `.env.example` → `.env` and set:

```env
MESH_ENV=production
MESH_CORS_ORIGINS=https://mesh.yourdomain.com
MESH_API_TOKEN=...
MESH_ADMIN_TOKEN=...
MESH_HUB_URL=https://hub.yourdomain.com
```

## Kubernetes (outline)

1. **Deployment** `mesh-api` — 2+ replicas, probes on `/health`.
2. **Service** ClusterIP → ingress.
3. **Secret** `mesh-tokens` for API/admin tokens.
4. **PVC** or managed Postgres for registry/activity.
5. **Ingress** TLS (cert-manager).

## Observability

- Poll `GET /v1/stats` for SLO dashboards.
- Stream `GET /v1/activity/stream` into your SIEM.
- Structured logs from uvicorn (JSON formatter recommended).

## Load testing

Before production cutover:

```bash
locust -f backend/load/locustfile.py --host https://mesh.staging.example \
  --headless -u 50 -r 10 -t 2m
```

Target: p95 `< 500ms` on `/v1/stats` and `/v1/activity` at 50 users.

## Hub federation

Set `MESH_HUB_URL` to your `aimarket-hub` deployment. Mesh discovery will merge hub search results with local verified agents.
