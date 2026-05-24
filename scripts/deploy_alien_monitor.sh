#!/usr/bin/env bash
# Deploy Alien Monitor on the AI-Factory host (nginx → /monitor/).
#
# Canonical source: alien-monitor/ in the aicom monorepo.
# GitHub mirror: https://github.com/alexar76/alien-monitor
#
# Usage (from monorepo root):
#   ./scripts/deploy_alien_monitor.sh
#   ./scripts/deploy_alien_monitor.sh --no-build
#   ./scripts/deploy_alien_monitor.sh --down
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR="$ROOT/alien-monitor"
COMPOSE=(docker compose -f "$MONITOR/docker-compose.prod.yml")
NO_BUILD=0
ACTION=up

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) NO_BUILD=1; shift ;;
    --down) ACTION=down; shift ;;
    -h|--help)
      sed -n '1,20p' "$0" | tail -n +2
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -d "$MONITOR" ]] || { echo "error: missing $MONITOR" >&2; exit 2; }
[[ -f "$MONITOR/docker-compose.prod.yml" ]] || { echo "error: missing docker-compose.prod.yml" >&2; exit 2; }

if [[ "$ACTION" == down ]]; then
  "${COMPOSE[@]}" down
  echo "OK alien-monitor stopped"
  exit 0
fi

if [[ "$NO_BUILD" -eq 0 ]]; then
  "${COMPOSE[@]}" up -d --build
else
  "${COMPOSE[@]}" up -d
fi

echo ""
echo "Alien Monitor: http://127.0.0.1:9100 (host network, LIVE mode)"
echo "Public (via nginx): https://magic-ai-factory.com/monitor/"
echo "Health: curl -s http://127.0.0.1:9100/api/health"
