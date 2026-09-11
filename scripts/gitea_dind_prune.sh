#!/usr/bin/env bash
# Weekly prune of leftover images inside Gitea act_runner Docker-in-Docker.
#
# act_runner builds CI jobs inside `gitea-runner-dind` (a nested Docker daemon
# with its own /var/lib/docker volume). Those images are throwaway — they are
# not the host's production images — and they stay until something prunes them.
# One leftover reached 1.5 GB on the oracle/Gitea host.
#
# Isolated daemon: `docker system prune -af` here cannot touch host images.
# Do not add --volumes: a named volume a workflow still wants would go too.
set -euo pipefail

LOG="${GITEA_DIND_PRUNE_LOG:-/var/log/gitea-dind-prune.log}"
CONTAINER="${GITEA_DIND_CONTAINER:-gitea-runner-dind}"

{
  echo "=== $(date -Is) gitea dind prune ==="
  if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -qx true; then
    echo "skip: $CONTAINER is not running"
    exit 0
  fi
  docker exec "$CONTAINER" docker system df || true
  docker exec "$CONTAINER" docker system prune -af
  docker exec "$CONTAINER" docker system df || true
  echo "=== done ==="
} >>"$LOG" 2>&1
