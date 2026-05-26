#!/usr/bin/env bash
# Capture README screenshot for apps/pulse-terminal (requires Pulse UI on :5199).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/apps/pulse-terminal/docs/screenshot.png"
URL="${PULSE_SCREENSHOT_URL:-http://127.0.0.1:9080/pulse/}"

mkdir -p "$(dirname "$OUT")"
cd "${ROOT}/apps/pulse-terminal"
npx --yes playwright@1.49.0 screenshot \
  --viewport-size=1400,900 \
  --wait-for-timeout=5000 \
  "$URL" \
  "$OUT"
echo "Wrote $OUT"
