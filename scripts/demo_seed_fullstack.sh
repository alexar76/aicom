#!/usr/bin/env bash
# Enqueue a **full_software** SaaS demo, wait for pipeline completion, optionally run seed script, open product page.
#
# Usage:
#   ./scripts/demo_seed_fullstack.sh [--no-open]
#
# Requires: Docker stack up (same as demo.sh), curl, python3; jq optional.
# Env:
#   DEMO_BASE_URL              default picks healthy :9080 / :8080
#   DEMO_ADMIN_PASSWORD        default admin123
#   DEMO_SEED_IDEA             product brief (default: remote teams SaaS)
#   DEMO_CONTAINER_NAME        default ai-factory (see demo.sh)
#
set -euo pipefail

OPEN_BROWSER=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-open) OPEN_BROWSER=0; shift ;;
    *) shift ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

IDEA="${DEMO_SEED_IDEA:-SaaS for remote teams — JWT auth, dashboard with charts, tasks table CRUD, SQLite or Postgres, settings page}"
PROFILE="full_software"

pick_base() {
  if [[ -n "${DEMO_BASE_URL:-}" ]]; then
    echo "${DEMO_BASE_URL}"
    return 0
  fi
  for cand in http://localhost:9080 http://localhost:8080; do
    if curl -sf "${cand}/api/health" >/dev/null 2>&1; then
      echo "${cand}"
      return 0
    fi
  done
  return 1
}

echo "[demo-seed] Waiting for API..."
BASE=""
for _ in $(seq 1 90); do
  if BASE="$(pick_base || true)" && [[ -n "${BASE}" ]]; then
    break
  fi
  sleep 2
done
[[ -n "${BASE:-}" ]] || { echo "[demo-seed] No healthy API — set DEMO_BASE_URL"; exit 1; }
echo "[demo-seed] Using ${BASE}"

PASS="${DEMO_ADMIN_PASSWORD:-admin123}"
login_json="$(curl -sS -X POST "${BASE}/api/admin/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"${PASS}\"}")"

if command -v jq >/dev/null 2>&1; then
  TOKEN="$(echo "${login_json}" | jq -r '.access_token // empty')"
else
  TOKEN="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('access_token') or '')" <<<"${login_json}")"
fi
[[ -n "${TOKEN}" ]] || { echo "[demo-seed] Admin login failed"; echo "${login_json}" | head -c 400; exit 1; }

payload="$(python3 -c "
import json, sys
print(json.dumps({'idea': sys.argv[1], 'delivery_profile': sys.argv[2]}))
" "${IDEA}" "${PROFILE}")"

create_json="$(curl -sS -X POST "${BASE}/api/admin/products/create" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d "${payload}")"

if command -v jq >/dev/null 2>&1; then
  PID="$(echo "${create_json}" | jq -r '.product_id // empty')"
else
  PID="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('product_id') or '')" <<<"${create_json}")"
fi
[[ -n "${PID}" ]] || { echo "[create failed] ${create_json}"; exit 1; }

echo "[demo-seed] Created ${PID} — waiting for pipeline (this can take 15–60+ min)..."
export ADMIN_TOKEN="${TOKEN}"
export TOKEN="${TOKEN}"
if ! python3 "${ROOT}/scripts/wait_pipeline_product.py" --base "${BASE}" --token "${TOKEN}" --product-id "${PID}" --timeout 7200; then
  echo "[demo-seed] Pipeline wait ended with error — check Admin → Pipeline"
  exit 1
fi

DATA_ROOT="${DATA_ROOT:-${ROOT}/data}"
if [[ -d "${DATA_ROOT}" ]]; then
  python3 "${ROOT}/scripts/seed_generated_demo_optional.py" --product-id "${PID}" --data-root "${DATA_ROOT}" || true
fi

PROD_URL="${BASE}/product/${PID}"
echo ""
echo "[demo-seed] Product page: ${PROD_URL}"

if [[ "${OPEN_BROWSER}" == "1" ]]; then
  case "$(uname -s)" in
    Darwin) open "${PROD_URL}" ;;
    MINGW*|CYGWIN*|MSYS*) start "${PROD_URL}" ;;
    *) xdg-open "${PROD_URL}" 2>/dev/null || sensible-browser "${PROD_URL}" 2>/dev/null || true ;;
  esac
fi
