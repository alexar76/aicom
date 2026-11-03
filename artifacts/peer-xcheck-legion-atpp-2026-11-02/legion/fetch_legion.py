"""Ask LEGION's public log for its latest record of each sampled server (one GET each, three at a time)."""
import json, sys, time, urllib.parse, urllib.request, urllib.error, concurrent.futures as cf
B = "https://tlog.legion-api.com/tlog/v0/servers/"
UA = {"User-Agent": "histor-xcheck/2026-11-02 (+https://histor.modelmarket.dev/; one-off comparison of two public logs)"}
names = [json.loads(l)["name"] for l in open("sample.jsonl")]
def get(name):
    time.sleep(0.4)
    try:
        with urllib.request.urlopen(urllib.request.Request(B + urllib.parse.quote(name, safe="/"), headers=UA), timeout=30) as r:
            return name, r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return name, e.code, None
    except Exception as e:
        return name, type(e).__name__, None
with open("legion_servers.jsonl", "w") as out, cf.ThreadPoolExecutor(3) as ex:
    for name, st, doc in ex.map(get, names):
        out.write(json.dumps({"name": name, "http": st, "doc": doc}) + "\n")
print("done", len(names))
