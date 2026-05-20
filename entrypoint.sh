#!/bin/bash
# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Entrypoint
# ============================================================================
# Starts all services:
#   1. FastAPI backend (port 8081)
#   2. Pipeline Worker (background)
#   3. Next.js frontend (port 8080) — main user-facing port
# ============================================================================

set -e

echo "=== AI-Factory v2.1 Starting ==="

# Activate Python virtual environment
source /app/venv/bin/activate

# LLM keys + sandbox demo password from Docker secrets or data/secrets/* (not compose `environment:`).
# shellcheck source=/dev/null
. /app/scripts/load_docker_secret_env.sh
load_llm_provider_secrets
load_sandbox_demo_password

# DeepSeek: persist API key + v4 models + reset circuit (survives volume / deploy)
python3 -m llm.persist_deepseek || echo "⚠ DeepSeek provider sync skipped (no key yet)"

# Sandbox previews: replace factory boilerplate index.html with spec-built product pages
python3 /app/scripts/materialize_all_spec_landings.py || echo "⚠ Spec landing materialize skipped"

# ── Ensure All Data Directories Exist (bind mount compatibility) ──────────
mkdir -p /app/data/config /app/data/logs /app/data/secrets /app/data/state
mkdir -p /app/data/arch /app/data/bugs /app/data/code /app/data/specs
mkdir -p /app/data/telemetry /app/data/feedback
mkdir -p /app/data/reports/director
echo "✓ Data directories verified"

# ── First run: autonomous pipeline (Director periodically creates products) ─
PIPELINE_FIRST_RUN="/app/data/config/first_run_pipeline_mode.done"
if [ ! -f "$PIPELINE_FIRST_RUN" ]; then
    echo ""
    echo "┌──────────────────────────────────────────────────────────────────────────┐"
    echo "│ AI-Factory — pipeline mode (first run with this data volume)             │"
    echo "│                                                                          │"
    echo "│  1) Autonomous development — AI Director creates products on a schedule   │"
    echo "│     (general.auto_pipeline = true).                                       │"
    echo "│  2) Ideas only — new products only when you provide an idea               │"
    echo "│     (admin UI / CLI).                                                     │"
    echo "└──────────────────────────────────────────────────────────────────────────┘"
    AP_RAW=""
    if [ -n "${AIFACTORY_AUTONOMOUS_PIPELINE:-}" ]; then
        AP_RAW="${AIFACTORY_AUTONOMOUS_PIPELINE}"
        echo "Mode from AIFACTORY_AUTONOMOUS_PIPELINE=${AP_RAW}"
    elif [ -t 0 ]; then
        read -r -p "Choose [1 or 2], Enter = 2 (ideas only): " choice || true
        choice="${choice:-2}"
        case "$choice" in
            1) AP_RAW="1" ;;
            *) AP_RAW="0" ;;
        esac
    else
        AP_RAW="0"
        echo "Non-interactive mode: default is 0 — ideas only."
        echo "Tip: docker run -e AIFACTORY_AUTONOMOUS_PIPELINE=1 … or enable in Admin → Settings."
    fi
    export AUTO_PIPELINE_VALUE="${AP_RAW}"
    python3 /app/scripts/set_auto_pipeline.py
    touch "$PIPELINE_FIRST_RUN"
    echo "✓ Mode saved to config (change anytime: Admin → Settings → Autonomous development)."
    echo ""
fi

# ── Persistent JWT Secret Key ──────────────────────────────────────────────
# Generate a persistent secret key so multiple workers can validate tokens.
JWT_SECRET_FILE="/app/data/secrets/jwt_secret.key"
mkdir -p /app/data/secrets
if [ ! -f "$JWT_SECRET_FILE" ]; then
    echo "Generating persistent JWT secret key..."
    python3 -c "
import os, hashlib
# Generate a 64-char hex key from random data
key = hashlib.sha256(os.urandom(64)).hexdigest()
with open('$JWT_SECRET_FILE', 'w') as f:
    f.write(key)
os.chmod('$JWT_SECRET_FILE', 0o600)
print('JWT secret key created')
"
fi
chmod 600 "$JWT_SECRET_FILE" 2>/dev/null || true
# Never trust an empty JWT_SECRET_KEY from compose/env — file is authoritative in Docker.
export JWT_SECRET_KEY="$(tr -d '\n\r' < "$JWT_SECRET_FILE")"
if [ "${#JWT_SECRET_KEY}" -lt 32 ]; then
    echo "ERROR: JWT secret from $JWT_SECRET_FILE is shorter than 32 characters. Regenerate the file."
    exit 1
fi
echo "JWT secret key loaded (persistent across restarts)"

# ── Customer storefront JWT (persistent; invalidates logins if rotated) ───
CUSTOMER_JWT_FILE="/app/data/secrets/customer_jwt.key"
if [ -z "${CUSTOMER_JWT_SECRET:-}" ]; then
    if [ ! -f "$CUSTOMER_JWT_FILE" ]; then
        echo "Generating persistent customer JWT secret..."
        python3 -c "import secrets; open('$CUSTOMER_JWT_FILE','w').write(secrets.token_hex(48))"
    fi
    export CUSTOMER_JWT_SECRET=$(cat "$CUSTOMER_JWT_FILE")
    echo "Customer JWT secret loaded (persistent across restarts)"
else
    echo "CUSTOMER_JWT_SECRET provided via environment (not using file)"
fi

# ── Admin bootstrap (interactive TTY password, random file, or AIFACTORY_DEV_BOOTSTRAP_PASSWORD) ─
# For first install with a prompt: docker compose run --rm -it app  (or ./run.sh with a TTY)
cd /app
python3 -m security.bootstrap_admin || exit 1

# ── Prometheus Multiproc Directory ─────────────────────────────────────────
# The prometheus_client library requires this directory to exist when
# PROMETHEUS_MULTIPROC_DIR is set (multiprocess mode). Without it, the
# backend crashes on startup with FileNotFoundError.
mkdir -p "${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_multiproc}"

# ── Pipeline DB backend (SQLite default, optional PostgreSQL from Admin Settings) ─
python3 /app/scripts/apply_pipeline_db_config.py || true
PIPELINE_DB_BACKEND="${PIPELINE_DB_BACKEND:-sqlite}"
echo "Pipeline DB backend: ${PIPELINE_DB_BACKEND}"

# ── SQLite Auto-Migration ─────────────────────────────────────────────────
# When USE_SQLITE=true, automatically migrate existing JSON data to SQLite.
# The migration is idempotent — safe to run on every container start.
SQLITE_PATH="${SQLITE_PATH:-/app/data/state/pipeline.db}"
if [[ "${PIPELINE_DB_BACKEND,,}" == "postgres" ]]; then
    echo "PIPELINE_DB_BACKEND=postgres — worker/API use PostgreSQL (set PIPELINE_DATABASE_URL in .env or Admin Settings)"
    if [[ -z "${PIPELINE_DATABASE_URL:-}" ]]; then
        echo "⚠ PIPELINE_DATABASE_URL is empty — configure Admin → Settings → Pipeline database before relying on Postgres"
    fi
elif [[ "${USE_SQLITE,,}" == "true" ]]; then
    echo "USE_SQLITE=true — checking SQLite backend..."
    mkdir -p "$(dirname "$SQLITE_PATH")"

    if [ -f "/app/data/state/pipeline.json" ]; then
        echo "Running JSON → SQLite migration..."
        python3 -m orchestrator.migrate \
            --json /app/data/state/pipeline.json \
            --db "$SQLITE_PATH" \
        && echo "✓ SQLite migration complete" \
        || echo "⚠ Migration failed or no data to migrate — SQLite will start fresh"
    else
        echo "No existing pipeline.json found — SQLite will initialize empty"
    fi

    export USE_SQLITE=true
    echo "✓ SQLite backend enabled (path: $SQLITE_PATH)"
else
    echo "USE_SQLITE not set or false — using default JSON backend"
fi

# ── Pipeline Worker ────────────────────────────────────────────────────────
echo "Starting Pipeline Worker..."
cd /app
python3 -m pipeline_worker &
WORKER_PID=$!
echo "Pipeline Worker started (PID: $WORKER_PID)"

# ── Director AI Worker ─────────────────────────────────────────────────────
echo "Starting Director AI Worker..."
cd /app
python3 -m director.worker &
DIRECTOR_PID=$!
echo "Director AI Worker started (PID: $DIRECTOR_PID)"

# ── FastAPI Backend ────────────────────────────────────────────────────────
# Default: 1 worker (each process would otherwise pick a random JWT secret).
# Set JWT_SECRET_KEY in the environment to allow multiple workers (recommended under load).
if [ -z "${UVICORN_WORKERS:-}" ]; then
  UVICORN_WORKERS=1
fi
# Cap workers — multiprocess supervisor has caused worker crash-loops under load (API 500/timeouts).
case "${UVICORN_WORKERS}" in
  ''|*[!0-9]*) UVICORN_WORKERS=1 ;;
esac
if [ "${UVICORN_WORKERS}" -gt 2 ] 2>/dev/null; then
  UVICORN_WORKERS=2
fi
start_backend() {
  cd /app
  python3 -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8081 --workers "${UVICORN_WORKERS}" &
  echo $! >/tmp/aicom-backend.pid
}

echo "Starting FastAPI backend on port 8081 (${UVICORN_WORKERS} worker(s))..."
start_backend
echo "Backend started (PID: $(cat /tmp/aicom-backend.pid))"

# Restart API if the worker dies (pipeline/QA load otherwise leaves Next.js proxying to ECONNREFUSED → HTTP 500).
(
  while true; do
    sleep 5
    pid="$(cat /tmp/aicom-backend.pid 2>/dev/null || true)"
    if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then
      echo "FastAPI backend not running — restarting..."
      start_backend
      echo "Backend restarted (PID: $(cat /tmp/aicom-backend.pid))"
    fi
  done
) &

# ── Next.js Frontend ──────────────────────────────────────────────────────
echo "Starting Next.js frontend on port 8080..."
cd /app/web/frontend
exec npx next start -p 8080
