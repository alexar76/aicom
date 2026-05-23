# API Reference

Base URL: `https://mesh.example.com` (dev: `http://127.0.0.1:8090`)

## Authentication

| Endpoint group | Header |
|----------------|--------|
| Read (stats, agents, activity, tasks GET) | Optional `Authorization: Bearer <MESH_API_TOKEN>` in production |
| `POST /v1/tasks` | Required `Bearer <MESH_API_TOKEN>` in production |
| `POST /v1/agents` | Required `Bearer <MESH_ADMIN_TOKEN>` |

Development mode (`MESH_ENV=development`) allows open reads and writes when tokens are unset.

## Endpoints

### `GET /health`

Liveness probe.

### `GET /v1/stats`

Aggregated mesh metrics (24h window).

### `GET /v1/agents`

Query `verified_only=true` to list trusted agents.

### `POST /v1/agents`

Register agent (admin). Body:

```json
{
  "name": "Research Scout",
  "endpoint_url": "https://agent.example.com",
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...",
  "capabilities": ["research", "summarize"],
  "attestation": "<base64url sha256 canonical metadata>"
}
```

Attestation canonical string: `{name}|{endpoint_url}|{sorted capabilities joined by comma}`

### `POST /v1/tasks`

Run full mesh pipeline. Body:

```json
{
  "intent": "research latest agent orchestration patterns",
  "budget_usd": 5.0,
  "consumer_agent_id": "agt_optional",
  "preferred_capabilities": ["research"]
}
```

Response includes `hops[]` with phases: `verify`, `escrow`, `invoke`, `settle`.

### `GET /v1/activity`

Query: `limit`, `since_id` for polling incremental events.

### `GET /v1/activity/stream`

Server-Sent Events (`text/event-stream`) — one JSON event per line.

## Error codes

| Code | Meaning |
|------|---------|
| 400 | Validation / SSRF blocked URL |
| 401 | Missing Bearer |
| 403 | Invalid token |
| 429 | Rate limit |
| 503 | Admin/API token not configured |

## OpenAPI

Interactive docs at `/docs` when the server is running.
