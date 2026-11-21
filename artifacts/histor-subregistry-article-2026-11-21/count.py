"""Count what dev.modelmarket.histor/observed says about each latest entry of the HISTOR subregistry.

    python3 count.py latest-2026-11-21.jsonl walk.log [as-of, server time] > counts-2026-11-21.json
The Mac this ran on keeps a skewed clock, so the as-of time is the server's Date header after the walk.
One category per server, first match wins:
  recorded      a target with a recorded tool list (toolCount not null)
  credentials   a target answered 401 or 403 (the crawler sends no credentials)
  robots        a target's robots.txt disallows the crawler, or could not be read
  not_tried     every target has notAttempted (package type, transport or templated URL HISTOR does not read)
  failed        anything else: timeouts, protocol errors, 404/410, private addresses, a package that exited
  no_block      no observed block: HISTOR has no target for that name yet
Among recorded servers: how many have no target whose last read was ok (the list is from an earlier read), how many changed their tool set at least once, and since when it is unchanged.
"""
import json, sys, collections
from datetime import datetime, timezone

walk = json.loads(open(sys.argv[2]).read().strip().splitlines()[-1])
at = datetime.strptime(sys.argv[3] if len(sys.argv) > 3 else walk["finished"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
cat = collections.Counter(); status = collections.Counter(); notatt = collections.Counter()
changed = 0; stale = 0; recent7 = 0; recent30 = 0; tools = 0; recorded_targets = 0
for line in open(sys.argv[1]):
    s = json.loads(line)
    o = s["_meta"].get("dev.modelmarket.histor/observed")
    if not o:
        cat["no_block"] += 1; continue
    ts = o["targets"]
    for t in ts:
        status[t["lastStatus"] or "none"] += 1
        if t["notAttempted"]: notatt[t["notAttempted"]] += 1
    rec = [t for t in ts if t["toolCount"] is not None]
    if rec:
        cat["recorded"] += 1
        recorded_targets += len(rec)
        if not any(t["lastStatus"] == "ok" for t in rec): stale += 1
        tools += max(t["toolCount"] for t in rec)
        if any(t["changes"] > 0 for t in rec): changed += 1
        since = [datetime.strptime(t["unchangedSince"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) for t in rec if t["unchangedSince"] and t["changes"] > 0]
        if since and (at - max(since)).days < 7: recent7 += 1
        if since and (at - max(since)).days < 30: recent30 += 1
    elif any((t["lastStatus"] or "") in ("http-401", "http-403") for t in ts): cat["credentials"] += 1
    elif any((t["lastStatus"] or "").startswith("robots") for t in ts): cat["robots"] += 1
    elif all(t["notAttempted"] for t in ts): cat["not_tried"] += 1
    else: cat["failed"] += 1
print(json.dumps({"as_of": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "https://histor.modelmarket.dev/v0.1/servers?version=latest", "walk": walk,
    "servers": sum(cat.values()), "categories": dict(cat.most_common()),
    "recorded": {"servers": cat["recorded"], "targets": recorded_targets, "tools_largest_target_sum": tools,
                 "last_read_not_ok": stale, "changed_at_least_once": changed, "changed_in_last_7_days": recent7, "changed_in_last_30_days": recent30},
    "target_last_status": dict(status.most_common()), "target_not_attempted": dict(notatt.most_common())}, indent=1))
