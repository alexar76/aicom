"""HISTOR snapshot 2026-11-02 (07:20Z) against LEGION's latest record per server, tool by tool.

LEGION's per-tool hash, from its records (tools_fingerprint.algo): sha256(JCS-RFC8785({name, description, inputSchema})).
The form of a missing member is not published; each variant is tried and reported.
"""
import collections, gzip, hashlib, json, sys
import rfc8785

def sha(obj):
    return hashlib.sha256(rfc8785.dumps(obj)).hexdigest()

VARIANTS = {
    "omit-missing": lambda t: {k: t[k] for k in ("name", "description", "inputSchema") if k in t},
    "null-missing": lambda t: {k: t.get(k) for k in ("name", "description", "inputSchema")},
    "empty-desc": lambda t: {"name": t.get("name"), "description": t.get("description", ""), **({"inputSchema": t["inputSchema"]} if "inputSchema" in t else {})},
}
sample = {json.loads(l)["name"]: json.loads(l) for l in open("sample.jsonl")}
sets = {}
for line in gzip.open("legion-toolsets.jsonl.gz", "rt"):
    d = json.loads(line); sets[d["digest"]] = json.loads(d["toolsJson"])
legion = {}
for line in open("legion_servers.jsonl"):
    r = json.loads(line); legion[r["name"]] = r
rows, per_variant = [], collections.Counter()
for name, h in sample.items():
    r = legion.get(name)
    rec = ((r or {}).get("doc") or {}).get("latest_record")
    if not rec or "tools_fingerprint" not in rec:
        rows.append({"name": name, "verdict": "legion-none", "http": (r or {}).get("http"), "status": ((r or {}).get("doc") or {}).get("status")})
        continue
    fp = rec["tools_fingerprint"]
    theirs = dict(fp["per_tool_sha256"])
    tools = sets.get(h["toolSetDigest"]) or []
    ours_by_variant = {v: {t["name"]: sha(f(t)) for t in tools} for v, f in VARIANTS.items()}
    best = max(VARIANTS, key=lambda v: sum(ours_by_variant[v].get(n) == s for n, s in theirs.items()))
    ours = ours_by_variant[best]
    same = sorted(n for n in theirs if ours.get(n) == theirs[n])
    differ = sorted(n for n in theirs if n in ours and ours[n] != theirs[n])
    only_l, only_h = sorted(set(theirs) - set(ours)), sorted(set(ours) - set(theirs))
    for v in VARIANTS:
        per_variant[v] += sum(ours_by_variant[v].get(n) == s for n, s in theirs.items())
    verdict = "same" if not differ and not only_l and not only_h else ("names-differ" if only_l or only_h else "definitions-differ")
    rows.append({"name": name, "verdict": verdict, "algo": fp.get("algo"), "legionObservedAt": rec.get("observed_at"),
                 "legionKind": rec.get("change", {}).get("kind"), "historUnchangedSince": h["unchangedSince"],
                 "historLastObserved": h["lastObserved"], "tools": len(theirs), "same": len(same), "differ": differ,
                 "onlyLegion": only_l, "onlyHistor": only_h, "variant": best})
json.dump(rows, open("compare.json", "w"), indent=1)
c = collections.Counter(r["verdict"] for r in rows)
print("servers", len(rows), dict(c))
cmp = [r for r in rows if r["verdict"] not in ("legion-none",)]
tools = sum(r["tools"] for r in cmp); same = sum(r["same"] for r in cmp)
print("tools compared", tools, "identical", same, "%.1f%%" % (100 * same / max(tools, 1)))
print("matches per variant", dict(per_variant))
print("legion-none:", collections.Counter((r.get("http"), r.get("status")) for r in rows if r["verdict"] == "legion-none").most_common(6))
