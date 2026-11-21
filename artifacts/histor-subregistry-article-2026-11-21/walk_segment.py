"""One segment of the walk: start after a cursor, stop when the next segment's first name appears.

    python3 walk_segment.py out.jsonl START_CURSOR [STOP_NAME]
Same pages as walk.py (version=latest, 100 per page, 0.3 s apart). Segments may overlap by one entry; merge with
merge.py, which keeps one line per name and version.
"""
import json, sys, time, urllib.parse, urllib.request
BASE = "https://histor.modelmarket.dev/v0.1/servers"
out = open(sys.argv[1], "w")
cursor, stop = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else None)
pages = n = 0
while True:
    q = {"limit": 100, "version": "latest", "cursor": cursor}
    req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "histor-subregistry-article-check/1"})
    for attempt in range(5):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60)); break
        except Exception:
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"page {pages} failed")
    done = False
    for s in d["servers"]:
        if stop and s["server"]["name"] == stop:
            done = True; break
        out.write(json.dumps(s, separators=(",", ":")) + "\n"); n += 1
    pages += 1
    cursor = d["metadata"].get("nextCursor")
    if done or not cursor: break
    time.sleep(0.3)
print(json.dumps({"start": sys.argv[2], "stop": stop, "pages": pages, "entries": n}))
