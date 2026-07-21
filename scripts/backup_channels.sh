#!/usr/bin/env bash
# Backup channels database with integrity check.
# Run via cron: */5 * * * * /app/scripts/backup_channels.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-data/backups}"
DB_PATH="${AIMARKET_CHANNELS_DB_PATH:-data/channels.db}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/channels_$TS.db"

# ── Integrity check ──────────────────────────────────────────────
if [ -f "$DB_PATH" ]; then
    INTEGRITY=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check" 2>&1)
    if [ "$INTEGRITY" != "ok" ]; then
        echo "FATAL: Database integrity check failed: $INTEGRITY" >&2
        if command -v python3 >/dev/null 2>&1; then
            MSG="🚨 channels.db integrity failed: ${INTEGRITY}"
            PYTHONPATH="${ROOT:-.}" python3 -c "
from web.backend.services.telegram_pipeline_notify import send_telegram_message_sync
send_telegram_message_sync('''${MSG}''')
" 2>/dev/null || echo "telegram notify skipped"
        fi
        exit 1
    fi
else
    echo "Database not found at $DB_PATH — skipping backup"
    exit 0
fi

# ── Backup ───────────────────────────────────────────────────────
sqlite3 "$DB_PATH" ".backup $BACKUP_FILE"
echo "Backup created: $BACKUP_FILE ($(stat -c%s "$BACKUP_FILE") bytes)"

# ── Cleanup old backups ──────────────────────────────────────────
find "$BACKUP_DIR" -name "channels_*.db" -mtime +"$RETENTION_DAYS" -delete

# ── Optional off-site copy (rclone) ───────────────────────────────
# Set BACKUP_RCLONE_REMOTE e.g. "b2:aicom-backups/channels" />
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
    if rclone copy "$BACKUP_FILE" "$BACKUP_RCLONE_REMOTE" --quiet; then
        echo "Off-site backup: $BACKUP_FILE → $BACKUP_RCLONE_REMOTE"
    else
        echo "WARN: rclone off-site copy failed for $BACKUP_FILE" >&2
    fi
fi
