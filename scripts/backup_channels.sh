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
