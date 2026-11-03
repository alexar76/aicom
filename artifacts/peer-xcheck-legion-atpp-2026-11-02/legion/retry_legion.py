import json, time, urllib.parse, urllib.request, urllib.error
B = "https://tlog.legion-api.com/tlog/v0/servers/"
UA = {"User-Agent": "histor-xcheck/2026-11-02 (+https://histor.modelmarket.dev/; one-off comparison of two public logs)"}
rows = [json.loads(l) for l in open("legion_servers.jsonl")]
retried = 0
for r in rows:
    if r["http"] in (200, 404): continue
    time.sleep(2.0); retried += 1
    try:
        with urllib.request.urlopen(urllib.request.Request(B + urllib.parse.quote(r["name"], safe="/"), headers=UA), timeout=40) as resp:
            r["http"], r["doc"] = resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        r["http"] = e.code
    except Exception as e:
        r["http"] = type(e).__name__
with open("legion_servers.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
import collections
print("retried", retried, collections.Counter(r["http"] for r in rows).most_common())
