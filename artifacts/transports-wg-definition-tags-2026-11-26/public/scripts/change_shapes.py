"""What tool-list changes look like, counted on a public HISTOR snapshot (changes.jsonl.gz + servers.jsonl.gz).

Answers three questions the Definition Tags draft leaves open:
  - how many tools one change touches (collection tag vs per-primitive tag),
  - which of the four contract members move (description / inputSchema / outputSchema),
  - how often a server returns to a tool list it served before (rollouts, rollbacks, per-instance lists).

Usage: python3 scripts/change_shapes.py changes.jsonl.gz servers.jsonl.gz public_suffix_list.dat > change-shapes.json
"""
import collections, gzip, json, statistics, sys
from datetime import datetime

import psl


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def publisher(server, registrable):
    ep = server.get("endpoint") or ""
    if "://" in ep:
        return registrable(ep.split("://", 1)[1].split("/", 1)[0])
    return ep  # npm:<name> / pypi:<name>: each package is its own publisher here


def shape(events):
    kinds, touched, fields = collections.Counter(), collections.Counter(), collections.Counter()
    for e in events:
        a, r, m = e["added"], e["removed"], e["modified"]
        kinds["tools added or removed" if a or r else "same names, definitions changed"] += 1
        n = a + r + len(m)
        touched["1" if n == 1 else "2-5" if n <= 5 else "6+"] += 1
        if m and not a and not r:
            fields["+".join(sorted(set().union(*m)))] += 1
    n = len(events)
    pct = lambda c: {k: {"n": v, "pct": round(100 * v / n, 1)} for k, v in c.most_common()}
    return {"changes": n, "servers": len({e["server"] for e in events}), "kind": pct(kinds),
            "toolsTouched": pct(touched), "sameNamesByMembers": pct(fields)}


if __name__ == "__main__":
    changes_path, servers_path, suffixes = sys.argv[1:4]
    registrable = psl.make(suffixes)
    servers = {}
    with gzip.open(servers_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            servers[s["id"]] = s
    events, seen, returns, gaps = [], collections.defaultdict(dict), [], []
    first = last = None
    with gzip.open(changes_path, "rt", encoding="utf-8") as f:   # oldest first
        for line in f:
            c = json.loads(line)
            if c.get("fromToolSetDigest") in (None, "None") or c.get("toToolSetDigest") in (None, "None"):
                continue  # first observation of a server, not a change
            s = json.loads(c["summaryJson"]) if isinstance(c["summaryJson"], str) else c["summaryJson"]
            sid, at = c["serverId"], c["observedAt"]
            first, last = first or at, at
            srv = servers.get(sid, {})
            e = {"server": sid, "publisher": publisher(srv, registrable), "transport": srv.get("transport"),
                 "added": len(s.get("added") or []), "removed": len(s.get("removed") or []),
                 "modified": [set(m.get("fields") or {}) for m in (s.get("modified") or [])]}
            events.append(e)
            hist = seen[sid]
            hist.setdefault(c["fromToolSetDigest"], at)
            if c["toToolSetDigest"] in hist:              # back to a list this server served before
                left = hist.get("_left_" + c["toToolSetDigest"], hist[c["toToolSetDigest"]])
                returns.append(e)
                gaps.append((ts(at) - ts(left)).total_seconds() / 3600)
            hist["_left_" + c["fromToolSetDigest"]] = at
            hist.setdefault(c["toToolSetDigest"], at)
    by_pub = collections.Counter(e["publisher"] for e in events)
    top = by_pub.most_common(8)
    top1 = top[0][0]
    per_server = collections.Counter(e["server"] for e in events)
    remote = [e for e in events if e["transport"] != "stdio"]
    out = {
        "snapshot": "2026-11-23", "window": [first, last],
        "all": shape(events),
        "topPublishers": [{"publisher": p, "changes": n, "pct": round(100 * n / len(events), 1)} for p, n in top],
        "withoutTopPublisher": {"publisher": top1, **shape([e for e in events if e["publisher"] != top1])},
        "remoteWithoutTopPublisher": shape([e for e in remote if e["publisher"] != top1]),
        "changesPerServer": {"servers": len(per_server), "median": statistics.median(per_server.values()),
                             "one": sum(1 for v in per_server.values() if v == 1),
                             "tenOrMore": sum(1 for v in per_server.values() if v >= 10)},
        "returnsToEarlierList": {
            "changes": len(returns), "pctOfChanges": round(100 * len(returns) / len(events), 1),
            "servers": len({e["server"] for e in returns}),
            "withoutTopPublisher": {"changes": sum(1 for e in returns if e["publisher"] != top1),
                                    "servers": len({e["server"] for e in returns if e["publisher"] != top1})},
            "hoursAwayMedian": round(statistics.median(gaps), 1) if gaps else None,
            "within1h": sum(1 for g in gaps if g <= 1), "within24h": sum(1 for g in gaps if g <= 24),
        },
    }
    json.dump(out, sys.stdout, indent=1)
    print()
