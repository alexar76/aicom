#!/usr/bin/env bash
# Smoke-test running AI-Factory stack (health, public API, admin API).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT="${ROOT}/data/reports/smoke_stack_$(date +%Y%m%d_%H%M%S).md"
mkdir -p "$(dirname "$REPORT")"

FRONT="${AICOM_PORT_FRONTEND:-9080}"
API="${AICOM_PORT_API:-9081}"
PROM="${AICOM_PORT_PROMETHEUS:-9090}"
GRAF="${AICOM_PORT_GRAFANA:-9082}"

PASS=0
FAIL=0
SKIP=0

log() { echo "$*" | tee -a "$REPORT"; }
check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    log "- [x] **$name**"
    PASS=$((PASS + 1))
    return 0
  else
    log "- [ ] **$name** — FAILED"
    FAIL=$((FAIL + 1))
    return 1
  fi
}

check_json_field() {
  local name="$1" url="$2" py_expr="$3"
  if python3 -c "
import json, urllib.request, sys
r = urllib.request.urlopen('$url', timeout=15)
d = json.load(r)
sys.exit(0 if ($py_expr) else 1)
" 2>/dev/null; then
    log "- [x] **$name**"
    PASS=$((PASS + 1))
  else
    log "- [ ] **$name** — FAILED"
    FAIL=$((FAIL + 1))
  fi
}

TOKEN="$(docker exec aicom-app-1 python3 -c "
from web.backend.core.security import SecurityManager
print(SecurityManager().create_access_token('admin', role='admin'))
" 2>/dev/null || true)"

{
  echo "# AI-Factory stack smoke report"
  echo ""
  echo "Generated: $(date -Is)"
  echo ""
  echo "## Infrastructure"
} >"$REPORT"

check "Docker app container healthy" docker inspect -f '{{.State.Health.Status}}' aicom-app-1
check "API /api/health" curl -fsS "http://127.0.0.1:${API}/api/health"
check "Frontend / (200)" curl -fsS -o /dev/null -w '' "http://127.0.0.1:${FRONT}/"
check "Admin login page" curl -fsS -o /dev/null "http://127.0.0.1:${FRONT}/admin/login"
check "Prometheus ready" curl -fsS "http://127.0.0.1:${PROM}/-/ready"
check "Grafana health" curl -fsS "http://127.0.0.1:${GRAF}/api/health"

log ""
log "## Public API"
check_json_field "GET /api/public/pipeline-status" "http://127.0.0.1:${API}/api/public/pipeline-status" "isinstance(d, dict)"
check_json_field "GET /api/public/ecosystem-status" "http://127.0.0.1:${API}/api/public/ecosystem-status" "'hub' in d and 'slo' in d"
check_json_field "GET /api/products/categories" "http://127.0.0.1:${API}/api/products/categories" "isinstance(d, (dict, list))"

log ""
log "## Admin API (Bearer)"
if [[ -n "$TOKEN" ]]; then
  AUTH=( -H "Authorization: Bearer $TOKEN" )
  check "GET /api/admin/dashboard/pipeline-summary" curl -fsS "${AUTH[@]}" "http://127.0.0.1:${API}/api/admin/dashboard/pipeline-summary"
  check "GET /api/admin/dashboard?quick=1" curl -fsS "${AUTH[@]}" "http://127.0.0.1:${API}/api/admin/dashboard?quick=1"
  check "GET /api/admin/dashboard (full)" curl -fsS "${AUTH[@]}" "http://127.0.0.1:${API}/api/admin/dashboard"
  check "GET /api/admin/wow/prompts/proposals" curl -fsS "${AUTH[@]}" "http://127.0.0.1:${API}/api/admin/wow/prompts/proposals"
  check "POST /api/admin/wow/prompts/analyze" curl -fsS -X POST "${AUTH[@]}" "http://127.0.0.1:${API}/api/admin/wow/prompts/analyze"
else
  log "- [~] Admin API checks skipped (no token)"
  SKIP=$((SKIP + 1))
fi

log ""
log "## Summary"
log "| Result | Count |"
log "|--------|-------|"
log "| Pass   | $PASS |"
log "| Fail   | $FAIL |"
log "| Skip   | $SKIP |"

echo ""
echo "Report: $REPORT"
exit $([[ "$FAIL" -eq 0 ]] && echo 0 || echo 1)
