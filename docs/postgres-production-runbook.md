# Postgres production runbook

Use Postgres when multiple API/worker replicas share pipeline or UNI state, or when you need durable backups and point-in-time recovery.

## Pipeline (`PIPELINE_DB_BACKEND=postgres`)

1. Provision Postgres 15+ and create a database/user.
2. Set in `.env` / Compose:
   - `PIPELINE_DB_BACKEND=postgres`
   - `PIPELINE_DATABASE_URL=postgresql://user:pass@host:5432/aicom_pipeline`
3. Run migrations from Admin → Settings → Database, or start the worker once (schema is applied on connect).
4. **Cutover from SQLite**
   - Stop pipeline workers and API writers.
   - Export JSON snapshot: copy `data/state/pipeline.json` (backup).
   - Run `python -m orchestrator.migrate --json data/state/pipeline.json --db data/state/pipeline.db` if you still use SQLite as intermediate.
   - Switch env to Postgres and start a single worker; verify `/api/admin/pipeline` shows products.
   - Scale workers after confirming no duplicate task runners fight the same queue (use one writer or Postgres backend only).

## UNI ledger (`UNI_DB_BACKEND=postgres`)

1. `UNI_DB_BACKEND=postgres`
2. `UNI_DATABASE_URL=postgresql://user:pass@host:5432/aicom_uni`
3. Restart API; wallet/receipt endpoints create tables on first use.
4. SQLite UNI data does **not** auto-migrate — export receipts via `/api/uni/receipts` before cutover if you need history.

## Operations

| Task | Command / note |
|------|----------------|
| Backup | `pg_dump -Fc $PIPELINE_DATABASE_URL > pipeline.dump` |
| Restore | `pg_restore -d $PIPELINE_DATABASE_URL --clean pipeline.dump` |
| Health | `GET /api/health` + Admin pipeline product count |
| Rollback | Revert env to `sqlite`, restore `pipeline.db` + `pipeline.json` from backup |

## Failure modes

- **Split brain**: two workers on SQLite — use Postgres or a single worker.
- **Stale JSON sync**: with Postgres backend, JSON is a secondary mirror; do not edit `pipeline.json` by hand while workers run.
- **Connection pool exhaustion**: raise `max_connections` or lower Uvicorn/worker count.

See also: `docs/pipeline-operations.md`, `.env.example` (`PIPELINE_*`, `UNI_*`).
