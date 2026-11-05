"""From outside: does any peer's signed catalogue time go backwards between reads?

Reads `generated_at` from each peer's catalogue twice, a few seconds apart, and compares both with the value
a hub recorded (lines `  <url>  generated_at <t>  recorded …` from check_live.py on stdin). A read older than the
recorded value is what the new check would refuse at the next crawl.
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone

def parse(t):
    d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aimarket-catalogue-floor-check/1 (+https://modelmarket.dev)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

recorded = {m[1]: m[2] for m in (re.match(r"\s+(\S+)\s+generated_at (\S+)", l) for l in sys.stdin) if m}
bad = 0
for url, rec in sorted(recorded.items()):
    try:
        wk = get(url + "/.well-known/ai-market.json")
        murl = wk.get("manifest_url") or url + "/ai-market/manifest"
        reads = []
        for i in range(2):
            reads.append(get(murl).get("generated_at"))
            time.sleep(3)
        older = [t for t in reads if parse(t) < parse(rec)]
        back = parse(reads[1]) < parse(reads[0])
        status = "OLDER THAN RECORDED" if older else ("WENT BACK" if back else "ok")
        bad += status != "ok"
        print(f"{status:20} {url}  recorded {rec}  reads {reads[0]} , {reads[1]}")
    except Exception as exc:
        print(f"{'unreachable':20} {url}  {type(exc).__name__}: {str(exc)[:80]}")
print(f"{len(recorded)} peers, {bad} would be refused")
