#!/usr/bin/env bash
# Install aicom disk cleanup cron (every 4 hours) + keep daily OpenClaw prune at 03:00.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLEAN="$ROOT/scripts/disk_cleanup.sh"
chmod +x "$CLEAN"
MARK="# aicom-disk-cleanup"
TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARK" | grep -v "$CLEAN" >"$TMP" || true
{
  cat "$TMP"
  echo "0 3 * * * docker system prune -af --volumes > /tmp/docker-cleanup.log 2>&1 # OpenClaw"
  echo "0 */4 * * * $CLEAN $MARK"
} | crontab -
echo "Installed cron (every 4h): $CLEAN"
crontab -l | grep -E 'disk_cleanup|docker system prune' || true
