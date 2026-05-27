#!/usr/bin/env bash
# Capture README screenshot for apps/pulse-terminal.
# Default: public /pulse/ (prod nginx strips prefix; bare :5199/ breaks /pulse/assets).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PULSE_SCREENSHOT_URL="${PULSE_SCREENSHOT_URL:-https://magic-ai-factory.com/pulse/}"

OUT="${ROOT}/apps/pulse-terminal/docs/screenshot.png"
mkdir -p "$(dirname "$OUT")"

npx --yes playwright@1.49.0 install chromium >/dev/null 2>&1 || true
npx --yes playwright@1.49.0 screenshot \
  --viewport-size=1400,900 \
  --wait-for-timeout=12000 \
  "${PULSE_SCREENSHOT_URL%/}/" \
  "$OUT"

# Reject blank captures (broken /pulse/assets on bare :5199/).
BYTES=$(wc -c <"$OUT" | tr -d ' ')
if [ "$BYTES" -lt 20000 ]; then
  echo "ERROR: screenshot too small (${BYTES} bytes) — use https://magic-ai-factory.com/pulse/" >&2
  exit 1
fi
echo "Wrote $OUT ($(du -h "$OUT" | awk '{print $1}'))"
