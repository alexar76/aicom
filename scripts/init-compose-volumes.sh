#!/bin/bash
# Prepare host bind-mount directories and ownership for Docker Compose.
# Prometheus image runs as uid 65534 (nobody), Grafana as 472.
# Run from project root: ./scripts/init-compose-volumes.sh
# On production, run once with sudo if ./data is not yet owned by these ids.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/data"

mkdir -p "$DATA/prometheus" "$DATA/grafana" "$DATA/store/downloads" \
  "$DATA/config" "$DATA/state" "$DATA/secrets" "$DATA/logs"

if [[ "${EUID:-0}" -eq 0 ]]; then
  chown -R 65534:65534 "$DATA/prometheus"
  chown -R 472:472 "$DATA/grafana"
  chmod 700 "$DATA/secrets" 2>/dev/null || true
  echo "✓ Volume permissions set (prometheus:65534, grafana:472)"
else
  echo "⚠ Not root: if Prometheus/Grafana fail with 'permission denied', run:"
  echo "  sudo $0"
fi
