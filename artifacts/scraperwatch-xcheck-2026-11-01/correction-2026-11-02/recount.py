"""Our 31 Oct / 1 Nov verdicts (../results.json) restricted to the records ScraperWatch kept after its
2026-11-02 robots.txt correction (changes.json here, against ../changes.json as first fetched).

    python3 -I recount.py ../changes.json changes.json ../results.json
"""
import collections
import json
import sys

old, new, res = (json.load(open(p)) for p in sys.argv[1:4])
DAYS = ("2026-10-31", "2026-11-01")


def keys(log):
    return collections.Counter((day["day"], c["endpoint"], c.get("op"))
                               for day in log["days"] if day["day"] in DAYS for c in day["changes"])


def size(v):
    return len(v) if isinstance(v, (list, dict)) else (v or 0)


before, after = keys(old), keys(new)
removed = before - after
for day in DAYS:
    print(day, "records", sum(n for k, n in before.items() if k[0] == day), "->",
          sum(n for k, n in after.items() if k[0] == day))
print("removed:", dict(collections.Counter(k[2] for k in removed.elements())),
      "on", len({k[1] for k in removed}), "endpoints")

left, gone = collections.Counter(removed), []
for row in res["tool_changes"]:
    k = (row["day"], row["endpoint"], row["op"])
    if left[k] > 0:
        left[k] -= 1
        gone.append(row)
kept = [row for row in res["tool_changes"] if row not in gone]
verdicts = collections.Counter(row["verdict"] for row in kept)
print("tool-change records", len(res["tool_changes"]), "->", len(kept), dict(verdicts))
match = "same change in HISTOR"
print("items seen in matches", sum(size(r.get("items_seen_by_histor")) for r in res["tool_changes"] if r["verdict"] == match),
      "->", sum(size(r.get("items_seen_by_histor")) for r in kept if r["verdict"] == match))
status_gone = {(d, e) for (d, e, op) in removed if op == "status_changed"}
print("status transitions", len(res["status_transitions"]), "->",
      sum(1 for r in res["status_transitions"] if (r.get("day"), r.get("endpoint")) not in status_gone))
print("removed rows by verdict:", dict(collections.Counter(r["verdict"] for r in gone)))
