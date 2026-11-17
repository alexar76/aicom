import json, os, sys, glob
from collections import Counter, defaultdict
S, M = sys.argv[1], sys.argv[2]
sys.path.insert(0, M)
from momus.codescan import vulnetix_classes as vx
cands = {a["ghsa"]: a for a in json.load(open(os.path.join(S, "candidates.json")))}
CLASS = {"CWE-918": {"VX-918-CHECK-THEN-CONNECT", "VX-918-UNPINNED-RETURN"},
         "CWE-306": {"VX-306-OPEN-WITHOUT-KEY"}, "CWE-290": {"VX-306-OPEN-WITHOUT-KEY", "VX-FWD-HEADER-TRUST"},
         "CWE-348": {"VX-FWD-HEADER-TRUST"}, "CWE-322": {"VX-SSH-NO-HOSTKEY"}, "CWE-295": {"VX-SSH-NO-HOSTKEY"}}
def scan(path, text):
    try:
        return vx.scan_file(path, text)
    except Exception as e:
        return None
rows = []
for meta_p in glob.glob(os.path.join(S, "src", "*", "meta.json")):
    meta = json.load(open(meta_p)); a = cands[meta["ghsa"]]
    want = set().union(*[CLASS.get(c, set()) for c in a["cwes"]]) if a["cwes"] else set()
    r = dict(ghsa=a["ghsa"], cve=a["cve"], cwes=a["cwes"], pkg=a["pkg"], published=a["published"][:10],
             repos=[], py_files=0, pre_any=0, pre_class=0, fixed_class=0, post_class=0, parse_err=0, rules_pre=Counter(), details=[])
    for c in meta["commits"]:
        if "files" not in c: continue
        r["repos"].append(c["repo"])
        base = os.path.join(S, "src", meta["ghsa"], c["sha"][:12])
        for f in c["files"]:
            p = f["path"]
            if p.endswith(".py"): r["py_files"] += 1
            res = {}
            for tag in ("pre", "post"):
                fp = os.path.join(base, tag, p)
                if os.path.exists(fp):
                    fs = scan(p, open(fp, encoding="utf-8", errors="replace").read())
                    if fs is None: r["parse_err"] += 1; fs = []
                    res[tag] = fs
            pre, post = res.get("pre", []), res.get("post", [])
            r["pre_any"] += len(pre)
            for x in pre: r["rules_pre"][x.rule] += 1
            pc = [x for x in pre if x.rule in want]; qc = [x for x in post if x.rule in want]
            r["pre_class"] += len(pc); r["post_class"] += len(qc)
            if len(pc) > len(qc): r["fixed_class"] += 1
            for x in pre: r["details"].append(f"{c['repo']}:{p}:{x.line} {x.rule} {getattr(x,'function','')}")
    r["rules_pre"] = dict(r["rules_pre"]); rows.append(r)
json.dump(rows, open(os.path.join(S, "results.json"), "w"), indent=1)
inscope = [r for r in rows if r["py_files"] > 0]
print("advisories:", len(rows), "| fix commit touches Python:", len(inscope))
for cwe in ["CWE-918", "CWE-306", "CWE-290", "CWE-348", "CWE-322", "CWE-295"]:
    g = [r for r in inscope if cwe in r["cwes"]]
    print(f"{cwe}: {len(g)} | class rule fired on pre-fix: {sum(1 for r in g if r['pre_class'])} | fired AND fix removed it: {sum(1 for r in g if r['fixed_class'])} | any rule pre: {sum(1 for r in g if r['pre_any'])}")
print("any-rule hits by rule:", Counter(k for r in inscope for k in r["rules_pre"]))
print("parse errors:", sum(r["parse_err"] for r in rows))
