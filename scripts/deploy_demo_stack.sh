#!/usr/bin/env bash
# Demo stack on AI-Factory host: Hub (:9083) + Factory (:9081) + Prom (:9090) + Mesh (:8090) + Monitor (/monitor/).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Demo stack deploy ==="
echo "Prerequisites: Factory + Hub already running."
echo "Full redeploy: ./scripts/quickstart_ecosystem.sh or ./scripts/deploy_ecosystem.sh"

if ! curl -sf http://127.0.0.1:9083/.well-known/ai-market.json >/dev/null; then
  echo "WARN: Hub not on :9083 — run: $ROOT/scripts/deploy_hub.sh" >&2
fi
if ! curl -sf http://127.0.0.1:9081/api/health >/dev/null; then
  echo "WARN: Factory API not on :9081 — run: cd $ROOT && ./scripts/deploy.sh" >&2
fi

"$ROOT/scripts/deploy_mesh.sh"
"$ROOT/scripts/deploy_alien_monitor.sh"

echo ""
echo "=== Three monitor contours (UI: TEST | LIVE | UNI) ==="
echo "  LIVE (real)  — Hub + Mesh + Factory + Prom, real metrics (balance may be 0)"
echo "  UNI          — local chain + live layers + AI architect scenario (auto-starts on switch)"
echo "  TEST         — simulated mocks only"
echo ""
echo "  Monitor:  https://monitor.modelmarket.dev/"
echo "  Hub:      http://127.0.0.1:9083"
echo "  Mesh:     http://127.0.0.1:8090"
echo "  Factory:  http://127.0.0.1:9081"
