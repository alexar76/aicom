"""Run histor/peer_xcheck.py on the exports saved here and compare with the hand-made results of 2026-11-01.

usage (from the repository root): histor/.venv/bin/python artifacts/scraperwatch-xcheck-2026-11-01/module_check.py
"""
import collections
import gzip
import json
import pathlib
import sys
from urllib.parse import urlsplit

A = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(A.parents[1] / "histor"))
from histor import peer_xcheck as px  # noqa: E402

rows = []
for f in ("histor-export.jsonl.gz", "reverse/histor-panel-changes.jsonl.gz", "reverse/histor-reads.jsonl.gz",
          "reverse/histor-blobs.jsonl.gz"):
    rows += [json.loads(l) for l in gzip.open(A / f, "rt") if l.startswith("{")]
targets = {r["id"]: r for r in rows if r["k"] == "target"}
obs = collections.defaultdict(dict)
for r in rows:
    if r["k"] == "obs" and r["status"] == "ok":
        obs[r["target_id"]][r["observed_at"]] = r
blobs = {r["digest"]: json.loads(r["body"]) for r in rows if r["k"] == "blob"}
changes = {(r["target_id"], r["observed_at"], r["k"]): {"target_id": r["target_id"], "observed_at": r["observed_at"],
                                                         "kind": "tools" if r["k"] == "change" else "extras"}
           for r in rows if r["k"] in ("change", "xchange")}
data = px.Data(list(targets.values()),
               lambda ids, s, e: [o for i in ids for t, o in obs.get(i, {}).items() if s <= t <= e],
               lambda ids, s, e: [c for c in changes.values() if c["target_id"] in set(ids) and s < c["observed_at"] <= e],
               lambda ds: {d: blobs[d] for d in ds if d in blobs})
doc = json.load(open(A / "changes.json"))
panel = [l.strip() for l in open(A / "reverse/panel.txt") if l.strip() and not l.startswith("#")]
texts = json.load(open(A / "reverse/robots.json"))
res = px.compare(data, doc, panel, ["2026-10-31", "2026-11-01"],
                 lambda u: px.robots_allows(texts.get(urlsplit(u).hostname), u, px.PEER["agent"]))

hand_fwd = json.load(open(A / "results.json"))["summary"]
hand_rev = json.load(open(A / "reverse/reverse.json"))
print("forward module:", res["forward"]["verdicts"], res["forward"]["itemsSeenByHistor"], "/", res["forward"]["items"])
print("forward by hand:", hand_fwd["verdicts"], hand_fwd["items_seen_by_histor"], "/", hand_fwd["items"])
print("reverse module:", res["reverse"]["endpointDaysWithHistorChange"], res["reverse"]["alsoInPeerLog"],
      res["reverse"]["notInPeerLog"], json.dumps(res["reverse"]["why"]))
print("reverse by hand:", hand_rev["pairsWithHistorChange"], hand_rev["alsoInScraperWatch"], hand_rev["notInScraperWatch"],
      json.dumps(hand_rev["why"]))
mod = {(r["endpoint"], r["day"]) for r in res["reverse"]["rows"]}
man = {(r["endpoint"], r["day"]) for r in hand_rev["all"]}
print("rows only by hand:", sorted(man - mod), "| rows only in module:", sorted(mod - man))
print("likely misses:", [(m["endpoint"], m["day"]) for m in res["reverse"]["likelyMisses"]])
same = (res["forward"]["verdicts"] == hand_fwd["verdicts"] and res["reverse"]["notInPeerLog"] == hand_rev["notInScraperWatch"]
        and mod == man)
print("MATCH" if same else "DIFFERS")
sys.exit(0 if same else 1)
