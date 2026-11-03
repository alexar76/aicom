# Read-only: examples behind cachechurn.py's "only dates or timestamps" and "only dates and version strings"
# changes (same week): per server, how often, which fields moved, a before/after snippet, and the tool list size.
import collections, json, re
from histor.config import load_settings
from histor.db import open_backend
START, END = "2026-10-25T00:00:00Z", "2026-11-01T00:00:00Z"
s = load_settings()
b = open_backend(s.db_path, s.database_url)
DATE = r"\d{4}-\d{2}-\d{2}([T ][\d:.]+(Z|[+-]\d{2}:?\d{2})?)?"
VER = r"\bv?\d+(\.\d+)+([-+][\w.]+)?\b"
def canon(v, level):
    if isinstance(v, dict): return {k: canon(x, level) for k, x in v.items()}
    if isinstance(v, list): return [canon(x, level) for x in v]
    if isinstance(v, str):
        t = " ".join(v.split())
        if level >= 1: t = re.sub(DATE, "<date>", t)
        if level >= 2: t = re.sub(VER, "<ver>", t)
        return t
    return v
def diffs(a, c, path=""):
    """Paths whose leaf strings differ, with a short window around the first differing character."""
    if isinstance(a, dict) and isinstance(c, dict):
        for k in sorted(set(a) | set(c)):
            yield from diffs(a.get(k), c.get(k), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(c, list) and len(a) == len(c):
        for i, (x, y) in enumerate(zip(a, c)):
            yield from diffs(x, y, f"{path}[{i}]")
    elif a != c:
        sa, sc = str(a), str(c)
        i = next((j for j in range(min(len(sa), len(sc))) if sa[j] != sc[j]), min(len(sa), len(sc)))
        lo = max(0, i - 50)
        yield path, sa[lo:i + 40], sc[lo:i + 40]
with b.read() as tx:
    rows = tx.execute("SELECT c.target_id, c.observed_at, c.from_toolset, c.to_toolset, t.transport, t.endpoint, t.name "
                      "FROM changes c JOIN targets t ON t.id = c.target_id WHERE c.observed_at >= ? AND c.observed_at < ? "
                      "AND c.from_toolset IS NOT NULL AND c.to_toolset IS NOT NULL", (START, END))
cache = {}
def blob(d):
    if d not in cache:
        with b.read() as tx:
            r = tx.one("SELECT body FROM blobs WHERE digest = ?", (d,))
        cache[d] = (json.loads(r["body"]), len(r["body"])) if r else (None, 0)
        if len(cache) > 64: cache.pop(next(iter(cache)))
    return cache[d]
per = {}
for r in rows:
    (a, _), (c, size) = blob(r["from_toolset"]), blob(r["to_toolset"])
    if a is None or c is None: continue
    ta = {t["name"]: t for t in a}; tc = {t["name"]: t for t in c}
    if set(ta) != set(tc) or canon(ta, 0) == canon(tc, 0): continue
    if canon(ta, 1) == canon(tc, 1): k = "dates"
    elif canon(ta, 2) == canon(tc, 2): k = "dates+versions"
    else: continue
    e = per.setdefault(r["target_id"], {"name": r["name"], "endpoint": r["endpoint"], "transport": r["transport"],
                                         "kinds": collections.Counter(), "fields": collections.Counter(), "times": [],
                                         "bytes": size, "tools": len(c), "example": None})
    e["kinds"][k] += 1; e["times"].append(r["observed_at"]); e["bytes"] = size
    for p, x, y in diffs(ta, tc):
        e["fields"][re.sub(r"\[\d+\]", "[]", p.split(".", 1)[1] if "." in p else p)] += 1
        if e["example"] is None: e["example"] = {"field": p, "before": x, "after": y}
out = []
for tid, e in sorted(per.items(), key=lambda kv: -sum(kv[1]["kinds"].values())):
    out.append({"target_id": tid, "name": e["name"], "endpoint": e["endpoint"], "transport": e["transport"],
                "changes": dict(e["kinds"]), "fields": dict(e["fields"].most_common(5)), "tools": e["tools"],
                "toolListBytes": e["bytes"], "first": min(e["times"]), "last": max(e["times"]), "example": e["example"]})
fieldkinds = collections.Counter()
for e in out:
    for f, n in e["fields"].items():
        fieldkinds["description" if f.endswith("description") and "inputSchema" not in f else
                   "inputSchema" if "inputSchema" in f else f.split(".")[-1]] += n
print(json.dumps({"window": [START, END], "servers": len(out), "changes": sum(sum(e["changes"].values()) for e in out),
                  "fieldKinds": dict(fieldkinds.most_common()), "byServer": out}, indent=1, default=str))
b.close()
