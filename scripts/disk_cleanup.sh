#!/usr/bin/env bash
# Reclaim Docker disk (safe prune). Installed via cron — see scripts/install_disk_cleanup_cron.sh
set -euo pipefail
LOG="${DISK_CLEANUP_LOG:-/var/log/aicom-disk-cleanup.log}"
{
  echo "=== $(date -Is) disk cleanup ==="
  df -h / | tail -1
  docker builder prune -af 2>&1 || true
  docker system prune -af 2>&1 || true
  df -h / | tail -1
} >>"$LOG" 2>&1
