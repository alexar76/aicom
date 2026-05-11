#!/usr/bin/env bash
# ============================================================================
# AI-Factory — one-command demo (Docker + enqueue product + open admin)
# ============================================================================
# Prerequisites: Docker, curl, jq OR python3; image/container from ./run.sh
#
# Usage:
#   ./demo.sh [--landing] [--no-open] [--compose] "your idea here"
#
#   --landing        brochure/marketing_landing only (faster). Default profile is full_software.
#   --no-open        do not open a browser
#   --compose        force DEMO_BASE_URL=http://localhost:9080 (Compose UI port)
#
# Environment:
#   DEMO_BASE_URL       e.g. http://localhost:8080 (default: auto 8080 then 9080)
#   DEMO_ADMIN_PASSWORD admin password (default: admin123)
#   DEMO_CONTAINER_NAME container name to wait on (default: ai-factory)
# ============================================================================
set -euo pipefail

PROFILE="full_software"
OPEN_BROWSER=1
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --landing) PROFILE="marketing_landing"; shift ;;
    --full-stack) PROFILE="full_software"; shift ;; # backward compatible alias
    --no-open) OPEN_BROWSER=0; shift ;;
    --compose) export DEMO_BASE_URL="${DEMO_BASE_URL:-http://localhost:9080}"; shift ;;
    -h|--help)
      sed -n '1,25p' "$0" | tail -n +2
      exit 0
      ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

IDEA="${POSITIONAL[*]:-}"
if [[ -z "${IDEA// }" ]]; then
  IDEA="Landing page for AI-powered resume builder"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

CNAME="${DEMO_CONTAINER_NAME:-ai-factory}"

if ! docker ps --format '{{.Names}}' | grep -qx "${CNAME}"; then
  if docker ps -a --format '{{.Names}}' | grep -qx "${CNAME}"; then
    echo "[demo] Starting container ${CNAME}..."
    docker start "${CNAME}" >/dev/null
  else
    echo "[demo] No container '${CNAME}'. Launching via ./run.sh --no-build ..."
    if [[ -x ./run.sh ]]; then
      ./run.sh --no-build || {
        echo "[demo] run.sh failed — build first: ./run.sh"
        exit 1
      }
    else
      echo "[demo] ./run.sh not found or not executable."
      exit 1
    fi
  fi
fi

pick_base() {
  if [[ -n "${DEMO_BASE_URL:-}" ]]; then
    echo "${DEMO_BASE_URL}"
    return 0
  fi
  for cand in http://localhost:8080 http://localhost:9080; do
    if curl -sf "${cand}/api/health" >/dev/null 2>&1; then
      echo "${cand}"
      return 0
    fi
  done
  return 1
}

echo "[demo] Waiting for API health..."
BASE=""
for _ in $(seq 1 90); do
  if BASE="$(pick_base || true)" && [[ -n "${BASE}" ]]; then
    break
  fi
  sleep 2
done
if [[ -z "${BASE:-}" ]]; then
  echo "[demo] Timeout: set DEMO_BASE_URL (e.g. http://localhost:8080)"
  exit 1
fi
echo "[demo] Using API base: ${BASE}"

PASS="${DEMO_ADMIN_PASSWORD:-admin123}"

login_json="$(curl -sS -X POST "${BASE}/api/admin/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"${PASS}\"}")"

if command -v jq >/dev/null 2>&1; then
  TOKEN="$(echo "${login_json}" | jq -r '.access_token // empty')"
else
  TOKEN="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('access_token') or '')" <<<"${login_json}")"
fi

if [[ -z "${TOKEN}" ]]; then
  echo "[demo] Login failed (wrong password or 2FA enabled?). Response:"
  echo "${login_json}" | head -c 400
  echo ""
  exit 1
fi

payload="$(python3 -c "
import json, sys
idea = sys.argv[1]
prof = sys.argv[2]
print(json.dumps({'idea': idea, 'delivery_profile': prof}))
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

if [[ -z "${PID}" ]]; then
  echo "[demo] Create product failed:"
  echo "${create_json}" | head -c 600
  echo ""
  exit 1
fi

echo "[demo] Created ${PID} (profile=${PROFILE})"
echo "[demo] Idea: ${IDEA}"

TAB_URL="${BASE}/admin?tab=pipeline"
PROD_URL="${BASE}/product/${PID}"

if [[ "${OPEN_BROWSER}" == "1" ]]; then
  echo "[demo] Opening Pipeline tab…"
  case "$(uname -s)" in
    Darwin) open "${TAB_URL}" ;;
    MINGW*|CYGWIN*|MSYS*) start "${TAB_URL}" ;;
    *) xdg-open "${TAB_URL}" 2>/dev/null || sensible-browser "${TAB_URL}" 2>/dev/null || true ;;
  esac
fi

echo ""
echo "  Pipeline (admin): ${TAB_URL}"
echo "  Product page:     ${PROD_URL}"
echo ""
echo "[demo] Full pipeline takes several minutes — watch tasks in Admin → Pipeline."
