"""Stream a consistent SQLite snapshot from the running Hub without exposing its contents."""

import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

key, default = ("AIMARKET_DB_PATH", "data/hub.db") if sys.argv[1] == "hub" else (
    "AIMARKET_CHANNELS_DB_PATH", "data/channels.db",
)
path = Path(os.environ.get(key) or default).resolve(strict=True)
with tempfile.TemporaryDirectory(prefix="publisher-custody-backup-") as temp:
    target = Path(temp) / "backup.db"
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    backup = sqlite3.connect(target)
    try:
        source.backup(backup)
        assert backup.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        backup.close()
        source.close()
    with target.open("rb") as stream:
        shutil.copyfileobj(stream, sys.stdout.buffer)
