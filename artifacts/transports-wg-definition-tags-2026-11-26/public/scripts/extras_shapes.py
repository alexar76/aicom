"""Changes outside name/description/inputSchema/outputSchema: which tool members move, and how often alone.

Counted on a public HISTOR snapshot (extras_changes.jsonl.gz, changes.jsonl.gz, servers.jsonl.gz).
Usage: python3 scripts/extras_shapes.py extras_changes.jsonl.gz changes.jsonl.gz servers.jsonl.gz public_suffix_list.dat > extras-shapes.json
"""
import collections, gzip, json, sys

import psl

if __name__ == "__main__":
    extras_path, changes_path, servers_path, suffixes = sys.argv[1:5]
    registrable = psl.make(suffixes)
    pub = {}
    with gzip.open(servers_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            ep = s.get("endpoint") or ""
            pub[s["id"]] = registrable(ep.split("://", 1)[1].split("/", 1)[0]) if "://" in ep else ep
    contract = set()
    with gzip.open(changes_path, "rt", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            contract.add((c["serverId"], c["observedAt"]))
    n = alone = 0
    first = last = None
    members, only, servers, by_pub, alone_pub = collections.Counter(), collections.Counter(), set(), collections.Counter(), collections.Counter()
    hint_only_alone = meta_alone = 0
    alone_servers = collections.defaultdict(set)
    with gzip.open(extras_path, "rt", encoding="utf-8") as f:
        for line in f:
            x = json.loads(line)
            if x.get("fromExtrasDigest") in (None, "None", ""):
                continue                      # first time extras were recorded for the server
            s = json.loads(x["summaryJson"]) if isinstance(x["summaryJson"], str) else x["summaryJson"]
            moved = set()
            for t in (s.get("tools") or {}).values():
                if t.get("annotations"):
                    moved.add("annotations")
                moved |= set((t.get("members") or {}).keys()) - {"annotations"}
            if not moved:
                continue
            n += 1
            first, last = first or x["observedAt"], x["observedAt"]
            servers.add(x["serverId"])
            p = pub.get(x["serverId"], "?")
            by_pub[p] += 1
            for m in moved:
                members[m if m in ("annotations", "_meta", "title", "icons", "execution") else "other member: " + m] += 1
            if (x["serverId"], x["observedAt"]) not in contract:
                alone += 1
                alone_pub[p] += 1
                only["+".join(sorted(moved))] += 1
                alone_servers["+".join(sorted(moved))].add(x["serverId"])
                hint_only_alone += moved == {"annotations"}
                meta_alone += "_meta" in moved
    top = by_pub.most_common(1)[0]
    json.dump({
        "snapshot": "2026-11-23", "window": [first, last], "changes": n, "servers": len(servers),
        "membersMoved": dict(members.most_common(12)),
        "withNoContractChangeInSameRead": {"changes": alone, "pct": round(100 * alone / n, 1),
                                           "byMembers": {k: {"changes": v, "servers": len(alone_servers[k])} for k, v in only.most_common(8)},
                                           "annotationsOnly": hint_only_alone, "touchingMeta": meta_alone,
                                           "topPublishers": alone_pub.most_common(4)},
        "topPublisher": {"publisher": top[0], "changes": top[1], "pct": round(100 * top[1] / n, 1)},
    }, sys.stdout, indent=1)
    print()
