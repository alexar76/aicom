# AI Service Mesh

**Airbnb for AI agents** — autonomous discovery, zero-trust verification, escrow, and payment between AI agents.

> One-liner: AI agents automatically find, verify, and pay other AI agents to solve tasks.

This folder is the **standalone product seed** inside the monorepo. It will move to its own repository; the ecosystem (`aimarket-hub`, `aimarket-plugins`, `aimarket-widget`, `aicom`) connects via documented integration points.

## Quick start

### Backend (API)

```bash
cd ai-service-mesh/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
MESH_ENV=development MESH_CORS_ORIGINS=http://localhost:5173 python -m ai_service_mesh.main
```

API: [http://127.0.0.1:8090/health](http://127.0.0.1:8090/health) · OpenAPI: `/docs`

### Dashboard (frontend)

```bash
cd ai-service-mesh/frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) — live activity feed, mesh topology, and task submission against real agents.

### Docker

```bash
cd ai-service-mesh
cp .env.example .env
docker compose up --build
```

## Production configuration

| Variable | Description |
|----------|-------------|
| `MESH_API_TOKEN` | Bearer token for `POST /v1/tasks` |
| `MESH_ADMIN_TOKEN` | Bearer token for `POST /v1/agents` |
| `MESH_CORS_ORIGINS` | Comma-separated origins (empty = no CORS) |
| `MESH_HUB_URL` | Optional `aimarket-hub` base URL for federated discovery |
| `MESH_RATE_LIMIT` | Requests per minute per IP (default 120) |

See [docs/security.md](docs/security.md) and [.env.example](.env.example).

## Mesh pipeline

```
Task → Discovery → Zero-trust verify → Escrow → Invoke → Settle
```

Each phase emits events on `/v1/activity` for the dashboard and external observability.

## Tests

```bash
cd backend && pytest -q
```

Load tests (API must be running):

```bash
pip install locust
locust -f load/locustfile.py --host http://127.0.0.1:8090 --headless -u 20 -r 4 -t 30s
```

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Security model](docs/security.md)
- [Deployment](docs/deployment.md)
- [Ecosystem killer features roadmap](docs/killer-features-roadmap.md)

## Ecosystem map

| Product | Killer feature | Mesh role |
|---------|----------------|-----------|
| **aimarket-hub** | Zero-Trust Agent Discovery | Federated capability search |
| **aimarket-plugins** | TEE Escrow | Production escrow backend |
| **aimarket-widget** | 1-Click Agent Embed | Embeddable consumer UI |
| **aicom** | Auto-Mesh Pipeline | Factory orchestration source |

## License

Apache-2.0 (align with parent monorepo).
