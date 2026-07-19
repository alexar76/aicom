#!/usr/bin/env bash
# Smoke all Argus feature surfaces after redeploy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARGUS_LIVE="${ARGUS_URL:-http://127.0.0.1:8787}"
ARGUS_UNI="${ARGUS_UNI_URL:-http://127.0.0.1:8788}"
PUBLIC_ARENA="${ARGUS_PUBLIC_ARENA:-https://magic-ai-factory.com/arena}"
PUBLIC_ARENA_UNI="${ARGUS_PUBLIC_ARENA_UNI:-https://magic-ai-factory.com/arena-uni}"

PASS=0
FAIL=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name" >&2
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Argus feature smoke ==="

# Unit tests (keystore PQC, warden, verify, lumen, budget, native, …)
if (cd "$ROOT/argus" && npm test); then
  echo "PASS  argus npm test (all vitest suites)"
  PASS=$((PASS + 1))
else
  echo "FAIL  argus npm test" >&2
  FAIL=$((FAIL + 1))
fi

# LIVE node
check "LIVE /health" curl -sf --max-time 10 "$ARGUS_LIVE/health"
check "LIVE /arena/stats" bash -c "curl -sf --max-time 10 '$ARGUS_LIVE/arena/stats' | python3 -c \"import json,sys; d=json.load(sys.stdin); assert 'mode' in d or 'stats' in d or isinstance(d, dict)\""

# UNI node
check "UNI /health" curl -sf --max-time 10 "$ARGUS_UNI/health"
check "UNI /arena/stats" bash -c "curl -sf --max-time 10 '$ARGUS_UNI/arena/stats' | python3 -c \"import json,sys; json.load(sys.stdin)\""

# Public nginx (optional — may fail offline)
if curl -sf --max-time 15 "$PUBLIC_ARENA/stats" >/dev/null 2>&1 || curl -sf --max-time 15 "${PUBLIC_ARENA%/}/stats" >/dev/null 2>&1; then
  echo "PASS  public LIVE arena"
  PASS=$((PASS + 1))
else
  echo "WARN  public LIVE arena unreachable (nginx?) — skipping"
fi
if curl -sf --max-time 15 "$PUBLIC_ARENA_UNI/stats" >/dev/null 2>&1 || curl -sf --max-time 15 "${PUBLIC_ARENA_UNI%/}/stats" >/dev/null 2>&1; then
  echo "PASS  public UNI arena"
  PASS=$((PASS + 1))
else
  echo "WARN  public UNI arena unreachable (nginx?) — skipping"
fi

echo ""
echo "=== Argus smoke: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
