#!/usr/bin/env bash
# Download-style deploy test: owner-export ZIP → extract → docker compose → smoke → teardown.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRODUCT_ID="${1:?usage: $0 <product-id>}"
API_PORT="${API_HOST_PORT:-18000}"
WEB_PORT="${WEB_HOST_PORT:-13000}"
PG_PORT="${POSTGRES_HOST_PORT:-15432}"
REDIS_PORT="${REDIS_HOST_PORT:-16379}"
DEPLOY="/tmp/aicom-product-deploy-${PRODUCT_ID}"
EXTRACT="/tmp/${PRODUCT_ID}-export"
ZIP="/tmp/${PRODUCT_ID}-owner-export.zip"
PROJECT="aicom-test-${PRODUCT_ID}"

cleanup() {
  echo "=== cleanup ==="
  if [[ -d "$DEPLOY" ]]; then
    (cd "$DEPLOY" && docker compose -p "$PROJECT" down -v --remove-orphans 2>/dev/null) || true
  fi
  rm -rf "$DEPLOY" "$EXTRACT" "$ZIP"
  docker exec aicom-app-1 bash -lc "rm -f /tmp/aicom-product-${PRODUCT_ID}-*.zip" 2>/dev/null || true
}
trap cleanup EXIT

echo "=== owner ZIP for $PRODUCT_ID ==="
docker exec aicom-app-1 bash -lc "cd /app && python3 -c \"
from pathlib import Path
import shutil
from web.backend.api.admin.dashboard.artifact_files import build_product_owner_export_zip
pid = '${PRODUCT_ID}'
zp, fn = build_product_owner_export_zip(pid, merged_pipeline_product=None)
out = Path('/tmp') / fn
shutil.copy2(zp, out)
print(out)
\""
ZIP_IN=$(docker exec aicom-app-1 bash -lc "ls -1 /tmp/aicom-product-${PRODUCT_ID}-*.zip | tail -1")
docker cp "aicom-app-1:${ZIP_IN}" "$ZIP"
rm -rf "$EXTRACT" "$DEPLOY"
mkdir -p "$EXTRACT"
unzip -q "$ZIP" -d "$EXTRACT"
cp -a "$EXTRACT/code" "$DEPLOY"

echo "=== docker compose up ($PROJECT) ==="
cd "$DEPLOY"
export API_HOST_PORT="$API_PORT" WEB_HOST_PORT="$WEB_PORT" POSTGRES_HOST_PORT="$PG_PORT" REDIS_HOST_PORT="$REDIS_PORT" SEED_DEMO=true
docker compose -p "$PROJECT" up -d --build postgres redis api web

echo "=== wait for API ==="
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "ERROR: API /health not ready on :${API_PORT}" >&2
  docker compose -p "$PROJECT" logs api --tail 40 >&2 || true
  exit 1
fi

echo "--- GET /health ---"
curl -sf "http://127.0.0.1:${API_PORT}/health" | python3 -m json.tool

echo "--- GET /docs status ---"
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${API_PORT}/docs"

echo "--- POST /api/auth/login (demo) ---"
LOGIN=$(curl -sf -X POST "http://127.0.0.1:${API_PORT}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@talenttailor.com","password":"demo1234"}') || LOGIN='{}'
echo "$LOGIN" | python3 -m json.tool 2>/dev/null || echo "$LOGIN"

TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token') or d.get('access_token',''))" 2>/dev/null || true)
if [[ -n "$TOKEN" ]]; then
  echo "--- GET /api/resumes/ (auth) ---"
  curl -sf "http://127.0.0.1:${API_PORT}/api/resumes/" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20
fi

echo "--- GET web :${WEB_PORT} ---"
curl -s -o /dev/null -w 'web %{http_code}\n' "http://127.0.0.1:${WEB_PORT}/"

echo "=== deploy smoke done ==="
