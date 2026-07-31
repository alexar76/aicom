#!/usr/bin/env bash
# Full ecosystem redeploy — Factory, Hub, Mesh, ARGUS, Alien Monitor (+ Pulse).
#
# Run from repo root. Hub MUST go through deploy_hub.sh (NOT docker compose from aimarket-hub/).
#
# Usage:
#   ./scripts/deploy_ecosystem.sh
#   ./scripts/deploy_ecosystem.sh --skip-verify
#   ./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_VERIFY=0
DEPLOY_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-verify) SKIP_VERIFY=1; shift ;;
    --public-url)
      DEPLOY_ARGS+=(--public-url "$2")
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [--skip-verify] [--public-url URL]"
      echo ""
      echo "Order: deploy.sh → deploy_hub.sh → deploy_mesh.sh → deploy_argus.sh"
      echo "       → deploy_alien_monitor.sh → deploy_lottery_uni.sh"
      echo "       → deploy_ecosystem_landing.sh → verify_ecosystem_full.sh"
      echo ""
      echo "Wrapper with preflight: ./scripts/quickstart_ecosystem.sh"
      echo "Do NOT use: cd aimarket-hub && docker compose up (breaks Hub on redeploy)."
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "=== Ecosystem full redeploy ==="
echo "Root: $ROOT"
echo ""

if [[ -x "$ROOT/scripts/ensure_deploy_satellites.sh" ]]; then
  echo "--- Pre-flight: satellite dirs for Docker COPY ---"
  "$ROOT/scripts/ensure_deploy_satellites.sh"
  echo ""
fi

if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "--- Pre-flight: docker network ecosystem ---"
  docker network create ecosystem
  echo ""
fi

if [[ -x "$ROOT/scripts/ecosystem_process_cleanup.sh" ]]; then
  echo "--- Pre-flight: host process cleanup ---"
  "$ROOT/scripts/ecosystem_process_cleanup.sh" --disk
  echo ""
fi

echo "--- 1/7 Factory (aicom-app) ---"
# Empty array is unbound under `set -u` on some bash builds — expand only if set.
"$ROOT/scripts/deploy.sh" ${DEPLOY_ARGS[@]+"${DEPLOY_ARGS[@]}"}

echo ""
echo "--- 2/7 Hub (modelmarket-hub :9083) — deploy_hub.sh only ---"
"$ROOT/scripts/deploy_hub.sh"

echo ""
echo "--- 3/7 Mesh (aicom-mesh-api :8090) ---"
"$ROOT/scripts/deploy_mesh.sh"

echo ""
echo "--- 4/7 ARGUS (reference agent :8787) ---"
"$ROOT/scripts/deploy_argus.sh"

echo ""
echo "--- 5/7 Alien Monitor + Pulse ---"
"$ROOT/scripts/deploy_alien_monitor.sh"

echo ""
echo "--- 6/7 UNI lottery relayer (live Monitor feed) ---"
"$ROOT/scripts/deploy_lottery_uni.sh" || echo "WARN: lottery relayer deploy failed — see logs"

echo ""
echo "--- 7/7 Ecosystem landing (modeldev.modelmarket.dev) ---"
if [[ -x "$ROOT/scripts/deploy_ecosystem_landing.sh" ]]; then
  "$ROOT/scripts/deploy_ecosystem_landing.sh" || echo "WARN: ecosystem landing deploy failed — see logs"
else
  echo "WARN: deploy_ecosystem_landing.sh missing — skip"
fi

echo ""
echo "--- Waiting for Factory API (:9081) ---"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:9081/api/health >/dev/null 2>&1; then
    echo "Factory API ready (${i}s)"
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "WARN: Factory API not ready after 30s — verify may fail" >&2
  fi
  sleep 1
done

# /api/health is instant; /api/products scans every product on disk (20–90s cold).
# Right after compose up the entrypoint may still restart the backend once (treasury guard).
# Retry warm-up so verify does not flake on funnel/admin checks that share the API process.
echo "--- Warming storefront catalog (GET /api/products) ---"
_warm_ok=0
for attempt in 1 5; do
  if curl -sf --max-time 120 "http://127.0.0.1:9081/api/products" >/dev/null; then
    echo "Storefront catalog warm (attempt ${attempt})"
    _warm_ok=1
    break
  fi
  echo "WARN: /api/products not ready (attempt ${attempt}/5) — backend may still be starting" >&2
  sleep 10
done
[[ "$_warm_ok" -eq 1 ]] || echo "WARN: storefront warm-up failed — run: docker compose restart app && ./scripts/verify_ecosystem_full.sh" >&2

for attempt in 1 3; do
  if curl -sf --max-time 60 "http://127.0.0.1:9081/api/marketing/trust-metrics" >/dev/null; then
    echo "Trust metrics warm"
    break
  fi
  [[ "$attempt" -lt 3 ]] && sleep 5
done || echo "WARN: trust-metrics warm-up slow — verify may retry" >&2

if [[ "$SKIP_VERIFY" -eq 0 ]]; then
  echo ""
  echo "--- Ecosystem verify (17+ checks) ---"
  "$ROOT/scripts/verify_ecosystem_full.sh"
fi

echo ""
echo "=== Ecosystem redeploy complete ==="
echo "  Factory:  http://127.0.0.1:9081"
echo "  Hub:      http://127.0.0.1:9083"
echo "  Mesh:     http://127.0.0.1:8090"
echo "  ARGUS:    http://127.0.0.1:8787/health"
echo "  Monitor:  https://magic-ai-factory.com/monitor/ (or :9100 local)"
echo "  Landing:  https://modeldev.modelmarket.dev/"
