"""For each server where the two logs differ: when did each last see a change, and does HISTOR's set now (live API)
equal LEGION's latest? Reads HISTOR's public API only for those servers."""
import collections, gzip, hashlib, json, time, urllib.request
import rfc8785
SNAP = "2026-11-02T07:20:03Z"
def sha(t): return hashlib.sha256(rfc8785.dumps({k: t[k] for k in ("name", "description", "inputSchema") if k in t})).hexdigest()
rows = json.load(open("compare.json"))
sample = {json.loads(l)["name"]: json.loads(l) for l in open("sample.jsonl")}
legion = {json.loads(l)["name"]: json.loads(l) for l in open("legion_servers.jsonl")}
diff = [r for r in rows if r["verdict"] in ("definitions-differ", "names-differ")]
ids = {sample[r["name"]]["id"] for r in diff}
hist_changes = collections.defaultdict(list)
for line in gzip.open("changes.jsonl.gz", "rt"):
    c = json.loads(line)
    if c["serverId"] in ids: hist_changes[c["serverId"]].append(c["observedAt"])
out = []
for r in diff:
    s = sample[r["name"]]; rec = legion[r["name"]]["doc"]["latest_record"]
    theirs = dict(rec["tools_fingerprint"]["per_tool_sha256"])
    lrecs = legion[r["name"]]["doc"].get("records") or []
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://histor.modelmarket.dev/api/v1/servers/{s['id']}",
                headers={"User-Agent": "histor-xcheck/2026-11-02"}), timeout=30) as resp:
            page = json.load(resp)
        live = {t["name"]: sha(t) for t in page.get("tools", [])}
        live_same = live == theirs
        live_info = {"liveUnchangedSince": page.get("unchangedSince") or (page.get("target") or {}).get("unchanged_since"), "liveEqualsLegion": live_same}
    except Exception as e:
        live_info = {"liveError": type(e).__name__}
    time.sleep(0.5)
    out.append({"name": r["name"], "id": s["id"], "verdict": r["verdict"], "differ": r["differ"][:5], "onlyLegion": r["onlyLegion"][:5],
                "onlyHistor": r["onlyHistor"][:5], "legionLatest": rec["observed_at"], "legionKind": rec["change"]["kind"],
                "legionRecords": len(lrecs), "historChanges": sorted(hist_changes.get(s["id"], []))[-4:],
                "historUnchangedSince": s["unchangedSince"], "historLastObserved": s["lastObserved"], **live_info})
json.dump(out, open("explain.json", "w"), indent=1)
for o in out:
    print(o["verdict"][:5], o["name"][:40], "| L", o["legionLatest"][5:16], o["legionKind"], o["legionRecords"], "| H unch", (o["historUnchangedSince"] or "")[5:16],
          "chg", [x[5:16] for x in o["historChanges"][-2:]], "| live=L", o.get("liveEqualsLegion"), "| d", len(o["differ"]), "L-only", len(o["onlyLegion"]), "H-only", len(o["onlyHistor"]))
