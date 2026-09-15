#!/usr/bin/env bash
# ============================================================================
# AI-Factory — reproducible quickstart (clone → one command → running demo)
# ============================================================================
# Usage:
#   ./scripts/quickstart.sh                    # build + run + landing demo idea
#   ./scripts/quickstart.sh --no-build         # reuse existing image
#   ./scripts/quickstart.sh "Your product idea" # full_software profile
#
# After start, open Admin → Pipeline. Sample output without running anything:
#   docs/sample-output/build-replay-spliteasy.json
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD=1
IDEA=""
PROFILE="marketing_landing"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=0; shift ;;
    --full-stack|--full) PROFILE="full_software"; shift ;;
    --landing) PROFILE="marketing_landing"; shift ;;
    -h|--help)
      sed -n '1,20p' "$0" | tail -n +2
      exit 0
      ;;
    *) IDEA="$1"; PROFILE="full_software"; shift ;;
  esac
done

if [[ "$BUILD" -eq 1 ]]; then
  echo "[quickstart] Building Docker image (first run may take several minutes)…"
  ./run.sh
else
  ./run.sh --no-build
fi

DEMO_ARGS=(--no-open)
if [[ "$PROFILE" == "marketing_landing" ]]; then
  DEMO_ARGS+=(--landing)
fi
if [[ -n "$IDEA" ]]; then
  DEMO_ARGS+=("$IDEA")
fi

echo "[quickstart] Enqueueing demo product (profile=${PROFILE})…"
./demo.sh "${DEMO_ARGS[@]}"

echo ""
echo "[quickstart] Done. Watch progress in Admin → Pipeline."
echo "  Sample build replay (no Docker): docs/sample-output/build-replay-spliteasy.json"
echo "  Public replay API shape: GET /api/public/build/{product_id}"
