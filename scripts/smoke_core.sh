#!/usr/bin/env bash
# ============================================================================
# Smoke test for the core stack (./start.sh).  Keeps the one-command path from
# rotting: run it in CI or after ./start.sh to confirm every core surface is up.
#
#   ./scripts/smoke_core.sh            # default localhost ports
#   FACTORY=http://host:9080 ./scripts/smoke_core.sh
#
# Exit non-zero if any REQUIRED surface is down. The Monitor universe can take a
# while to deploy its local chain, so it is polled with a longer, softer budget.
# ============================================================================
set -uo pipefail

FACTORY_API="${FACTORY_API:-http://localhost:9081}"
FACTORY_WEB="${FACTORY_WEB:-http://localhost:9080}"
HUB="${HUB:-http://localhost:9083}"
MESH="${MESH:-http://localhost:8090}"
MONITOR="${MONITOR:-http://localhost:9100}"
PROM="${PROM:-http://localhost:9090}"

pass=0; fail=0
check() { # label url required timeout
  local label="$1" url="$2" required="$3" timeout="${4:-5}"
  if curl -fsS -m "$timeout" "$url" >/dev/null 2>&1; then
    printf '  ✓ %s\n' "$label"; pass=$((pass+1)); return 0
  fi
  if [[ "$required" == "required" ]]; then
    printf '  ✗ %s  (%s)\n' "$label" "$url"; fail=$((fail+1))
  else
    printf '  ~ %s  (optional, not ready)\n' "$label"
  fi
  return 1
}

wait_for() { # label url timeout
  local label="$1" url="$2" budget="${3:-120}" start; start=$(date +%s)
  while true; do
    if curl -fsS -m 4 "$url" >/dev/null 2>&1; then check "$label" "$url" required 4; return 0; fi
    if [[ $(( $(date +%s) - start )) -ge "$budget" ]]; then check "$label" "$url" optional 4; return 1; fi
    sleep 3
  done
}

echo "== core smoke =="
check "Factory API"  "$FACTORY_API/api/health"                required
check "Factory web"  "$FACTORY_WEB/"                          required 8
check "Hub"          "$HUB/.well-known/ai-market.json"        required
check "Mesh API"     "$MESH/health"                           required
check "Prometheus"   "$PROM/prometheus/-/ready"               optional
wait_for "Monitor"   "$MONITOR/api/health"                    120

echo ""
echo "passed: $pass · failed: $fail"
[[ "$fail" -eq 0 ]] && { echo "core smoke OK"; exit 0; } || { echo "core smoke FAILED"; exit 1; }
