"""Two numbers for the Security IG post, from HISTOR snapshot 2026-11-02 (doi:10.5281/zenodo.23884408)."""
import gzip, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

d = Path(sys.argv[1])
m = json.loads((d / "manifest.json").read_text())
files = m["files"]
for name in ("changes.jsonl.gz", "extras_changes.jsonl.gz", "servers.jsonl.gz"):
    want = files[name] if isinstance(files, dict) else None
    got = "sha256-" + __import__("base64").b64encode(hashlib.sha256((d / name).read_bytes()).digest()).decode()
    got_hex = hashlib.sha256((d / name).read_bytes()).hexdigest()
    print(name, "manifest:", json.dumps(want)[:120], "| ours:", got[:30], got_hex[:16])

def rows(name):
    with gzip.open(d / name, "rt") as f:
        for line in f:
            yield json.loads(line)

servers = {s["id"]: s for s in rows("servers.jsonl.gz")}
kind = lambda sid: "package" if str(servers.get(sid, {}).get("endpoint", "")).startswith(("npm:", "pypi:")) else "remote"
host = lambda sid: urlsplit(servers[sid]["endpoint"]).hostname if kind(sid) == "remote" else servers.get(sid, {}).get("endpoint")

n = Counter(); same = Counter(); known = Counter(); desc_only = Counter(); full = Counter()
srv_changed = defaultdict(set); srv_same = defaultdict(set); hosts_changed = set(); hosts_same = set()
for c in rows("changes.jsonl.gz"):
    k = kind(c["serverId"]); n[k] += 1
    s = json.loads(c["summaryJson"])
    srv_changed[k].add(c["serverId"])
    if k == "remote": hosts_changed.add(host(c["serverId"]))
    fv, tv = c.get("fromServerVersion"), c.get("toServerVersion")
    if fv is not None and tv is not None:
        known[k] += 1
        if fv == tv:
            same[k] += 1; srv_same[k].add(c["serverId"])
            if k == "remote": hosts_same.add(host(c["serverId"]))
    if s.get("detail", "full") == "full":
        full[k] += 1
        if not s["added"] and not s["removed"] and s["modified"] and all(list(x["fields"]) == ["description"] for x in s["modified"]):
            desc_only[k] += 1
extras = Counter(kind(c["serverId"]) for c in rows("extras_changes.jsonl.gz"))
print("servers in snapshot:", len(servers), Counter(kind(i) for i in servers))
for k in ("remote", "package"):
    print(f"{k}: changes {n[k]}, with both server versions {known[k]}, at an unchanged serverInfo.version {same[k]}"
          f" ({same[k]/max(known[k],1):.1%}); servers with a change {len(srv_changed[k])}, of them with one at an unchanged version"
          f" {len(srv_same[k])} ({len(srv_same[k])/max(len(srv_changed[k]),1):.1%}); description-only {desc_only[k]}/{full[k]};"
          f" extras changes {extras[k]}")
print("remote hosts with a change", len(hosts_changed), "with one at an unchanged version", len(hosts_same),
      f"({len(hosts_same)/max(len(hosts_changed),1):.1%})")
print("total changes", sum(n.values()))

# Per host (remote): one publisher must not stand for thousands of changes.
per_host = Counter(); desc_hosts = set(); extra_hosts = set()
for c in rows("changes.jsonl.gz"):
    if kind(c["serverId"]) != "remote":
        continue
    h = host(c["serverId"]); per_host[h] += 1
    s = json.loads(c["summaryJson"])
    if s.get("detail", "full") == "full" and not s["added"] and not s["removed"] and s["modified"] \
            and all(list(x["fields"]) == ["description"] for x in s["modified"]):
        desc_hosts.add(h)
for c in rows("extras_changes.jsonl.gz"):
    if kind(c["serverId"]) == "remote":
        extra_hosts.add(host(c["serverId"]))
top = per_host.most_common(3)
print("top hosts by remote changes:", [(h[:40], k, f"{k/sum(per_host.values()):.1%}") for h, k in top])
print("remote hosts with a description-only change:", len(desc_hosts), f"of {len(hosts_changed)} ({len(desc_hosts)/len(hosts_changed):.1%})")
print("remote hosts with an extras change:", len(extra_hosts), "; of them never a contract change:", len(extra_hosts - hosts_changed))
remote_hosts_all = {host(i) for i in servers if kind(i) == "remote"}
print("remote hosts in snapshot:", len(remote_hosts_all))
