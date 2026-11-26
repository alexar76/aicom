"""Classify the newest HISTOR change records (public API, read-only).
Usage: python3 -B sample_changes.py [pages]   # 200 records per page, default 10
"""
import collections, json, sys, time, urllib.request

pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
rows, before = [], None
for _ in range(pages):
    url = "https://histor.modelmarket.dev/api/v1/changes?limit=200" + (f"&before={before}" if before else "")
    req = urllib.request.Request(url, headers={"User-Agent": "impact-plus-sample/1 (read-only)"})
    page = json.load(urllib.request.urlopen(req, timeout=60))["changes"]
    if not page:
        break
    rows += page
    before = page[-1]["id"]
    time.sleep(1)


def added(c):
    return [a if isinstance(a, str) else a.get("tool") for a in c["summary"]["added"]]


def fleet(c):  # the Pipeworx rollout of 26 Nov: same four new tools on every entry
    return "result_settings" in added(c) or any(m["tool"].startswith("ask_pipeworx") for m in c["summary"]["modified"])


def stats(sel):
    kinds, touched, fields = collections.Counter(), collections.Counter(), collections.Counter()
    for c in sel:
        s = c["summary"]
        a, r, m = len(s["added"]), len(s["removed"]), s["modified"]
        kinds["list changed" if a or r else "same names, definitions changed"] += 1
        n = a + r + len(m)
        touched["1" if n == 1 else "2-5" if n <= 5 else "6+"] += 1
        if m and not a and not r:
            fs = set()
            for x in m:
                fs |= set(x["fields"])
            fields["+".join(sorted(fs))] += 1
    return {"records": len(sel), "servers": len({c["target_id"] for c in sel}),
            "kinds": dict(kinds), "toolsTouched": dict(touched), "modifiedOnlyByFields": dict(fields.most_common())}


one = [c for c in rows if fleet(c)]
rest = [c for c in rows if not fleet(c)]
print(json.dumps({
    "source": "https://histor.modelmarket.dev/api/v1/changes",
    "window": [rows[-1]["observed_at"], rows[0]["observed_at"]], "ids": [rows[-1]["id"], rows[0]["id"]],
    "all": stats(rows),
    "oneFleetRollout": {**stats(one), "window": [min(c["observed_at"] for c in one), max(c["observed_at"] for c in one)]} if one else None,
    "withoutThatFleet": stats(rest),
}, indent=1))
