"""summarize_sample.py SAMPLE.jsonl — counts for the two-era sample."""
import collections, json, sys

rows = [json.loads(l) for l in open(sys.argv[1])]
pair = [r for r in rows if r.get("modern", {}).get("digest", "").startswith("sha256-") and r.get("handshake", {}).get("digest", "").startswith("sha256-")]
diff = [r for r in pair if r["modern"]["digest"] != r["handshake"]["digest"]]
no_modern = [r for r in rows if "error" in r.get("modern", {}) and r.get("handshake", {}).get("digest", "").startswith("sha256-")]
no_hs = [r for r in rows if r.get("modern", {}).get("digest", "").startswith("sha256-") and "error" in r.get("handshake", {})]
neither = [r for r in rows if r not in pair and r not in no_modern and r not in no_hs]
print(f"servers read: {len(rows)}; both eras digested: {len(pair)}; same digest: {len(pair)-len(diff)}; different: {len(diff)}"
      f" ({100*len(diff)/max(1,len(pair)):.1f}%)")
print(f"modern only (handshake refused or failed): {len(no_hs)}; handshake only: {len(no_modern)}; neither: {len(neither)}")
kinds = collections.Counter()
for r in diff:
    d = r.get("differ", {})
    key = []
    if d.get("only_modern") or d.get("only_handshake"): key.append("different tool names")
    for k in ("description", "inputSchema", "outputSchema"):
        if d.get("members", {}).get(k): key.append(k)
    kinds[" + ".join(key) or "other"] += 1
for k, n in kinds.most_common(): print(f"   {n:3}  {k}")
neg = collections.Counter(r["handshake"].get("negotiated") for r in pair)
print("handshake answered as:", dict(neg))
print("handshake errors where modern worked:", collections.Counter((r["handshake"]["error"] or "")[:50] for r in no_hs).most_common(5))
