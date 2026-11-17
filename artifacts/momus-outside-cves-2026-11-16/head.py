import json, os, sys, urllib.request, urllib.parse, subprocess
S, M = sys.argv[1], sys.argv[2]; sys.path.insert(0, M)
from momus.codescan import vulnetix_classes as vx
rows = json.load(open(os.path.join(S, "results.json")))
targets = {}
for r in rows:
    for d in r["details"]:
        loc = d.split(" ")[0]; repo, path, _ = loc.split(":", 2)
        targets[(repo, path)] = 1
for repo, path in sorted(targets):
    br = json.loads(subprocess.run(["gh","api",f"repos/{repo}"],capture_output=True).stdout or b"{}").get("default_branch","main")
    url = f"https://raw.githubusercontent.com/{repo}/{br}/" + urllib.parse.quote(path)
    try:
        src = urllib.request.urlopen(url, timeout=30).read().decode("utf-8","replace")
    except Exception:
        print(f"{repo}:{path}  (gone at {br})"); continue
    d = os.path.join(S, "head", repo.replace("/","__")); os.makedirs(os.path.dirname(os.path.join(d,path)), exist_ok=True)
    open(os.path.join(d,path),"w").write(src)
    fs = vx.scan_file(path, src)
    print(f"{repo}:{path} @{br}: " + ("; ".join(f"{f.rule}@{f.line} {getattr(f,'function','')}" for f in fs) or "clean"))
