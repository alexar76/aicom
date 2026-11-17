import json, re, subprocess, sys, os, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
S = sys.argv[1]
cands = json.load(open(os.path.join(S, "candidates.json")))
SSHISH = re.compile(r"(\.(py|sh|bash|ya?ml|toml|cfg|conf|ini|env)$|(^|/)Dockerfile[^/]*$|(^|/)ssh_config$)")
def raw(o, r, sha, path):
    url = f"https://raw.githubusercontent.com/{o}/{r}/{sha}/" + urllib.parse.quote(path)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            b = resp.read()
            return b if len(b) < 3_000_000 else None
    except Exception:
        return None
def one(a):
    out = os.path.join(S, "src", a["ghsa"])
    meta_p = os.path.join(out, "meta.json")
    if os.path.exists(meta_p):
        return
    os.makedirs(out, exist_ok=True)
    commits = []
    for link in a["commits"]:
        m = re.search(r"github\.com/([^/]+)/([^/]+)/commit/([0-9a-f]{7,40})", link)
        if m and m.groups() not in commits:
            commits.append(m.groups())
    meta = {"ghsa": a["ghsa"], "commits": []}
    for o, r, sha in commits[:3]:
        try:
            c = json.loads(subprocess.run(["gh", "api", f"repos/{o}/{r}/commits/{sha}"], capture_output=True, timeout=60, check=True).stdout)
        except Exception as e:
            meta["commits"].append({"repo": f"{o}/{r}", "sha": sha, "error": "commit not readable"}); continue
        if not c.get("parents"):
            continue
        full, parent = c["sha"], c["parents"][0]["sha"]
        files = []
        for f in c.get("files") or []:
            p = f["filename"]
            if not SSHISH.search(p):
                continue
            pre = raw(o, r, parent, p) if f["status"] != "added" else b""
            post = raw(o, r, full, p) if f["status"] != "removed" else b""
            for tag, data in (("pre", pre), ("post", post)):
                if data is not None:
                    d = os.path.join(out, full[:12], tag, os.path.dirname(p))
                    os.makedirs(d, exist_ok=True)
                    open(os.path.join(out, full[:12], tag, p), "wb").write(data)
            files.append({"path": p, "status": f["status"], "pre": pre is not None, "post": post is not None})
        meta["commits"].append({"repo": f"{o}/{r}", "sha": full, "parent": parent, "files": files})
    json.dump(meta, open(meta_p, "w"), indent=1)
with ThreadPoolExecutor(8) as ex:
    list(ex.map(one, cands))
print("done")
