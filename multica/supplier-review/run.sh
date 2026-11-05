#!/bin/sh
# Fetch what modelmarket.dev publishes about its sellers and run review.mjs over it.
# Run by the Multica agent «ревьюер поставщиков» once per task. curl goes through the agent's
# egress proxy (HTTPS_PROXY); review.mjs itself opens no socket. Prints the summary line and
# the path of this run's report.md / report.json.
set -eu
HUB="${SUPPLIER_REVIEW_HUB:-https://modelmarket.dev}"
HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${SUPPLIER_REVIEW_STATE:-$HOME/.local/state/supplier-review}"
WARDEN_DIR="${WARDEN_PACKAGE:-$HOME/tools/warden}"
RUN="$STATE_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$RUN"

fetch() {
  curl -fsS --max-time 90 -A 'aicom-supplier-review/1 (+https://modelmarket.dev/developers)' -o "$RUN/$1" "$HUB$2"
}
fetch manifest.json /ai-market/v2/manifest
fetch peers.json /ai-market/v2/federation/peers
fetch observed.json /ai-market/v2/federation/observed-sellers

node "$HERE/review.mjs" \
  --manifest "$RUN/manifest.json" --peers "$RUN/peers.json" --observed "$RUN/observed.json" \
  --state "$STATE_DIR/state.json" --out "$RUN/report.json" --md "$RUN/report.md" --warden "$WARDEN_DIR"
echo "report: $RUN/report.md"
echo "data: $RUN/report.json"

# Keep the last 30 runs.
ls -1d "$STATE_DIR"/runs/*/ 2>/dev/null | sort | head -n -30 | while read -r old; do rm -rf "$old"; done
