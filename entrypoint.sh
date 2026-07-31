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

# ── Git credential helper (product pushes; never embed tokens in remotes) ───
# Persist credentials inside the data volume rather than the container FS.
GIT_CRED_FILE="${GIT_CREDENTIALS_FILE:-${AIFACTORY_DATA_ROOT:-/app/data}/secrets/git-credentials}"
if [ ! -f "$GIT_CRED_FILE" ]; then
  mkdir -p "$(dirname "$GIT_CRED_FILE")" || true
  touch "$GIT_CRED_FILE" || true
fi
chmod 600 "$GIT_CRED_FILE" 2>/dev/null || true
git config --global credential.helper "store --file ${GIT_CRED_FILE}" || true

# Fernet vault sync + HashiCorp/env resolver → export LLM keys
python3 -m security.bootstrap_secrets || echo "⚠ Secret vault bootstrap skipped"

# DeepSeek: persist API key + v4 models + reset circuit (survives volume / deploy)
python3 -m llm.persist_deepseek || echo "⚠ DeepSeek provider sync skipped (no key yet)"

# Sandbox previews: replace factory boilerplate index.html with spec-built product pages
python3 /app/scripts/materialize_all_spec_landings.py || echo "⚠ Spec landing materialize skipped"

# ── Ensure All Data Directories Exist (bind mount compatibility) ──────────
mkdir -p /app/data/config /app/data/logs /app/data/secrets /app/data/secrets/zk /app/data/state
mkdir -p /app/data/logs/marketing /app/data/funnel
mkdir -p /app/data/arch /app/data/bugs /app/data/code /app/data/specs
mkdir -p /app/data/telemetry /app/data/feedback
mkdir -p /app/data/reports/director
python3 /app/scripts/ensure_config_overlay.py || echo "⚠ Config overlay bootstrap skipped"
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
    # secrets.token_hex(32) → 64 hex chars / 256 bits of CSPRNG entropy.
    # (Previous version hashed urandom(64) through SHA-256, which threw away
    # half the entropy for no security benefit.)
    JWT_SECRET_FILE_ESCAPED="$JWT_SECRET_FILE" python3 - <<'PY'
import os, secrets
path = os.environ["JWT_SECRET_FILE_ESCAPED"]
with open(path, "w") as f:
    f.write(secrets.token_hex(32))
os.chmod(path, 0o600)
print("JWT secret key created")
PY
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
    # Lock down to owner-only — this file signs customer storefront sessions.
    chmod 600 "$CUSTOMER_JWT_FILE" 2>/dev/null || true
    export CUSTOMER_JWT_SECRET=$(cat "$CUSTOMER_JWT_FILE")
    echo "Customer JWT secret loaded (persistent across restarts)"
else
    echo "CUSTOMER_JWT_SECRET provided via environment (not using file)"
fi

# ── Admin bootstrap (interactive TTY password, random file, or AIFACTORY_DEV_BOOTSTRAP_PASSWORD) ─
# For first install with a prompt: docker compose run --rm -it app  (or ./run.sh with a TTY)
cd /app
python3 -m security.bootstrap_admin || exit 1
python3 -c "from security.prod_startup_guard import assert_production_startup_safe; assert_production_startup_safe()" || exit 1

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
# ── Production DB credential guard ─────────────────────────────────────────
# Refuse to start in production (AIFACTORY_PROD=1) with the well-known default
# Postgres password that docker-compose.pg.yml used to ship. Mirrors the
# weak-admin-password check in security.prod_startup_guard.
if [ "${AIFACTORY_PROD:-0}" = "1" ] && [ "${POSTGRES_PASSWORD:-}" = "aicom" ]; then
    echo "FATAL: AIFACTORY_PROD=1 but POSTGRES_PASSWORD=aicom (known default)."
    echo "       Set a strong POSTGRES_PASSWORD in .env (e.g. openssl rand -base64 24) and restart."
    exit 1
fi

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

# ── Role selection (docker-compose.split.yml) ──────────────────────────────
# Default (unset / "all"): single-container — workers + API + frontend.
# `api`, `frontend`, `pipeline-worker`, `director-worker`: run just that role.
ROLE="${AICOM_ROLE:-all}"
echo "Role: ${ROLE}"

run_pipeline_worker() {
  echo "Starting Pipeline Worker..."
  cd /app
  python3 -m pipeline_worker &
  WORKER_PID=$!
  echo "Pipeline Worker started (PID: $WORKER_PID)"
}

run_director_worker() {
  echo "Starting Director AI Worker..."
  cd /app
  python3 -m director.worker &
  DIRECTOR_PID=$!
  echo "Director AI Worker started (PID: $DIRECTOR_PID)"
}

case "${ROLE}" in
  pipeline-worker)
    cd /app
    exec python3 -m pipeline_worker
    ;;
  director-worker)
    cd /app
    exec python3 -m director.worker
    ;;
  frontend)
    cd /app/web/frontend
    exec npx next start -p 8080
    ;;
  api|all)
    if [ "${ROLE}" = "all" ]; then
      run_pipeline_worker
      run_director_worker
    fi
    ;;
  *)
    echo "FATAL: unknown AICOM_ROLE=${ROLE} (expected one of: all|api|frontend|pipeline-worker|director-worker)"
    exit 1
    ;;
esac

# ── FastAPI Backend ────────────────────────────────────────────────────────
# Bind address for uvicorn. Default 0.0.0.0 keeps single-container / compose
# port publishing working out of the box. Multi-tenant or shared-host deploys
# that put a reverse proxy in front can set AIFACTORY_BIND_ADDRESS=127.0.0.1
# so the API is only reachable on loopback (proxy → loopback). The supervisor
# health check always probes 127.0.0.1, which works for either binding.
BACKEND_BIND_ADDRESS="${AIFACTORY_BIND_ADDRESS:-0.0.0.0}"

# UVICORN_WORKERS sanitization (integer >=1, capped at 4).
# Workers >1 require PostgreSQL (PIPELINE_DB_BACKEND=postgres). SQLite's
# single-writer lock causes crash loops under concurrent multiprocess load.
# Default 1 worker is safe for SQLite. For multi-worker production, set
# PIPELINE_DB_BACKEND=postgres and PIPELINE_DATABASE_URL before increasing.
# Root cause of multi-worker instability under load is tracked as KI-3 in
# docs/known-issues.md — supervisor below is mitigation, not a fix.
if [ -z "${UVICORN_WORKERS:-}" ]; then
  UVICORN_WORKERS=1
fi
case "${UVICORN_WORKERS}" in
  ''|*[!0-9]*) UVICORN_WORKERS=1 ;;
esac
if [ "${UVICORN_WORKERS}" -gt 4 ] 2>/dev/null; then
  echo "⚠ UVICORN_WORKERS=${UVICORN_WORKERS} > 4 — capping at 4 (see docs/known-issues.md KI-3)."
  UVICORN_WORKERS=4
fi
if [ "${USE_SQLITE:-false}" = "true" ] && [ "${UVICORN_WORKERS}" -gt 1 ] 2>/dev/null; then
  echo "⚠ USE_SQLITE=true — forcing UVICORN_WORKERS=1 (SQLite single-writer; KI-3)."
  UVICORN_WORKERS=1
fi

write_crash_telemetry() {
  local reason="$1"
  {
    echo "=== uvicorn crash $(date -u +%Y-%m-%dT%H:%M:%SZ) reason=${reason} ==="
    echo "UVICORN_WORKERS=${UVICORN_WORKERS} USE_SQLITE=${USE_SQLITE:-false}"
    echo "PROMETHEUS_MULTIPROC_DIR=${PROMETHEUS_MULTIPROC_DIR:-<unset>}"
    if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ] && [ -d "${PROMETHEUS_MULTIPROC_DIR}" ]; then
      echo "prometheus_multiproc_files=$(find "${PROMETHEUS_MULTIPROC_DIR}" -type f 2>/dev/null | wc -l | tr -d ' ')"
    fi
    echo "--- log tail ---"
    tail -n 30 "$BACKEND_LOG_FILE" 2>/dev/null || true
    echo ""
  } >>"$BACKEND_DIAG_FILE" 2>/dev/null || true
}

BACKEND_LOG_DIR="/app/data/logs"
mkdir -p "$BACKEND_LOG_DIR"
BACKEND_PID_FILE="/tmp/aicom-backend.pid"
BACKEND_LOG_FILE="$BACKEND_LOG_DIR/uvicorn.log"
BACKEND_DIAG_FILE="$BACKEND_LOG_DIR/uvicorn-last-crash.log"

start_backend() {
  cd /app
  # Stale prometheus_client multiproc files from prior runs can cause worker
  # startup failures (FileExistsError / corrupt counters). Clean before fork.
  if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ] && [ -d "${PROMETHEUS_MULTIPROC_DIR}" ]; then
    find "${PROMETHEUS_MULTIPROC_DIR}" -mindepth 1 -delete 2>/dev/null || true
  fi
  # Rotate the previous run's log into a "last crash" file so the next
  # restart still has the most recent diagnostics on disk — invaluable
  # when the supervisor restarts faster than the operator can `docker logs`.
  if [ -s "$BACKEND_LOG_FILE" ]; then
    mv -f "$BACKEND_LOG_FILE" "$BACKEND_DIAG_FILE"
  fi
  python3 -m uvicorn web.backend.main:app \
      --host "${BACKEND_BIND_ADDRESS}" --port 8081 \
      --workers "${UVICORN_WORKERS}" \
      --log-level "${UVICORN_LOG_LEVEL:-info}" \
      --access-log \
      >>"$BACKEND_LOG_FILE" 2>&1 &
  echo $! >"$BACKEND_PID_FILE"
}

echo "Starting FastAPI backend on port 8081 (${UVICORN_WORKERS} worker(s))..."
start_backend
echo "Backend started (PID: $(cat $BACKEND_PID_FILE))"

# ── Supervisor with exponential backoff + circuit breaker ─────────────────
# Previous version blindly restarted every 5s — a stuck dependency (DB down,
# config error, OOM-killer hammering) would put the host into a busy-loop.
# Now:
#   - exponential backoff 5s → 10s → 20s → 40s → 60s cap
#   - reset backoff if backend stayed up for >5 min
#   - after MAX_RESTARTS within a 30-min window, give up and exit 1 so the
#     outer container runtime (docker, k8s) can apply its own restart policy
#     instead of us masking a persistent failure
#   - on restart, log the tail of the crash log so the operator sees why
(
  MAX_RESTARTS="${BACKEND_MAX_RESTARTS:-20}"
  WINDOW_SECS="${BACKEND_RESTART_WINDOW_SECS:-1800}"
  HEALTH_PATH="${BACKEND_HEALTH_PATH:-/api/health}"
  HEALTH_FAILS_BEFORE_KILL="${BACKEND_HEALTH_FAILS_BEFORE_KILL:-5}"
  backoff=5
  consecutive_health_fails=0
  restart_count=0
  window_start=$(date +%s)
  last_restart_at=0

  while true; do
    sleep 5
    pid="$(cat "$BACKEND_PID_FILE" 2>/dev/null || true)"
    now=$(date +%s)
    needs_restart=0
    crash_reason=""

    if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then
      needs_restart=1
      crash_reason="process gone"
    elif [ -r "/proc/${pid}/status" ] && grep -qE '^State:[[:space:]]*Z' "/proc/${pid}/status" 2>/dev/null; then
      needs_restart=1
      crash_reason="zombie process"
    elif ! curl -sf --max-time 8 "http://127.0.0.1:8081${HEALTH_PATH}" >/dev/null 2>&1; then
      consecutive_health_fails=$((consecutive_health_fails + 1))
      if [ "$consecutive_health_fails" -ge "$HEALTH_FAILS_BEFORE_KILL" ]; then
        needs_restart=1
        crash_reason="health check failed ${consecutive_health_fails}x in a row"
        kill -TERM "$pid" 2>/dev/null || true
        # give uvicorn a moment to flush its log before we read it
        sleep 1
      fi
    else
      consecutive_health_fails=0
      # If backend has been up for >5min since last restart, reset backoff
      if [ "$last_restart_at" -gt 0 ] && [ $((now - last_restart_at)) -gt 300 ]; then
        if [ "$backoff" -ne 5 ]; then
          echo "Backend healthy >5min — resetting restart backoff."
        fi
        backoff=5
      fi
    fi

    if [ "$needs_restart" -eq 1 ]; then
      # Restart-rate circuit breaker
      if [ $((now - window_start)) -gt "$WINDOW_SECS" ]; then
        window_start=$now
        restart_count=0
      fi
      restart_count=$((restart_count + 1))
      if [ "$restart_count" -gt "$MAX_RESTARTS" ]; then
        echo "FATAL: backend restarted $restart_count times in ${WINDOW_SECS}s — giving up."
        echo "Last crash diagnostics:"
        tail -n 50 "$BACKEND_LOG_FILE" 2>/dev/null || true
        exit 1
      fi

      echo "FastAPI backend down ($crash_reason). Last 20 log lines:"
      write_crash_telemetry "$crash_reason"
      tail -n 20 "$BACKEND_LOG_FILE" 2>/dev/null || echo "  (no log)"
      echo "Restart ${restart_count}/${MAX_RESTARTS} (window ${WINDOW_SECS}s); backoff ${backoff}s."
      sleep "$backoff"
      start_backend
      last_restart_at=$(date +%s)
      consecutive_health_fails=0
      # exponential backoff, capped at 60s
      backoff=$((backoff * 2))
      [ "$backoff" -gt 60 ] && backoff=60
      echo "Backend restarted (PID: $(cat $BACKEND_PID_FILE))"
    fi
  done
) &

# ── Next.js Frontend (single-container "all" role only) ──────────────────
# In split-services mode (AICOM_ROLE=api) the frontend runs in its own
# container — this `exec` is skipped and the backend supervisor keeps PID 1.
if [ "${ROLE}" = "all" ]; then
  echo "Starting Next.js frontend on port 8080..."
  cd /app/web/frontend
  exec npx next start -p 8080
else
  echo "AICOM_ROLE=${ROLE} — frontend is in a separate container; backend remains PID 1."
  # `wait` blocks until the supervisor subshell exits (it only exits on
  # circuit-breaker trip), keeping the API container alive.
  wait
fi
