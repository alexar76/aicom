#!/usr/bin/env bash
# Headless ecosystem load smoke — Factory, Hub, Mesh, ARGUS, Monitor, Pulse.
# Excludes lottery, Platon, oracle-family (remote hosts).
#
# Usage:
#   ./scripts/load/run_load_smoke.sh
#   LOAD_USERS=30 LOAD_DURATION=2m ./scripts/load/run_load_smoke.sh
#   ARGUS_LOAD_ASK=1 ./scripts/load/run_load_smoke.sh   # includes POST /ask (heavy)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

USERS="${LOAD_USERS:-8}"
RATE="${LOAD_SPAWN_RATE:-2}"
TIME="${LOAD_DURATION:-60s}"
LOCUST_FILE="$ROOT/scripts/load/locust_ecosystem.py"
VENV="$ROOT/scripts/load/.venv"

ensure_locust() {
  if command -v locust >/dev/null 2>&1; then
    return 0
  fi
  if [[ -x "$VENV/bin/locust" ]]; then
    export PATH="$VENV/bin:$PATH"
    return 0
  fi
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/scripts/load/requirements.txt"
  export PATH="$VENV/bin:$PATH"
}

ensure_locust

echo "=== Ecosystem load smoke ==="
echo "Users=$USERS spawn_rate=$RATE duration=$TIME"
echo "Factory=${FACTORY_URL:-http://127.0.0.1:9081} Hub=${HUB_URL:-http://127.0.0.1:9083}"
echo "Mesh=${MESH_URL:-http://127.0.0.1:8090} ARGUS=${ARGUS_URL:-http://127.0.0.1:8787}"
echo "Monitor=${MONITOR_URL:-http://127.0.0.1:9100} Pulse=${PULSE_URL:-http://127.0.0.1:5199}"
echo "ARGUS_LOAD_ASK=${ARGUS_LOAD_ASK:-0} (set 1 + ARGUS_HTTP_TOKEN for /ask)"
echo "LOAD_MESH_TASKS=${LOAD_MESH_TASKS:-0} (set 1 to POST /v1/tasks)"
echo ""

export PYTHONPATH="$ROOT/scripts/load${PYTHONPATH:+:$PYTHONPATH}"

locust -f "$LOCUST_FILE" \
  --headless \
  -u "$USERS" \
  -r "$RATE" \
  -t "$TIME" \
  --only-summary \
  --exit-code-on-error 0
