# PostgreSQL Setup

AI-Factory supports **SQLite** (default, zero-config) and **PostgreSQL 16** (production, multi-component).

## Quick Start (Docker Compose)

```bash
# Start with PostgreSQL
docker compose -f docker-compose.yml -f docker-compose.pg.yml up -d

# Check logs
docker compose logs app | grep -i "postgresql"
# Expected: "PostgreSQL backend initialized: postgresql://aicom:***@postgres:5432/aicom"

# Check migration status
docker compose exec app python -m aimarket_hub.migrations status
```

The PG overlay:
- Adds a `postgres` service (PostgreSQL 16 Alpine)
- Sets `DATABASE_URL` on the `app` service
- Adds a healthcheck dependency (`app` waits for PG to be ready)
- Creates a persistent volume `pgdata` for data survival across restarts

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(empty)* | PostgreSQL connection string. When set → PostgreSQL. When unset → SQLite. |
| `AIMARKET_DB_PATH` | `data/hub.db` | SQLite database path (ignored when `DATABASE_URL` is set) |
| `POSTGRES_USER` | `aicom` | PostgreSQL user (docker-compose only) |
| `POSTGRES_PASSWORD` | `aicom` | PostgreSQL password (docker-compose only) |
| `POSTGRES_DB` | `aicom` | PostgreSQL database name |
| `POSTGRES_PORT` | `5432` | PostgreSQL port on host |

### Connection String Format

```
postgresql://<user>:<password>@<host>:<port>/<database>
```

Examples:
```bash
# Docker Compose (internal network)
DATABASE_URL=postgresql://aicom:aicom@postgres:5432/aicom

# External PostgreSQL (e.g., AWS RDS, Supabase, Neon)
DATABASE_URL=postgresql://user:password@db.example.com:5432/aicom

# Local PostgreSQL
DATABASE_URL=postgresql://aicom:aicom@localhost:5432/aicom
```

## Database Schema

All tables are auto-created on first startup via versioned migrations.  
The `_migrations` table tracks which migrations have been applied.

| Migration | Contents |
|-----------|----------|
| 001 | `capabilities`, `peers` — core hub index |
| 002 | `invocation_stats` — invoke history |
| 003 | `reputation_events` — signed outcomes, disputes |
| 004 | `channels`, `debited_receipts` — payment channel ledger |
| 005 | `provenance_receipts` — AI provenance receipts |

### Key PostgreSQL features used

- **JSONB** for `input_schema`, `output_schema`, `parent_receipts`, `tee_attestation`, `raw_json`
- **TIMESTAMPTZ** for all timestamps (UTC, timezone-aware)
- **SERIAL** for auto-incrementing IDs
- **Partial indexes** — `idx_channels_expires WHERE status = 'open'`
- **UNIQUE constraints** — `(capability_id, product_id, source_hub)`, `receipt_id`
- **Connection pooling** — `psycopg_pool` with min=2, max=8 connections

## Migrating from SQLite to PostgreSQL

### Option 1: Fresh start (no existing data)

Just start with the PG overlay — all tables are created automatically.

### Option 2: Migrate existing data

```bash
# 1. Preview what will be migrated (dry run)
python scripts/migrate_to_postgres.py --dry-run \
  --sqlite-db data/hub.db \
  --sqlite-channels data/channels.db \
  --sqlite-provenance data/provenance.db \
  --pg-url postgresql://aicom:aicom@localhost:5432/aicom

# 2. Run the migration
python scripts/migrate_to_postgres.py \
  --sqlite-db data/hub.db \
  --sqlite-channels data/channels.db \
  --sqlite-provenance data/provenance.db \
  --pg-url postgresql://aicom:aicom@localhost:5432/aicom

# 3. Verify row counts match
python scripts/migrate_to_postgres.py --verify-only \
  --pg-url postgresql://aicom:aicom@localhost:5432/aicom
```

The migration script:
- Reads all rows from SQLite tables
- Bulk-inserts into PostgreSQL
- Handles type conversions (SQLite REAL → PG DOUBLE PRECISION, JSON → JSONB)
- Preserves all data, timestamps, and relationships
- Verifies row counts after migration

## Backup & Restore

### PostgreSQL

```bash
# Backup
docker compose -f docker-compose.pg.yml exec postgres \
  pg_dump -U aicom aicom > backup_$(date +%Y%m%d).sql

# Restore
docker compose -f docker-compose.pg.yml exec -T postgres \
  psql -U aicom aicom < backup_20260523.sql
```

### SQLite (default)

```bash
# Backup
cp data/hub.db data/hub.db.bak
cp data/channels.db data/channels.db.bak
cp data/provenance.db data/provenance.db.bak

# Restore
cp data/hub.db.bak data/hub.db
cp data/channels.db.bak data/channels.db
cp data/provenance.db.bak data/provenance.db
```

## Performance Tuning

### PostgreSQL

Recommended `postgresql.conf` overrides for production:

```ini
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
wal_buffers = 16MB
random_page_cost = 1.1
effective_io_concurrency = 200
max_connections = 50
```

To apply in Docker Compose, mount a custom config:

```yaml
postgres:
  volumes:
    - ./config/postgresql.conf:/etc/postgresql/postgresql.conf:ro
  command: ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
```

### Connection Pool

The app uses `psycopg_pool.ConnectionPool` with:
- **min_size: 2** — keep at least 2 idle connections
- **max_size: 8** — up to 8 concurrent connections

Adjust via env vars if needed:

```bash
AIMARKET_PG_POOL_MIN=4
AIMARKET_PG_POOL_MAX=16
```

## Troubleshooting

### "could not connect to server"

- Check PostgreSQL is running: `docker compose -f docker-compose.pg.yml ps postgres`
- Check `DATABASE_URL` is correct in `.env`
- Check network: the app must reach `postgres:5432` (inside Docker) or `localhost:5432` (outside)

### "relation already exists"

- This is normal — idempotent migrations use `CREATE TABLE IF NOT EXISTS`
- To force re-creation: `docker compose down -v` (destroys the PG volume!)

### "migration 00x failed"

```bash
# Check migration status
python -m aimarket_hub.migrations status

# Apply remaining migrations
python -m aimarket_hub.migrations up

# Roll back last migration (if needed)
python -m aimarket_hub.migrations down
```

### Switching back to SQLite

Remove `DATABASE_URL` from `.env` and restart. The app will use SQLite with the same schema.  
Note: data is NOT synced between SQLite and PostgreSQL — they are independent stores.
