#!/usr/bin/env python3
"""Build the calibration corpus for WARDEN's hint-versus-description check from a HISTOR snapshot.

One row per tool on a listed server's current tool set whose current extras record carries
annotations with an explicit readOnlyHint=true or destructiveHint=false (the two "says less" claims
the check reads). Each row: server id, endpoint, tool name, description, annotations.

usage: extract.py <folder with servers.jsonl.gz and tool_extras.jsonl.gz> <toolsets.jsonl(.gz) path or -> <out.jsonl>
       toolsets may be '-' to read the decompressed stream on stdin (it is 3.5 GB compressed).
"""
import gzip
import json
import sys


def claims(a):
    return isinstance(a, dict) and (a.get("readOnlyHint") is True or a.get("destructiveHint") is False)


def main(folder, toolsets, out):
    want_set, want_extras = {}, {}
    with gzip.open(f"{folder}/servers.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            if s.get("delisted") or not s.get("toolSetDigest") or not s.get("toolExtrasDigest"):
                continue
            want_set.setdefault(s["toolSetDigest"], []).append((s["id"], s.get("endpoint") or "", s["toolExtrasDigest"]))
            want_extras[s["toolExtrasDigest"]] = None
    with gzip.open(f"{folder}/tool_extras.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["digest"] in want_extras:
                e = r["extrasJson"]
                e = json.loads(e) if isinstance(e, str) else e
                want_extras[r["digest"]] = (e or {}).get("tools") or {}
    src = sys.stdin if toolsets == "-" else (gzip.open(toolsets, "rt", encoding="utf-8") if toolsets.endswith(".gz") else open(toolsets, encoding="utf-8"))
    rows = sets = 0
    with open(out, "w", encoding="utf-8") as w:
        for line in src:
            r = json.loads(line)
            servers = want_set.get(r["digest"])
            if not servers:
                continue
            sets += 1
            tools = r["toolsJson"]
            tools = json.loads(tools) if isinstance(tools, str) else tools
            for sid, ep, xd in servers:
                extras = want_extras.get(xd) or {}
                for t in tools if isinstance(tools, list) else []:
                    name = t.get("name")
                    a = (extras.get(name) or {}).get("annotations")
                    if not claims(a):
                        continue
                    w.write(json.dumps({"server": sid, "endpoint": ep, "tool": name,
                                        "description": t.get("description") or "", "annotations": a}, ensure_ascii=False) + "\n")
                    rows += 1
    print(json.dumps({"currentToolSets": len(want_set), "toolSetsRead": sets, "rows": rows}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
