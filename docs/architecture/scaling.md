# Scaling story

Current defaults target **single-node** operation. Horizontal scale requires explicit env and external queue (not bundled).

## Today

| Component | Default | Notes |
|-----------|---------|--------|
| Pipeline DB | SQLite (`data/state/pipeline.db`) | Postgres optional via Admin → Settings |
| Pipeline worker | **One** in-process worker | `pipeline_worker.py` / orchestrator loop |
| Web API | Stateless FastAPI + Next.js in one container | Session JWT, local filesystem `data/` |
| Sandbox preview | Host Docker / subprocess | Not multi-host without shared storage |

## Single-node limits

- Concurrent pipeline products: bounded by worker concurrency env (`AIFACTORY_PIPELINE_*`).
- SQLite: writer lock under heavy parallel task updates — use Postgres for >~5 concurrent active products.
- `data/` volume: must be shared NFS/block storage if you run multiple API replicas (not supported out of the box).

## Target architecture (multi-node)

1. **Postgres** for pipeline state (`PIPELINE_DB_BACKEND=postgres`, `PIPELINE_DATABASE_URL`).
2. **Distributed queue** for tasks — Redis + RQ/Celery, or Temporal. Stub env: `AIFACTORY_PIPELINE_QUEUE_BACKEND=redis` (reserved; worker still in-process until implemented).
3. **Object storage** for `data/code`, telemetry, backups (S3-compatible).
4. **One sandbox runner** per host with Docker socket — route preview starts by affinity label.

## Env reference

| Variable | Purpose |
|----------|---------|
| `AIFACTORY_PROD=1` | Refuse weak admin passwords at startup |
| `AIFACTORY_DEMO_READONLY=1` | Public demo guard (not production) |
| `PIPELINE_DB_BACKEND` | `sqlite` \| `postgres` |
| `AIFACTORY_PIPELINE_WORKER_ID` | Reserved worker identity for multi-worker logs |
| `AIFACTORY_PIPELINE_QUEUE_BACKEND` | `inline` (default) \| `redis` (future) |

## What we do not claim yet

- Auto-scaling sandbox pools across regions
- Multi-master pipeline without external DB + queue
- HA SQLite

See [module-boundaries.md](./module-boundaries.md) for where to add queue integration (`orchestrator/` domain).
