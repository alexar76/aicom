"""Walk https://histor.modelmarket.dev/v0.1/servers?version=latest and save every entry (one JSON per line).

    python3 walk.py out.jsonl
Standard library only. 100 per page, 0.3 s between pages.
"""
import json, sys, time, urllib.parse, urllib.request
BASE = "https://histor.modelmarket.dev/v0.1/servers"
out = open(sys.argv[1], "w")
cursor, pages, n = None, 0, 0
started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
while True:
    q = {"limit": 100, "version": "latest"}
    if cursor: q["cursor"] = cursor
    req = urllib.request.Request(BASE + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "histor-subregistry-article-check/1"})
    for attempt in range(5):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60)); break
        except Exception as e:
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"page {pages} failed")
    for s in d["servers"]:
        out.write(json.dumps(s, separators=(",", ":")) + "\n"); n += 1
    pages += 1
    cursor = d["metadata"].get("nextCursor")
    if not cursor: break
    time.sleep(0.3)
print(json.dumps({"started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pages": pages, "entries": n}))
