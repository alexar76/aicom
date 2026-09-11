#!/usr/bin/env bash
# Hot-patch running aicom-app-1 with Admin Files API fix (artifact_files module).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${AICOM_APP_CONTAINER:-aicom-app-1}"
for f in \
  web/backend/api/admin/dashboard/artifact_files.py \
  web/backend/api/admin/dashboard/routes_products.py \
  web/backend/api/admin/dashboard/routes_pipeline.py \
  web/backend/services/product_pulse.py \
  web/backend/core/security.py; do
  docker cp "$ROOT/$f" "$CONTAINER:/app/$f"
done
docker restart "$CONTAINER"
echo "Hotfix applied to $CONTAINER — verify: curl -H \"Authorization: Bearer …\" /api/admin/products/prod-demo-landing-studio/files"
