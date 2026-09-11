#!/bin/bash
# Staging load / soak test for KI-3 validation (uvicorn stability under traffic).
#
# Prerequisites: factory API reachable (e.g. ./scripts/run_prod_compose.sh up -d --build).
#
# Usage:
#   ./scripts/load_test_factory.sh
#   ./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 3600 --concurrency 10
#   ./scripts/load_test_factory.sh --profile-on-fail   # py-spy sample if requests fail
#
# Captures:
#   - HTTP success/error counts
#   - supervisor restart hints from docker logs (if compose stack running)
#   - optional crash log tail from ./data/logs/uvicorn-last-crash.log

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:9081}"
DURATION="${DURATION:-600}"
CONCURRENCY="${CONCURRENCY:-10}"
INTERVAL="${INTERVAL:-0.5}"
OUT_DIR="${OUT_DIR:-./data/logs/load-test}"
PROFILE_ON_FAIL="${PROFILE_ON_FAIL:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --profile-on-fail) PROFILE_ON_FAIL=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--base-url URL] [--duration SECS] [--concurrency N] [--interval SECS]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

BASE_URL="${BASE_URL%/}"
HEALTH_URL="${BASE_URL}/api/health"
LIST_URL="${BASE_URL}/api/pipeline/list"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
LOG_FILE="${OUT_DIR}/load-test-${STAMP}.log"
SUMMARY_FILE="${OUT_DIR}/load-test-${STAMP}-summary.txt"
OK_FILE="${OUT_DIR}/.ok-${STAMP}"
FAIL_FILE="${OUT_DIR}/.fail-${STAMP}"
: >"$OK_FILE"
: >"$FAIL_FILE"

echo "Load test: base=${BASE_URL} duration=${DURATION}s concurrency=${CONCURRENCY}" | tee "$LOG_FILE"

if ! curl -fsS "$HEALTH_URL" >/dev/null; then
  echo "ERROR: ${HEALTH_URL} not reachable — start the stack first." | tee -a "$LOG_FILE"
  exit 1
fi

start_ts=$(date +%s)
end_ts=$((start_ts + DURATION))

worker() {
  local id="$1"
  while [[ $(date +%s) -lt $end_ts ]]; do
    local path="$HEALTH_URL"
    if (( id % 3 == 0 )); then
      path="$LIST_URL"
    fi
    if curl -fsS -m 10 "$path" >/dev/null 2>&1; then
      echo "ok $(date -u +%H:%M:%S) worker=${id} ${path}" >>"$LOG_FILE"
      echo 1 >>"$OK_FILE"
    else
      echo "fail $(date -u +%H:%M:%S) worker=${id} ${path}" >>"$LOG_FILE"
      echo 1 >>"$FAIL_FILE"
    fi
    sleep "$INTERVAL"
  done
}

pids=()
for i in $(seq 1 "$CONCURRENCY"); do
  worker "$i" &
  pids+=($!)
done

for pid in "${pids[@]}"; do
  wait "$pid" || true
done

ok=$(wc -l <"$OK_FILE" | tr -d ' ')
fail=$(wc -l <"$FAIL_FILE" | tr -d ' ')
rm -f "$OK_FILE" "$FAIL_FILE"
elapsed=$(( $(date +%s) - start_ts ))
total=$((ok + fail))
rate="0"
if [[ "$elapsed" -gt 0 ]]; then
  rate=$(awk "BEGIN {printf \"%.2f\", $total / $elapsed}")
fi

{
  echo "=== load test summary ${STAMP} ==="
  echo "duration_secs=${elapsed}"
  echo "concurrency=${CONCURRENCY}"
  echo "requests_ok=${ok}"
  echo "requests_fail=${fail}"
  echo "requests_per_sec=${rate}"
  echo "health_url=${HEALTH_URL}"
} | tee "$SUMMARY_FILE"

if command -v docker >/dev/null 2>&1 && docker compose ps app &>/dev/null 2>&1; then
  echo "--- docker compose app log (restart hints) ---" >>"$SUMMARY_FILE"
  docker compose logs --tail=50 app 2>/dev/null | grep -E 'restart|crash|FATAL|Backend died' >>"$SUMMARY_FILE" || true
fi

if [[ -f ./data/logs/uvicorn-last-crash.log ]]; then
  echo "--- uvicorn-last-crash.log tail ---" >>"$SUMMARY_FILE"
  tail -n 20 ./data/logs/uvicorn-last-crash.log >>"$SUMMARY_FILE" || true
fi

echo "Summary written to ${SUMMARY_FILE}"

if [[ "$fail" -gt 0 ]]; then
  echo "WARNING: ${fail} failed requests — inspect ${LOG_FILE}"
  if [[ "$PROFILE_ON_FAIL" == "1" ]]; then
    PROFILE_FILE="${OUT_DIR}/py-spy-${STAMP}.txt"
    if command -v py-spy >/dev/null 2>&1; then
      UV_PID="$(pgrep -f 'uvicorn web.backend.main:app' | head -1 || true)"
      if [[ -n "$UV_PID" ]]; then
        echo "Capturing py-spy top (pid=${UV_PID}) → ${PROFILE_FILE}" | tee -a "$SUMMARY_FILE"
        py-spy top --pid "$UV_PID" --duration 15 --nonblocking >"$PROFILE_FILE" 2>&1 || true
      else
        echo "py-spy: uvicorn pid not found — skip profile" | tee -a "$SUMMARY_FILE"
      fi
    else
      echo "py-spy not installed — pip install py-spy" | tee -a "$SUMMARY_FILE"
    fi
  fi
  exit 1
fi

echo "OK: ${ok} requests, 0 failures"
