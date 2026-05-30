#!/usr/bin/env bash
# Reclaim Docker disk (safe prune). Installed via cron — see scripts/install_disk_cleanup_cron.sh
#
# Also drops orphaned Foundry Anvil *tmp snapshots* under ~/.foundry/anvil/tmp/anvil-state-*.
# Live UNI chain state is NOT touched: data/alien-monitor/universe/anvil-state (bind mount).
set -euo pipefail
LOG="${DISK_CLEANUP_LOG:-/var/log/aicom-disk-cleanup.log}"

_cleanup_orphan_anvil_snapshots() {
  # Host: stale anvil-state-* dirs (can grow to tens of GB; not used when --state points elsewhere).
  local tmp_root="${FOUNDRY_ANVIL_TMP:-/root/.foundry/anvil/tmp}"
  if [ -d "$tmp_root" ]; then
    local n=0
    shopt -s nullglob
    for stale in "$tmp_root"/anvil-state-*; do
      [ -e "$stale" ] || continue
      echo "removing host orphan anvil snapshot: $stale"
      du -sh "$stale" 2>/dev/null || true
      rm -rf "$stale"
      n=$((n + 1))
    done
    shopt -u nullglob
    echo "host anvil tmp snapshots removed: $n"
  fi

  # alien-monitor container: same pattern inside /root/.foundry (writable layer bloat).
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'alien-monitor'; then
    docker exec alien-monitor sh -c '
      set -e
      tmp=/root/.foundry/anvil/tmp
      [ -d "$tmp" ] || exit 0
      n=0
      for stale in "$tmp"/anvil-state-*; do
        [ -e "$stale" ] || continue
        echo "removing container orphan anvil snapshot: $stale"
        du -sh "$stale" 2>/dev/null || true
        rm -rf "$stale"
        n=$((n + 1))
      done
      echo "container anvil tmp snapshots removed: $n"
    ' 2>&1 || true
  fi
}

{
  echo "=== $(date -Is) disk cleanup ==="
  df -h / | tail -1
  _cleanup_orphan_anvil_snapshots
  docker builder prune -af 2>&1 || true
  docker system prune -af 2>&1 || true
  df -h / | tail -1
} >>"$LOG" 2>&1
