#!/usr/bin/env bash
# Reset pipeline data, clear logs, turn off autonomous pipeline, enqueue one complex SKU, restart.
# Run from repo root:  ./scripts/run_factory_demo_reset.sh
# Requires: docker compose v2, running Docker, project .env with API keys as needed.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="${COMPOSE:-docker compose}"

echo "==> Build & start app (embeds latest scripts)"
$COMPOSE build app
$COMPOSE up -d app

echo "==> Wipe pipeline + artifacts + logs + dashboard commerce/benchmark files (zeros in admin)"
$COMPOSE exec -T app python /app/scripts/wipe_pipeline_products.py \
  --db /app/data/state/pipeline.db \
  --yes --also-artifacts --zero-dashboard

echo "==> Disable autonomous pipeline (general.auto_pipeline in /app/config.yaml)"
$COMPOSE exec -T app env AUTO_PIPELINE_VALUE=0 python /app/scripts/set_auto_pipeline.py

echo "==> Enqueue one complex full_software product (FleetMind Ops demo brief)"
$COMPOSE exec -T app python /app/scripts/enqueue_single_complex_product.py

echo "==> Restart app (reload Director config + pipeline worker)"
$COMPOSE restart app

echo ""
echo "Done. Open Admin → Pipeline Monitor (sort: shipped first) and watch the single product."
echo "Tip: to stop Discovery auto-enqueue, add AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0 to .env and recreate the app service."
