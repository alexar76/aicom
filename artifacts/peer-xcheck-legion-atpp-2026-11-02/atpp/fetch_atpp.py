"""Fetch ATPP's signed claim for each sampled server (one GET each, one at a time) and decode the in-toto payload."""
import base64, json, time, urllib.parse, urllib.request, urllib.error
UA = {"User-Agent": "histor-xcheck/2026-11-02 (+https://histor.modelmarket.dev/; one-off comparison of two public records)"}
with open("atpp_claims.jsonl", "w") as out:
    for line in open("sample.jsonl"):
        name = json.loads(line)["name"]
        url = "https://trust.redthreadsec.com/v/mcp/" + urllib.parse.quote(name, safe="/") + ".json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                env = json.load(r); st = r.status
            pred = json.loads(base64.b64decode(env["payload"])).get("predicate")
        except urllib.error.HTTPError as e:
            st, pred = e.code, None
        except Exception as e:
            st, pred = type(e).__name__, None
        out.write(json.dumps({"name": name, "http": st, "predicate": pred}) + "\n"); out.flush()
        time.sleep(0.6)
print("done")
