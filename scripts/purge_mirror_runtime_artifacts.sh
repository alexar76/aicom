#!/usr/bin/env bash
# Remove SQLite/runtime junk that must never ship in a public satellite mirror.
set -euo pipefail

clone="${1:-}"
[[ -n "$clone" && -d "$clone" ]] || {
  echo "usage: purge_mirror_runtime_artifacts.sh <clone-dir>" >&2
  exit 2
}

rm -f "$clone/:memory:" "$clone/:memory:-wal" "$clone/:memory:-shm"

find "$clone" -type f \( \
  -name '*.sqlite3' -o -name '*.sqlite3-wal' -o -name '*.sqlite3-shm' -o \
  -name 'channels.db' -o -name 'channels.db-wal' -o -name 'channels.db-shm' \
\) -delete 2>/dev/null || true
