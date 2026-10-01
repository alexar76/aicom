#!/usr/bin/env bash
# Headless ecosystem load — Factory, Hub, Mesh, ARGUS, Monitor, Pulse, plus
# optional fleet reads (Metis/GAIA/ATLAS/…) and a rare heavy POST coda.
#
# Usage:
#   ./scripts/load/run_load_smoke.sh
#   LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
#   LOAD_TARGET=public LOAD_MODE=full ./scripts/load/run_load_smoke.sh
#   LOAD_TARGET=public LOAD_MODE=heavy ./scripts/load/run_load_smoke.sh
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

TARGET="${LOAD_TARGET:-local}"
MODE="${LOAD_MODE:-smoke}"
if [[ "$TARGET" == "public" ]]; then
  # Live operator fleet — read-only mix. Override any one URL to retarget a block.
  export FACTORY_URL="${FACTORY_URL:-https://magic-ai-factory.com}"
  export FRONTEND_URL="${FRONTEND_URL:-https://magic-ai-factory.com}"
  export HUB_URL="${HUB_URL:-https://modelmarket.dev}"
  export MESH_URL="${MESH_URL:-https://service-mesh.modelmarket.dev}"
  export ARGUS_URL="${ARGUS_URL:-https://magic-ai-factory.com}"
  export ARGUS_HEALTH_PATH="${ARGUS_HEALTH_PATH:-/arena}"
  export MONITOR_URL="${MONITOR_URL:-https://monitor.modelmarket.dev}"
  export PULSE_URL="${PULSE_URL:-https://pulse.modelmarket.dev}"
  export PULSE_SHELL_PATH="${PULSE_SHELL_PATH:-/pulse/}"
  export METIS_URL="${METIS_URL:-https://metis.modelmarket.dev}"
  export ORACLES_URL="${ORACLES_URL:-https://oracles.modelmarket.dev}"
  export LOTTERY_URL="${LOTTERY_URL:-https://lottery.modelmarket.dev}"
  export GAIA_URL="${GAIA_URL:-https://iot.modelmarket.dev}"
  export ATLAS_URL="${ATLAS_URL:-https://atlas.modelmarket.dev}"
  export MOMUS_URL="${MOMUS_URL:-https://momus.modelmarket.dev}"
  export SKOPOS_URL="${SKOPOS_URL:-https://skopos.modelmarket.dev}"
  export LOGOS_URL="${LOGOS_URL:-https://logos.modelmarket.dev}"
  export VERIFY_URL="${VERIFY_URL:-https://verify.modelmarket.dev}"
  export FORGE_URL="${FORGE_URL:-https://forge.modelmarket.dev}"
  export THEMIS_URL="${THEMIS_URL:-https://themis.modelmarket.dev}"
fi

SCOPE="${LOAD_SCOPE:-core}"

# Methodology defaults: smoke = short step, constant = shelf, ramp = climb until it breaks.
case "$MODE" in
  smoke)
    USERS="${LOAD_USERS:-8}"
    RATE="${LOAD_SPAWN_RATE:-4}"
    TIME="${LOAD_DURATION:-90s}"
    ;;
  constant)
    USERS="${LOAD_USERS:-20}"
    RATE="${LOAD_SPAWN_RATE:-2}"
    TIME="${LOAD_DURATION:-10m}"
    ;;
  ramp)
    USERS="${LOAD_USERS:-80}"
    RATE="${LOAD_SPAWN_RATE:-2}"
    TIME="${LOAD_DURATION:-20m}"
    unset ARGUS_LOAD_ASK LOAD_MESH_TASKS LOAD_METIS_VERIFY LOAD_HUB_INVOKE
    export ARGUS_LOAD_ASK=0 LOAD_MESH_TASKS=0 LOAD_METIS_VERIFY=0 LOAD_HUB_INVOKE=0
    ;;
  full)
    SCOPE=full
    USERS="${LOAD_USERS:-24}"
    RATE="${LOAD_SPAWN_RATE:-2}"
    TIME="${LOAD_DURATION:-10m}"
    ;;
  heavy)
    SCOPE=heavy
    USERS="${LOAD_USERS:-5}"
    RATE="${LOAD_SPAWN_RATE:-5}"
    TIME="${LOAD_DURATION:-3m}"
    export LOAD_MESH_TASKS="${LOAD_MESH_TASKS:-1}"
    export LOAD_METIS_VERIFY="${LOAD_METIS_VERIFY:-1}"
    export LOAD_HUB_INVOKE="${LOAD_HUB_INVOKE:-1}"
    export LOAD_PIPELINE_CREATE="${LOAD_PIPELINE_CREATE:-1}"
    export AIMARKET_SANDBOX_VISITOR="${AIMARKET_SANDBOX_VISITOR:-loadtest-$(date -u +%Y%m%dT%H%M%SZ)}"
    if [[ "$TARGET" == "public" ]]; then
      export ARGUS_ASK_PATH="${ARGUS_ASK_PATH:-/argus/ask}"
      if [[ -z "${ARGUS_HTTP_TOKEN:-}" ]]; then
        # Live token lives in the factory argus container, not laptop .env. Do not echo it.
        ARGUS_HTTP_TOKEN="$(ssh -o BatchMode=yes -o ConnectTimeout=15 my-vps \
          'docker exec argus printenv ARGUS_HTTP_TOKEN' 2>/dev/null || true)"
        ARGUS_HTTP_TOKEN="${ARGUS_HTTP_TOKEN//$'\r'/}"
        ARGUS_HTTP_TOKEN="${ARGUS_HTTP_TOKEN//$'\n'/}"
        export ARGUS_HTTP_TOKEN
        if [[ -z "${ARGUS_HTTP_TOKEN}" ]]; then
          echo "WARNING: ARGUS_HTTP_TOKEN empty after factory docker exec — POST /ask will skip" >&2
        else
          echo "ARGUS_HTTP_TOKEN: pulled from factory argus container"
        fi
      fi
    fi
    if [[ -n "${ARGUS_HTTP_TOKEN:-}" ]]; then
      export ARGUS_LOAD_ASK="${ARGUS_LOAD_ASK:-1}"
    fi
    ;;
  *)
    echo "unknown LOAD_MODE=$MODE (smoke|constant|ramp|full|heavy)" >&2
    exit 2
    ;;
esac
if [[ "$SCOPE" == "full" && "$MODE" != "heavy" ]]; then
  if [[ "$MODE" == "ramp" ]]; then
    USERS="${LOAD_USERS:-40}"
    export LOAD_RAMP_MAX="${LOAD_RAMP_MAX:-40}"
  fi
fi
export LOAD_MODE="$MODE"
export LOAD_SCOPE="$SCOPE"
LOCUST_FILE="$ROOT/scripts/load/locust_ecosystem.py"
VENV311="$ROOT/scripts/load/.venv311"
VENV="$ROOT/scripts/load/.venv"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="$ROOT/scripts/load/reports"
mkdir -p "$REPORT_DIR"

ensure_locust() {
  # Prefer 3.11+ venv (Locust 2.46). The 3.9 .venv is leftover and too old.
  if [[ -x "$VENV311/bin/locust" ]]; then
    export PATH="$VENV311/bin:$PATH"
    return 0
  fi
  if [[ -x "$VENV/bin/locust" ]]; then
    export PATH="$VENV/bin:$PATH"
    return 0
  fi
  if command -v locust >/dev/null 2>&1; then
    return 0
  fi
  local py="python3"
  if command -v python3.11 >/dev/null 2>&1; then
    py="python3.11"
  elif command -v python3.12 >/dev/null 2>&1; then
    py="python3.12"
  fi
  echo "Creating locust venv with $($py --version) …"
  "$py" -m venv "$VENV"
  "$VENV/bin/pip" install -q -U pip
  "$VENV/bin/pip" install -q -r "$ROOT/scripts/load/requirements.txt"
  export PATH="$VENV/bin:$PATH"
}

preflight() {
  echo "=== Preflight (one GET per health URL) ==="
  local url code
  local pairs=(
    "factory ${FACTORY_URL:-http://127.0.0.1:9081}/api/health"
    "hub ${HUB_URL:-http://127.0.0.1:9083}/ai-market/v2/health"
    "mesh ${MESH_URL:-http://127.0.0.1:8090}/health"
    "argus-arena ${ARGUS_URL:-http://127.0.0.1:8787}/arena/stats"
    "monitor ${MONITOR_URL:-http://127.0.0.1:9100}/api/health"
    "frontend ${FRONTEND_URL:-http://127.0.0.1:9080}/"
    "pulse ${PULSE_URL:-http://127.0.0.1:5199}${PULSE_SHELL_PATH:-/pulse/}"
    "pulse-factory https://magic-ai-factory.com/pulse/"
  )
  case "$SCOPE" in
    full)
      pairs+=(
        "metis ${METIS_URL:-https://metis.modelmarket.dev}/health"
        "oracles ${ORACLES_URL:-https://oracles.modelmarket.dev}/health"
        "lottery ${LOTTERY_URL:-https://lottery.modelmarket.dev}/"
        "gaia ${GAIA_URL:-https://iot.modelmarket.dev}/"
        "atlas ${ATLAS_URL:-https://atlas.modelmarket.dev}/"
        "momus ${MOMUS_URL:-https://momus.modelmarket.dev}/health"
        "skopos ${SKOPOS_URL:-https://skopos.modelmarket.dev}/health"
      )
      ;;
  esac
  for pair in "${pairs[@]}"; do
    local name="${pair%% *}"
    url="${pair#* }"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 -A 'aicom-load-preflight/1' "$url" || echo 000)"
    echo "  $name  HTTP $code  $url"
  done
  echo ""
}

ensure_locust
if [[ "$TARGET" == "public" ]]; then
  python3 "$ROOT/scripts/load/topology.py" | tee "$REPORT_DIR/$MODE-$STAMP-topology.txt"
  echo ""
fi
preflight

echo "=== Ecosystem load ($MODE) ==="
echo "target=$TARGET mode=$MODE scope=$SCOPE Users=$USERS spawn_rate=$RATE duration=$TIME"
echo "Factory=${FACTORY_URL:-http://127.0.0.1:9081} Hub=${HUB_URL:-http://127.0.0.1:9083}"
echo "Mesh=${MESH_URL:-http://127.0.0.1:8090} ARGUS=${ARGUS_URL:-http://127.0.0.1:8787}"
echo "Monitor=${MONITOR_URL:-http://127.0.0.1:9100} Pulse=${PULSE_URL:-http://127.0.0.1:5199}"
echo "ARGUS_LOAD_ASK=${ARGUS_LOAD_ASK:-0} token=${ARGUS_HTTP_TOKEN:+set} path=${ARGUS_ASK_PATH:-/ask}"
echo "LOAD_MESH_TASKS=${LOAD_MESH_TASKS:-0} LOAD_METIS_VERIFY=${LOAD_METIS_VERIFY:-0} LOAD_HUB_INVOKE=${LOAD_HUB_INVOKE:-0} LOAD_PIPELINE_CREATE=${LOAD_PIPELINE_CREATE:-0}"
echo "report=$REPORT_DIR/$MODE-$STAMP"
echo ""

export PYTHONPATH="$ROOT/scripts/load${PYTHONPATH:+:$PYTHONPATH}"

# 429 on Mesh is counted success in locust_ecosystem.py. Fail the process if more
# than 5% of remaining requests still fail.
locust -f "$LOCUST_FILE" \
  --headless \
  -u "$USERS" \
  -r "$RATE" \
  -t "$TIME" \
  --html "$REPORT_DIR/$MODE-$STAMP.html" \
  --csv "$REPORT_DIR/$MODE-$STAMP" \
  --only-summary \
  --exit-code-on-error 1
