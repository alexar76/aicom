#!/usr/bin/env bash
# Prune old pipeline.db.bak.* snapshots (keeps newest N). Safe on running factory — only deletes backups.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${SQLITE_PATH:-$ROOT/data/state/pipeline.db}"
KEEP="${AIFACTORY_SQLITE_BACKUP_KEEP:-2}"
export SQLITE_PATH="$DB"
exec python3 -c "
from orchestrator.migrate import prune_old_sqlite_backups
from pathlib import Path
import os
db = os.environ.get('SQLITE_PATH', 'data/state/pipeline.db')
n = prune_old_sqlite_backups(db, keep=int(os.environ.get('AIFACTORY_SQLITE_BACKUP_KEEP', '2')))
print(f'Pruned {n} old backup(s); kept newest {os.environ.get(\"AIFACTORY_SQLITE_BACKUP_KEEP\", \"2\")} for {Path(db).name}')
"
