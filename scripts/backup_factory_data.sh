#!/usr/bin/env bash
# Full backup of the AI-Factory data bind mount (host-side).
# Prefer this for large instances; Admin → Settings also offers a ZIP download.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${AIFACTORY_DATA_ROOT:-$ROOT/data}"
PARENT="$(dirname "$DATA")"
BASE="$(basename "$DATA")"

if [[ ! -d "$DATA" ]]; then
  echo "Data directory not found: $DATA" >&2
  exit 1
fi

OUT="${1:-aicom-factory-backup-$(date -u +%Y%m%dT%H%M%SZ).tar.gz}"
echo "Archiving $DATA → $OUT"
tar -czf "$OUT" -C "$PARENT" "$BASE"
echo "Done. Size: $(du -h "$OUT" | cut -f1)"
echo "Restore: stop containers, extract over $DATA, restart app."
