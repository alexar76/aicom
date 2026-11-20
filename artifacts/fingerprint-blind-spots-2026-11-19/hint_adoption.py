#!/usr/bin/env python3
"""How many servers in a HISTOR snapshot send tool hint annotations at all, and how completely.

Population: listed servers with a recorded tool set whose extras were observed (servers.toolExtrasDigest
is not null; "" means observed with no extra members). Per server it reads the current extras record.

usage: hint_adoption.py <snapshot folder>   (needs servers.jsonl.gz and tool_extras.jsonl.gz)
"""
import collections
import gzip
import json
import sys
from urllib.parse import urlsplit

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def main(folder):
    extras = {}
    with gzip.open(f"{folder}/tool_extras.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            e = r["extrasJson"]
            extras[r["digest"]] = json.loads(e) if isinstance(e, str) else e

    n = collections.Counter()
    hosts = collections.defaultdict(set)
    tools = collections.Counter()
    with gzip.open(f"{folder}/servers.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            if s.get("delisted") or not s.get("toolSetDigest"):
                continue
            d = s.get("toolExtrasDigest")
            if d is None:
                n["not_observed_since_extras_are_kept"] += 1
                continue
            ep = s.get("endpoint") or ""
            remote = ep.startswith("http")
            host = (urlsplit(ep).hostname or ep) if remote else ep
            kind = "remote" if remote else "package"
            count = s.get("toolCount") or 0
            e = extras.get(d) if d else {"tools": {}}
            if e is None:
                n["extras_record_missing"] += 1
                continue
            partial = bool(e.get("omitted") or e.get("oversized"))
            per_hint = collections.Counter()
            any_hint_tools = 0
            misplaced = 0
            for t in (e.get("tools") or {}).values():
                a = t.get("annotations") if isinstance(t.get("annotations"), dict) else {}
                got = [h for h in HINTS if isinstance(a.get(h), bool)]
                if got:
                    any_hint_tools += 1
                for h in got:
                    per_hint[h] += 1
                    tools[f"{h}={str(a[h]).lower()}"] += 1
                if any(h in t for h in HINTS):
                    misplaced += 1
            n["servers"] += 1
            n[f"servers_{kind}"] += 1
            hosts["all"].add(host)
            tools["all"] += count
            tools["with_any_hint"] += any_hint_tools
            if partial:
                n["servers_with_partial_extras_record"] += 1
            if any_hint_tools:
                n["servers_with_any_hint"] += 1
                n[f"servers_with_any_hint_{kind}"] += 1
                hosts["any_hint"].add(host)
            if per_hint["readOnlyHint"]:
                n["servers_with_readOnlyHint_on_some_tool"] += 1
                if count and per_hint["readOnlyHint"] >= count and not partial:
                    n["servers_with_readOnlyHint_on_every_tool"] += 1
            if count and all(per_hint[h] >= count for h in HINTS) and not partial:
                n["servers_with_all_four_hints_on_every_tool"] += 1
            if misplaced:
                n["servers_with_a_hint_outside_annotations"] += 1
                tools["with_a_hint_outside_annotations"] += misplaced
    out = {
        "population": "listed servers with a recorded tool set and an observed extras record",
        "servers": dict(sorted(n.items())),
        "hosts_or_packages": {k: len(v) for k, v in sorted(hosts.items())},
        "tools": dict(sorted(tools.items())),
    }
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main(sys.argv[1])
