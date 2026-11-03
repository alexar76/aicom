"""Does LEGION's latest tool list equal one HISTOR held at some time? Classify every differing server."""
import collections, gzip, hashlib, json
import rfc8785
def per_tool(ts): return {t["name"]: hashlib.sha256(rfc8785.dumps({k: t[k] for k in ("name", "description", "inputSchema") if k in t})).hexdigest() for t in ts}
sets = {}
for f in ("legion-toolsets.jsonl.gz", "legion-toolsets2.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        d = json.loads(l); sets[d["digest"]] = per_tool(json.loads(d["toolsJson"]))
ex = json.load(open("explain.json")); hist = json.load(open("history.json"))
sample = {json.loads(l)["name"]: json.loads(l) for l in open("sample.jsonl")}
legion = {json.loads(l)["name"]: json.loads(l) for l in open("legion_servers.jsonl")}
out = collections.Counter(); rows = []
for e in ex:
    rec = legion[e["name"]]["doc"]["latest_record"]; theirs = dict(rec["tools_fingerprint"]["per_tool_sha256"])
    changes = sorted(hist.get(e["id"], []), key=lambda c: c["at"])
    # intervals: each 'to' set held from its change time until the next change; the first 'from' before that
    held = []
    if changes:
        held.append((changes[0]["from"], None, changes[0]["at"]))
        for i, c in enumerate(changes):
            held.append((c["to"], c["at"], changes[i + 1]["at"] if i + 1 < len(changes) else None))
    else:
        held.append((sample[e["name"]]["toolSetDigest"], None, None))
    match = [(d, a, b) for d, a, b in held if d in sets and sets[d] == theirs]
    current = held[-1][0]
    if match and match[-1][0] == current:
        kind = "equal-to-current (live)"          # cannot happen for differing rows unless snapshot vs live
    elif match:
        last = match[-1]
        kind = "LEGION shows an earlier HISTOR set" if (last[2] or "") <= "2026-11-02T07:20:03Z" else "other"
    elif e.get("liveEqualsLegion"):
        kind = "HISTOR caught up after the snapshot (live equals LEGION)"
    else:
        kind = "no HISTOR set equals LEGION's"
    gw = e["name"].startswith("io.github.pipeworx-io/")
    out[(("gateway " if gw else "") + kind)] += 1
    rows.append({"name": e["name"], "kind": kind, "gateway": gw, "legionLatest": rec["observed_at"],
                 "matchHeld": [m[1:] for m in match][-1:], "historChanges": len(changes), "historLastChange": changes[-1]["at"] if changes else None})
json.dump(rows, open("classified.json", "w"), indent=1)
for k, v in out.most_common(): print(v, k)
for r in rows:
    if not r["gateway"]: print(r["kind"][:40], r["name"], "L", r["legionLatest"][5:16], "Hlast", (r["historLastChange"] or "")[5:16], "held", r["matchHeld"])
