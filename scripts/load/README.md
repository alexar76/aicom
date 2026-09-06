# Ecosystem load tests (Locust)

HTTP load coverage for the **local fleet** deployed by `./scripts/deploy_ecosystem.sh`.

| Block | Host (default) | Endpoints |
|-------|----------------|-----------|
| Factory | `:9081` | `/api/health`, trust-metrics, `/api/products` |
| Frontend | `:9080` | `/` |
| Hub | `:9083` | well-known, stats/live, search, capital/pricing, `/ai-market/v2/health` |
| Mesh | `:8090` | `/v1/stats`, activity, agents, optional `POST /v1/tasks` |
| ARGUS | `:8787` | `/health`, `/arena/stats`, optional `POST /ask` |
| Monitor | `:9100` | `/api/health`, `/monitor/api/state` |
| Pulse | `:5199` | `/pulse/` |

**Not included** (separate servers): lottery relayer, Platon, oracle-family.

Mesh-only tests also live in `ai-service-mesh/backend/load/`.

## Quick smoke (headless)

```bash
./scripts/load/run_load_smoke.sh
```

Defaults: 15 users, spawn 3/s, 60s. Override:

```bash
LOAD_USERS=25 LOAD_DURATION=90s ./scripts/load/run_load_smoke.sh
```

Reads URLs and tokens from repo `.env` (`FACTORY_URL`, `HUB_URL`, `MESH_API_TOKEN`, `ALIEN_API_TOKEN`, …).

## Interactive UI

```bash
pip install -r scripts/load/requirements.txt
locust -f scripts/load/locust_ecosystem.py
# open http://127.0.0.1:8089
```

## Heavy paths (opt-in)

| Env | Effect |
|-----|--------|
| `ARGUS_LOAD_ASK=1` | Adds `POST /ask` (needs `ARGUS_HTTP_TOKEN`; runs the LLM — use low user count) |
| `MESH_API_TOKEN` | Enables `POST /v1/tasks` when `LOAD_MESH_TASKS=1` |
| `LOAD_MESH_TASKS=1` | Include Mesh task creation (otherwise read-only) |
| `ALIEN_API_TOKEN` | Required for `/monitor/api/state` in production |

## After deploy

```bash
./scripts/deploy_ecosystem.sh
./scripts/verify_ecosystem_full.sh
./scripts/load/run_load_smoke.sh
```
