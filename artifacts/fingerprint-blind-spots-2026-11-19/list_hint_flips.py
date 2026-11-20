#!/usr/bin/env python3
"""List every hint flip in a read where the AI SDK tool fingerprint of no tool changed.

Written separately from blind_spots.py on purpose: it walks the extras file first and
applies the visibility rule per read, so its totals check the other script's
`no_tool_fingerprint_changed_in_that_read` numbers.

usage: list_hint_flips.py <snapshot folder> <since> <until> <out.csv>
"""
import collections
import csv
import gzip
import json
import sys
from urllib.parse import urlsplit

TOP_ADDITIONAL = '$."additionalProperties"'


def summary(row):
    s = row["summaryJson"]
    return json.loads(s) if isinstance(s, str) else s


def main(folder, since, until, out_path):
    servers = {}
    with gzip.open(f"{folder}/servers.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            servers[r["id"]] = r
    contract = {}
    with gzip.open(f"{folder}/changes.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if since <= r["observedAt"] <= until:
                contract[(r["serverId"], r["observedAt"])] = r

    rows = []
    with gzip.open(f"{folder}/extras_changes.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if not since <= r["observedAt"] <= until:
                continue
            s = summary(r)
            if s.get("truncated"):
                continue
            c = contract.get((r["serverId"], r["observedAt"]))
            cs = summary(c) if c else None
            if cs and cs.get("detail") != "full":
                continue
            seen = False
            if cs:
                if cs.get("added") or cs.get("removed"):
                    seen = True
                for m in cs.get("modified", []):
                    f = m.get("fields") or {}
                    if "description" in f:
                        seen = True
                    if "inputSchema" in f and not all(p.get("path") == TOP_ADDITIONAL for p in f["inputSchema"]):
                        seen = True
            for d in s["tools"].values():
                if "title" in (d.get("annotations") or {}) or "title" in (d.get("members") or {}):
                    seen = True
            if seen:
                continue
            for name, d in s["tools"].items():
                ann = d.get("annotations") or {}
                ro, de = ann.get("readOnlyHint"), ann.get("destructiveHint")
                moves = []
                if ro and ro[0] is True and ro[1] is False:
                    moves.append("readOnlyHint true->false")
                if de and de[0] is False and de[1] is True:
                    moves.append("destructiveHint false->true")
                sv = servers.get(r["serverId"], {})
                ep = sv.get("endpoint") or ""
                host = urlsplit(ep).hostname if ep.startswith("http") else ep
                for move in moves:
                    rows.append((r["observedAt"], r["serverId"], sv.get("name"), host, name, move,
                                 json.dumps(ann, sort_keys=True),
                                 "outputSchema or top-level additionalProperties only" if cs else "none"))
    rows.sort()
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["observedAt", "serverId", "serverName", "hostOrPackage", "tool", "move",
                    "annotationMoves", "contractChangeInSameRead"])
        w.writerows(rows)
    pairs = collections.defaultdict(set)
    for row in rows:
        pairs[row[5]].add((row[1], row[4]))
    for move, p in sorted(pairs.items()):
        print(f"{move}: {len(p)} tools on {len({x[0] for x in p})} servers")


if __name__ == "__main__":
    main(*sys.argv[1:5])
