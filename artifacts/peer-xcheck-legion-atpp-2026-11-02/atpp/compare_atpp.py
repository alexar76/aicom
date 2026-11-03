"""ATPP's signed claim per server (tools count + list sha256, 'tools-stable' check) against HISTOR's 2026-11-02 snapshot.
ATPP does not publish how its list digest is formed; candidate forms are tried over HISTOR's entries."""
import collections, gzip, hashlib, json, sys
import rfc8785
L = sys.argv[1]
def h(b): return hashlib.sha256(b).hexdigest()
def pick(t, keys): return {k: t[k] for k in keys if k in t}
FORMS = {
    "jcs sorted {name,description,inputSchema}": lambda ts: h(rfc8785.dumps(sorted((pick(t, ("name", "description", "inputSchema")) for t in ts), key=lambda x: x.get("name", "")))),
    "jcs sorted full entries": lambda ts: h(rfc8785.dumps(sorted(ts, key=lambda x: x.get("name", "")))),
    "jcs as served {name,description,inputSchema}": lambda ts: h(rfc8785.dumps([pick(t, ("name", "description", "inputSchema")) for t in ts])),
    "jcs as served full": lambda ts: h(rfc8785.dumps(ts)),
    "json sort_keys sorted {n,d,i}": lambda ts: h(json.dumps(sorted((pick(t, ("name", "description", "inputSchema")) for t in ts), key=lambda x: x.get("name", "")), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()),
    "jcs sorted {name,description,inputSchema,outputSchema,annotations}": lambda ts: h(rfc8785.dumps(sorted((pick(t, ("name", "description", "inputSchema", "outputSchema", "annotations")) for t in ts), key=lambda x: x.get("name", "")))),
}
sample = {json.loads(l)["name"]: json.loads(l) for l in open("sample.jsonl")}
sets = {json.loads(l)["digest"]: json.loads(json.loads(l)["toolsJson"]) for l in gzip.open(f"{L}/legion-toolsets.jsonl.gz", "rt")}
legion = {}
for l in open(f"{L}/legion_servers.jsonl"):
    r = json.loads(l); rec = ((r.get("doc") or {}).get("latest_record") or {})
    if rec.get("tools_fingerprint"): legion[r["name"]] = rec["tools_fingerprint"].get("sha256")
out, forms_hit, c = [], collections.Counter(), collections.Counter()
for l in open("atpp_claims.jsonl"):
    r = json.loads(l); p = r["predicate"]; s = sample[r["name"]]
    if not p:
        c["no-claim %s" % r["http"]] += 1; continue
    tools = p.get("tools") or {}
    checks = {x[0]: (x[1], x[2]) for x in p.get("checks", []) if isinstance(x, list) and len(x) >= 3}
    if not tools.get("sha256"):
        c["claim without tools"] += 1
        out.append({"name": r["name"], "verdict": "no-tools", "checks": checks}); continue
    ours = sets.get(s["toolSetDigest"]) or []
    hits = [f for f, fn in FORMS.items() if fn(ours) == tools["sha256"]]
    forms_hit.update(hits)
    v = "digest-equal" if hits else ("count-equal" if tools.get("count") == len(ours) else "count-differs")
    c[v] += 1
    out.append({"name": r["name"], "verdict": v, "forms": hits, "atppCount": tools.get("count"), "historCount": len(ours),
                "atppEqualsLegionList": legion.get(r["name"]) == tools["sha256"] if r["name"] in legion else None,
                "asOf": p.get("as_of"), "toolsStable": checks.get("tools-stable"), "historUnchangedSince": s["unchangedSince"]})
json.dump(out, open("compare.json", "w"), indent=1)
print(dict(c)); print("forms that reproduce ATPP's digest:", dict(forms_hit))
print("ATPP list digest == LEGION list digest:", collections.Counter(o.get("atppEqualsLegionList") for o in out))
print("tools-stable fails:", [(o["name"], o["toolsStable"]) for o in out if o.get("toolsStable") and not o["toolsStable"][0]][:10])
