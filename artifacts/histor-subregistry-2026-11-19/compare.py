"""Compare the local subregistry with the official registry, and validate answers against the registry's OpenAPI."""
import json, sys, time, urllib.parse, urllib.request
import yaml, jsonschema
OURS, THEIRS = "http://127.0.0.1:9497", "https://registry.modelcontextprotocol.io"
OFF = "io.modelcontextprotocol.registry/official"
def get(base, path, origin=None):
    req = urllib.request.Request(base + path, headers={"Accept": "application/json", "User-Agent": "subregistry-check/1", **({"Origin": origin} if origin else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"{}")
spec = yaml.safe_load(open(sys.argv[1]))
def resolver_schema(name):
    return {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
def valid(doc, name):
    errs = list(jsonschema.Draft202012Validator(resolver_schema(name)).iter_errors(doc))
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:120]}" for e in errs[:3]]
out = {}
# 1. the first 300 latest entries, page by page: same order, same server objects, same official block
same = diff = 0; cursor_o = cursor_t = None; bad_schema = []
for page in range(3):
    q = "?version=latest&limit=100"
    so, _, o = get(OURS, "/v0.1/servers" + q + (f"&cursor={urllib.parse.quote(cursor_o)}" if cursor_o else ""))
    st, _, t = get(THEIRS, "/v0.1/servers" + q + (f"&cursor={urllib.parse.quote(cursor_t)}" if cursor_t else ""))
    bad_schema += valid(o, "ServerList")
    for a, b in zip(o["servers"], t["servers"]):
        if a["server"] == b["server"] and a["_meta"][OFF] == b["_meta"][OFF]: same += 1
        else: diff += 1; out.setdefault("first_diffs", []).append([a["server"]["name"], a["server"]["version"], b["server"]["name"], b["server"]["version"]])
    cursor_o, cursor_t = o["metadata"].get("nextCursor"), t["metadata"].get("nextCursor")
    out.setdefault("cursors", []).append([cursor_o, cursor_t])
    time.sleep(0.3)
out["list_same"], out["list_diff"], out["list_schema_errors"] = same, diff, bad_schema
# 2. single lookups, encoded and plain, latest and exact
names = ["io.github.alexar76/histor", "io.github.alexar76/warden", "io.github.alexar76/aimarket-hub", "ac.inference.sh/mcp"]
single = []
for n in names:
    enc = urllib.parse.quote(n, safe="")
    so, ho, o = get(OURS, f"/v0.1/servers/{enc}/versions/latest", origin="https://vscode.dev")
    st, _, t = get(THEIRS, f"/v0.1/servers/{enc}/versions/latest")
    v = urllib.parse.quote(o["server"]["version"], safe="")
    s2, _, o2 = get(OURS, f"/v0.1/servers/{enc}/versions/{v}")
    s3, _, o3 = get(OURS, f"/v0.1/servers/{n}/versions/latest")
    s4, _, o4 = get(OURS, f"/v0.1/servers/{enc}/versions")
    single.append({"name": n, "status": [so, st, s2, s3, s4], "server_equal": o["server"] == t["server"], "official_equal": o["_meta"][OFF] == t["_meta"][OFF],
                   "exact_equal": o2 == o, "plain_equal": o3 == o, "versions_kept": o4["metadata"]["count"], "schema": valid(o, "ServerResponse") + valid(o4, "ServerList"),
                   "cors": [ho.get("access-control-allow-origin"), ho.get("access-control-allow-methods"), ho.get("access-control-allow-headers")]})
out["single"] = single
# 3. errors, search, updated_since
so, ho, o = get(OURS, "/v0.1/servers/io.github.nobody%2Fnothing/versions/latest"); st, ht, t = get(THEIRS, "/v0.1/servers/io.github.nobody%2Fnothing/versions/latest")
out["missing"] = {"ours": [so, ho.get("content-type"), o], "theirs": [st, ht.get("content-type"), t]}
so, _, o = get(OURS, "/v0.1/servers?search=alexar76&version=latest&limit=100"); st, _, t = get(THEIRS, "/v0.1/servers?search=alexar76&version=latest&limit=100")
out["search_alexar76"] = {"ours": len(o["servers"]), "theirs": len(t["servers"]), "same_names": [s["server"]["name"] for s in o["servers"]] == [s["server"]["name"] for s in t["servers"]]}
print(json.dumps(out, indent=1))
