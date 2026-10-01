#!/usr/bin/env bash
# Run Slither on all in-repo EVM contract trees + emit markdown summary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORT="$ROOT/contracts/audits/slither-summary-$(date +%Y%m%d).md"
mkdir -p "$(dirname "$REPORT")"

if ! command -v slither >/dev/null 2>&1; then
  pip install slither-analyzer==0.10.4
fi

{
  echo "# Slither summary — $(date -Iseconds)"
  echo ""
  for dir in contracts/evm acex/contracts/evm; do
    if [[ ! -d "$ROOT/$dir" ]]; then
      echo "## $dir — skipped (not present)"
      echo ""
      continue
    fi
    echo "## $dir"
    echo '```'
    (cd "$ROOT/$dir" && make install OZ_VERSION=v5.0.2 2>/dev/null || true)
    (cd "$ROOT/$dir" && slither . --config-file slither.config.json --fail-high 2>&1) || true
    echo '```'
    echo ""
  done
  echo "---"
  echo "External audit disposition: see [audit-response.md](./audit-response.md)"
} | tee "$REPORT"

echo "Wrote $REPORT"
