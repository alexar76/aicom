#!/usr/bin/env bash
# Install safe aicom cleanup every 4 hours and daily at 03:00.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLEAN="$ROOT/scripts/disk_cleanup.sh"
chmod +x "$CLEAN"
MARK="# aicom-disk-cleanup"
TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARK" | grep -v "$CLEAN" | grep -vE '^0 3 \* \* \* docker system prune -af --volumes > /tmp/docker-cleanup\.log 2>&1 # OpenClaw$' >"$TMP" || true
{
  cat "$TMP"
  echo "0 3 * * * $CLEAN $MARK-daily"
  echo "0 */4 * * * $CLEAN $MARK"
} | crontab -
rm -f "$TMP"
echo "Installed cron (every 4h): $CLEAN"
crontab -l | grep -E 'disk_cleanup|docker system prune' || true
