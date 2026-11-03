# Read-only: how many tool-definition changes in a week touch only dates, version strings, numbers or whitespace.
import collections, json, re
from histor.config import load_settings
from histor.db import open_backend
START, END = "2026-10-25T00:00:00Z", "2026-11-01T00:00:00Z"
s = load_settings()
b = open_backend(s.db_path, s.database_url)
def canon(v, level):
    """level 0: whitespace; 1: + dates and timestamps; 2: + version strings; 3: + every number."""
    if isinstance(v, dict): return {k: canon(x, level) for k, x in v.items()}
    if isinstance(v, list): return [canon(x, level) for x in v]
    if isinstance(v, str):
        t = " ".join(v.split())
        if level >= 1: t = re.sub(r"\d{4}-\d{2}-\d{2}([T ][\d:.]+(Z|[+-]\d{2}:?\d{2})?)?", "<date>", t)
        if level >= 2: t = re.sub(r"\bv?\d+(\.\d+)+([-+][\w.]+)?\b", "<ver>", t)
        if level >= 3: t = re.sub(r"\d+", "<n>", t)
        return t
    if level >= 3 and isinstance(v, (int, float)) and not isinstance(v, bool): return "<n>"
    return v
with b.read() as tx:
    rows = tx.execute("SELECT c.target_id, c.observed_at, c.from_toolset, c.to_toolset, t.transport FROM changes c "
                      "JOIN targets t ON t.id = c.target_id WHERE c.observed_at >= ? AND c.observed_at < ? "
                      "AND c.from_toolset IS NOT NULL AND c.to_toolset IS NOT NULL", (START, END))
cache = {}
def blob(d):
    if d not in cache:
        with b.read() as tx:
            r = tx.one("SELECT body FROM blobs WHERE digest = ?", (d,))
        cache[d] = json.loads(r["body"]) if r else None
        if len(cache) > 64: cache.pop(next(iter(cache)))
    return cache[d]
kind = collections.Counter(); servers = collections.defaultdict(set); per_server = collections.Counter()
for r in rows:
    a, c = blob(r["from_toolset"]), blob(r["to_toolset"])
    if a is None or c is None: kind["missing blob"] += 1; continue
    ta = {t["name"]: t for t in a}; tc = {t["name"]: t for t in c}
    if set(ta) != set(tc): k = "tools added or removed"
    elif canon(ta, 0) == canon(tc, 0): k = "whitespace only"
    elif canon(ta, 1) == canon(tc, 1): k = "only dates or timestamps"
    elif canon(ta, 2) == canon(tc, 2): k = "only dates and version strings"
    elif canon(ta, 3) == canon(tc, 3): k = "only numbers (counts, limits, versions)"
    else: k = "wording or schema"
    kind[k] += 1; servers[k].add(r["target_id"])
    per_server[r["target_id"]] += 1
remote = sum(1 for r in rows if r["transport"] != "stdio")
print(json.dumps({"window": [START, END], "changes": len(rows), "remote": remote, "kinds": dict(kind.most_common()),
                  "serversByKind": {k: len(v) for k, v in servers.items()}, "servers": len(per_server),
                  "serversWith7plus": sum(1 for n in per_server.values() if n >= 7),
                  "changesFromThose": sum(n for n in per_server.values() if n >= 7)}, indent=1))
b.close()
