#!/usr/bin/env bash
# Deploy pipeline stage-inference UI fix into running aicom-app-1 without full image rebuild.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${AICOM_APP_CONTAINER:-aicom-app-1}"

echo "Building frontend…"
(cd "$ROOT/web/frontend" && npm run build)

echo "Replacing /app/web/frontend/.next in ${CONTAINER}…"
docker exec -u root "$CONTAINER" rm -rf /app/web/frontend/.next
docker cp "$ROOT/web/frontend/.next" "${CONTAINER}:/app/web/frontend/.next"
docker restart "$CONTAINER"
echo "Done. Open Admin → Pipeline and hard-refresh (Ctrl+Shift+R)."
