# Scaling story

Current defaults target **single-node** operation. Horizontal scale requires explicit env and external queue (not bundled).

## Today

| Component | Default | Notes |
|-----------|---------|--------|
| Pipeline DB | SQLite (`data/state/pipeline.db`) | Postgres via `docker-compose.prod.yml` or Admin → Settings |
| Pipeline worker | **One** in-process worker | Split overlay: dedicated `pipeline-worker` container |
| Web API | Stateless FastAPI + Next.js in one container | Session JWT, local filesystem `data/` |
| Sandbox preview | Host Docker / subprocess | Not multi-host without shared storage |

## Production stack (recommended)

For real traffic, use the production overlay instead of the default single-container SQLite stack:

```bash
python3 scripts/fill_production_env.py --env-file .env --public-url https://your-host
./scripts/run_prod_compose.sh up -d --build
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 600
```

This enables:

- **PostgreSQL** pipeline store (`PIPELINE_DB_ENV_PINNED=1` — compose wins over Admin YAML)
- **Split services** — API, frontend, pipeline worker, director worker
- **`AIFACTORY_PROD=1`** — weak-password guards
- **`UVICORN_WORKERS=1`** until KI-3 load test closes (see `docs/known-issues.md`)

Compose file: `docker-compose.prod.yml` (layers on `docker-compose.yml`).

## Single-node limits

- Concurrent pipeline products: bounded by worker concurrency env (`AIFACTORY_PIPELINE_*`).
- SQLite: writer lock under heavy parallel task updates — use Postgres for >~5 concurrent active products.
- `data/` volume: must be shared NFS/block storage if you run multiple API replicas (not supported out of the box).

## Target architecture (multi-node)

1. **Postgres** for pipeline state (`PIPELINE_DB_BACKEND=postgres`, `PIPELINE_DATABASE_URL`).
2. **Distributed queue** for tasks — Redis wake list (`AIFACTORY_PIPELINE_QUEUE_BACKEND=redis`, `AIFACTORY_REDIS_URL`). Implemented in `orchestrator/redis_wake.py`; full Celery/Temporal still future.
3. **Object storage** for `data/code`, telemetry, backups (S3-compatible).
4. **One sandbox runner** per host with Docker socket — route preview starts by affinity label.

## Env reference

| Variable | Purpose |
|----------|---------|
| `AIFACTORY_PROD=1` | Refuse weak admin passwords at startup |
| `AIFACTORY_DEMO_READONLY=1` | Public demo guard (not production) |
| `PIPELINE_DB_BACKEND` | `sqlite` \| `postgres` |
| `PIPELINE_DB_ENV_PINNED` | `1` in prod compose — prevents Admin YAML from reverting Postgres to SQLite |
| `AIFACTORY_PIPELINE_WORKER_ID` | Reserved worker identity for multi-worker logs |
| `AIFACTORY_PIPELINE_QUEUE_BACKEND` | `inline` (default) \| `redis` (cross-worker wake) |
| `AIFACTORY_REDIS_URL` | Redis URL when queue backend is `redis` |

## What we do not claim yet

- Auto-scaling sandbox pools across regions
- Multi-master pipeline without external DB + queue
- HA SQLite

See [module-boundaries.md](./module-boundaries.md) for where to add queue integration (`orchestrator/` domain).
