#!/usr/bin/env bash
# Reclaim Docker disk (safe prune). Installed via cron — see scripts/install_disk_cleanup_cron.sh
#
# Also drops orphaned Foundry Anvil *tmp snapshots* under ~/.foundry/anvil/tmp/anvil-state-*.
# Live chain state is NOT touched: data/alien-monitor/universe/anvil-state (bind mount).
set -euo pipefail
LOG="${DISK_CLEANUP_LOG:-/var/log/aicom-disk-cleanup.log}"

_cleanup_orphan_anvil_in_container() {
  local c="$1"
  docker exec "$c" sh -c '
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
}

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

  # Any running container with Foundry anvil tmp (alien-monitor, ailottery-chain-1, etc.).
  local c
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    docker exec "$c" test -d /root/.foundry/anvil/tmp 2>/dev/null || continue
    echo "scanning container $c for orphan anvil snapshots"
    _cleanup_orphan_anvil_in_container "$c"
  done < <(docker ps --format '{{.Names}}' 2>/dev/null || true)
}

_cleanup_git_bundles() {
  shopt -s nullglob
  local f
  for f in /tmp/aicom*.bundle /tmp/*.bundle; do
    [ -e "$f" ] || continue
    echo "removing git bundle: $f"
    du -sh "$f" 2>/dev/null || true
    rm -f "$f"
  done
  shopt -u nullglob
}

_cleanup_tmp_product_exports() {
  shopt -s nullglob
  local p
  for p in /tmp/prod-*-export /tmp/prod-*-export.zip /tmp/prod-*-owner-export.zip; do
    [ -e "$p" ] || continue
    echo "removing temp product export: $p"
    du -sh "$p" 2>/dev/null || true
    rm -rf "$p"
  done
  shopt -u nullglob
}

_cleanup_pipeline_db_backups() {
  local root="${AICOM_ROOT:-/root/claudecode/aicom}"
  local script="$root/scripts/prune_pipeline_db_backups.sh"
  local db="$root/data/state/pipeline.db"
  [ -f "$db" ] || return 0

  if [ -x "$script" ] && python3 -c "import orchestrator" 2>/dev/null; then
    AIFACTORY_SQLITE_BACKUP_KEEP="${AIFACTORY_SQLITE_BACKUP_KEEP:-2}" "$script" 2>&1 || true
    return 0
  fi

  # Factory host: orchestrator lives in the app container, not on the host Python.
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'aicom-app-1'; then
    docker exec aicom-app-1 python3 -c "
from orchestrator.migrate import prune_old_sqlite_backups
from core.paths import pipeline_db_path
import os
keep = int(os.environ.get('AIFACTORY_SQLITE_BACKUP_KEEP', '2'))
n = prune_old_sqlite_backups(str(pipeline_db_path()), keep=keep)
print(f'Pruned {n} pipeline.db backup(s); keep={keep}')
" 2>&1 || true
  fi
}

{
  echo "=== $(date -Is) disk cleanup ==="
  df -h / | tail -1
  _cleanup_orphan_anvil_snapshots
  _cleanup_git_bundles
  _cleanup_tmp_product_exports
  _cleanup_pipeline_db_backups
  docker builder prune -af 2>&1 || true
  docker system prune -af 2>&1 || true
  df -h / | tail -1
} >>"$LOG" 2>&1
