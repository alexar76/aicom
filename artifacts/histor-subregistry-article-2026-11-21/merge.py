"""Merge walk.py's output (cut at the first segment's first name) with the segments into one file.

    python3 merge.py OUT latest-2026-11-21.jsonl seg-f.jsonl seg-k.jsonl seg-p.jsonl seg-u.jsonl
The main walk ran past the first segment's start; its lines from that name on are dropped. Keeps the first line per
name and version and fails if a segment boundary was not reached by the part before it.
"""
import json, sys
out, main, segs = sys.argv[1], sys.argv[2], sys.argv[3:]
first = [json.loads(open(s).readline())["server"]["name"] for s in segs]
seen, lines = set(), []
def take(path, stop=None):
    reached = stop is None
    for line in open(path):
        s = json.loads(line)
        if stop and s["server"]["name"] == stop:
            reached = True; break
        key = (s["server"]["name"], s["server"]["version"])
        if key not in seen:
            seen.add(key); lines.append(line)
    if not reached:
        raise SystemExit(f"{path} did not reach {stop}")
take(main, first[0])
for s in segs:
    take(s)
open(out, "w").writelines(lines)
print(json.dumps({"entries": len(lines), "segments": first}))
