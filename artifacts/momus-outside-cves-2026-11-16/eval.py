"""Score a scanner version on a set of advisories: per distinct fix commit, did a rule of the advisory's class fire
before the fix, and did the fix lower that count. Usage: eval.py S MOMUS_DIR SET(dev|test|all) [srcdir candidates]"""
import json, os, sys, glob
from collections import Counter
S, M, SET = sys.argv[1], sys.argv[2], sys.argv[3]
SRC = sys.argv[4] if len(sys.argv) > 4 else "src"
CANDS = sys.argv[5] if len(sys.argv) > 5 else "candidates.json"
sys.path.insert(0, M)
from momus.codescan import vulnetix_classes as vx
cands = {a["ghsa"]: a for a in json.load(open(os.path.join(S, CANDS)))}
split = json.load(open(os.path.join(S, "split.json"))) if SET != "all" else {}
CLS = {"CWE-918": "918", "CWE-306": "306", "CWE-290": "306", "CWE-348": "FWD", "CWE-322": "TLS", "CWE-295": "TLS",
       "CWE-862": "306", "CWE-287": "306"}
RULE_CLS = lambda r: ("918" if "918" in r else "306" if "306" in r else "FWD" if "FWD" in r else "TLS" if ("295" in r or "SSH" in r) else "?")
units = {}
for mp in glob.glob(os.path.join(S, SRC, "*", "meta.json")):
    m = json.load(open(mp)); g = m["ghsa"]
    if SET != "all" and split.get(g) != SET: continue
    key = tuple(sorted(c.get("sha", "") for c in m["commits"] if "files" in c))
    if key: units.setdefault(key, []).append(m)
res = Counter(); per_rule = Counter(); hits = []
for key, ms in units.items():
    classes = {CLS[c] for m in ms for c in cands[m["ghsa"]]["cwes"] if c in CLS}
    m = ms[0]; fired = Counter(); fixed = set()
    for c in m["commits"]:
        base = os.path.join(S, SRC, m["ghsa"], c.get("sha", "")[:12])
        for f in c.get("files", []):
            p = f["path"]; out = {}
            for tag in ("pre", "post"):
                fp = os.path.join(base, tag, p)
                out[tag] = vx.scan_file(p, open(fp, encoding="utf-8", errors="replace").read()) if os.path.exists(fp) else []
            for cl in classes:
                a = [x for x in out["pre"] if RULE_CLS(x.rule) == cl]; b = [x for x in out["post"] if RULE_CLS(x.rule) == cl]
                fired[cl] += len(a)
                if len(a) > len(b):
                    fixed.add(cl); per_rule.update({x.rule for x in a})
    for cl in classes:
        res[(cl, "n")] += 1; res[(cl, "fired")] += fired[cl] > 0; res[(cl, "fixed")] += cl in fixed
        if cl in fixed: hits.append((cl, ms[0]["ghsa"], cands[ms[0]["ghsa"]]["summary"][:70]))
tot = [0, 0, 0]
for cl in ("918", "306", "FWD", "TLS"):
    n, f, x = res[(cl, "n")], res[(cl, "fired")], res[(cl, "fixed")]
    tot = [tot[0] + n, tot[1] + f, tot[2] + x]
    print(f"{cl:4} units={n:3} fired={f:3} fixed={x:3}")
print(f"ALL  units={tot[0]:3} fired={tot[1]:3} fixed={tot[2]:3}  ({100*tot[2]/max(tot[0],1):.1f}% confirmed by the fix)")
print("rules behind confirmed hits:", dict(per_rule))
if os.environ.get("SHOW"):
    for h in hits: print("  ", *h)
