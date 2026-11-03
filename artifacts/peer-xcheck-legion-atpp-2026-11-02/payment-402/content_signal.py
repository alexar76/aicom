import re, collections
from histor.config import load_settings
from histor.db import open_backend
s = load_settings(); db = open_backend(s.db_path, s.database_url)
try:
    with db.read() as tx:
        rows = tx.execute("SELECT origin, body FROM robots_txt WHERE kind = 'ok' AND body IS NOT NULL")
finally:
    db.close()
c = collections.Counter(); no_train = []
for r in rows:
    sig = re.findall(r"(?im)^\s*content-signal\s*:\s*(.+)$", r["body"] or "")
    if not sig: continue
    c["with content-signal"] += 1
    vals = {}
    for line in sig:
        for part in line.split(","):
            if "=" in part:
                k, v = part.split("=", 1); vals.setdefault(k.strip().lower(), set()).add(v.strip().lower())
    for k in ("search", "ai-input", "ai-train"):
        if "no" in vals.get(k, ()): c[k + "=no"] += 1
print("robots.txt files read ok:", len(rows), dict(c))
