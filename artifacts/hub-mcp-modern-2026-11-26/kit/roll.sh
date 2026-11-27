#!/usr/bin/env bash
# roll.sh CONTAINER NEW_TAG HEALTH_URLS(comma separated) — swap the container onto NEW_TAG with
# rollout_container.py (which restores the previous container if a health URL does not answer).
# No database backup: the change adds no migration and writes nothing new.
set -euo pipefail
C="$1"; NEW="$2"; HEALTH="$3"
D="$(cd "$(dirname "$0")" && pwd)"
ARGS=(); IFS=',' read -ra URLS <<< "$HEALTH"; for u in "${URLS[@]}"; do ARGS+=(--health "$u"); done
echo "previous image $(docker inspect -f '{{.Config.Image}}' "$C") $(docker inspect -f '{{.Image}}' "$C" | cut -c1-19)"
date -u +"switch %FT%TZ"
cd "$D" && python3 rollout_container.py "$C" --image "$NEW" "${ARGS[@]}"
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E "^$C\b|themis" || true
