"""Why PyPI and npm differ: read the declared SDK dependency of a random sample of packages.

For 300 PyPI and 300 npm registry entries drawn at random (seed below) from the entries the sandbox
read under observer 5, fetch the metadata of the exact version that ran and classify how it depends
on an MCP SDK. Nothing is installed or executed; only registry metadata is read.

Usage: python3 -B sample_dependencies.py package_observations.jsonl.gz servers.jsonl.gz > data/dependency_sample.json
"""
import collections, concurrent.futures, gzip, json, random, re, sys, urllib.parse, urllib.request

SEED, PER_REGISTRY, MODERN = 20261126, 300, "2026-07-28"
UA = {"User-Agent": "histor-protocol-count/1 (+https://histor.modelmarket.dev; metadata read only)"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return json.load(r)
    except Exception as exc:  # 404 for a yanked version, etc.
        return {"_error": str(exc)[:80]}


def spec_of(requires, name):
    for r in requires or []:
        if ";" in r and "extra ==" in r.split(";", 1)[1]:
            continue
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(\[[^\]]*\])?\s*(.*?)\s*(;.*)?$", r)
        if m and re.sub(r"[-_.]+", "-", m.group(1)).lower() == name:
            return m.group(3).strip("() ") or "(any)"
    return None


def capped_below(spec, major):
    """True when the specifier cannot resolve to `major` or later."""
    if spec in (None, "(any)"):
        return False
    for part in spec.split(","):
        part = part.strip()
        m = re.match(r"(<=|<|==|~=)\s*v?(\d+)(?:\.(\d+))?", part)
        if not m:
            continue
        op, maj = m.group(1), int(m.group(2))
        if op == "<" and (maj < major or (maj == major and not m.group(3))):
            return True
        if op == "<" and maj == major and m.group(3) == "0":
            return True
        if op in ("<=", "==", "~=") and maj < major:
            return True
    return False


def pypi(name, version):
    d = get(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json")
    if "_error" in d:
        return "metadata not available", None
    req = d.get("info", {}).get("requires_dist") or []
    uploaded = min((u["upload_time_iso_8601"] for u in d.get("urls") or []), default=None)
    mcp, fast = spec_of(req, "mcp"), spec_of(req, "fastmcp")
    if mcp is not None:
        return ("mcp, capped below 2" if capped_below(mcp, 2) else "mcp, 2.x allowed"), uploaded
    if fast is not None:
        return ("fastmcp, capped below 4" if capped_below(fast, 4) else "fastmcp, 4.x allowed"), uploaded
    return "no direct mcp or fastmcp dependency", uploaded


def npm(name, version):
    d = get(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/{urllib.parse.quote(version)}")
    if "_error" in d:
        return "metadata not available", None
    deps = {**(d.get("dependencies") or {}), **(d.get("peerDependencies") or {})}
    if any(k in deps for k in ("@modelcontextprotocol/server", "@modelcontextprotocol/core")):
        return "@modelcontextprotocol/server or core (2.x)", None
    if "@modelcontextprotocol/sdk" in deps:
        return "@modelcontextprotocol/sdk (1.x line)", None
    return "no direct dependency on the official SDK", None


if __name__ == "__main__":
    obs_path, servers_path = sys.argv[1:3]
    endpoint = {}
    with gzip.open(servers_path, "rt", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            endpoint[s["id"]] = s.get("endpoint") or ""
    latest = {}
    with gzip.open(obs_path, "rt", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if o["status"] != "ok" or o.get("protocolVersion") in (None, "None") or o.get("packageVersion") in (None, "None"):
                continue
            try:
                launch = json.loads(o["launchJson"])
            except (TypeError, ValueError):
                continue
            if str(launch.get("observer")) == "5":
                latest[o["serverId"]] = (o["protocolVersion"], o["packageVersion"])
    rng = random.Random(SEED)
    out = {"seed": SEED, "perRegistry": PER_REGISTRY}
    for reg, fn in (("pypi", pypi), ("npm", npm)):
        ids = sorted(i for i in latest if endpoint.get(i, "").startswith(reg + ":"))
        picked = rng.sample(ids, PER_REGISTRY)
        jobs = [(i, endpoint[i].split(":", 1)[1], latest[i][1], latest[i][0]) for i in picked]
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            kinds = list(pool.map(lambda j: fn(j[1], j[2]), jobs))
        table = collections.defaultdict(collections.Counter)
        rows = []
        for (i, name, version, proto), (kind, uploaded) in zip(jobs, kinds):
            table[kind]["modern" if proto == MODERN else "legacy"] += 1
            rows.append({"id": i, "package": name, "version": version, "protocol": proto, "dependency": kind,
                         "uploaded": uploaded})
        out[reg] = {"population": len(ids), "table": {k: dict(v) for k, v in sorted(table.items())}, "rows": rows}
    json.dump(out, sys.stdout, indent=1)
    print()
