import concurrent.futures, datetime, hashlib, io, json, urllib.request, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PACKAGES = ["aimarket-mcp", "skopos-fleet", "aimarket-platon", "aimarket-oracle-core", "aimarket-logos", "aimarket-metis", "aimarket-treasury", "aimarket-atlas", "aimarket-hestia"]
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "alexar76-local-security-review", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response: return response.read()
def inspect(name):
    try:
        data = json.loads(get("https://pypi.org/pypi/" + name + "/json"))
        wheels = [f for f in data["urls"] if f["filename"].endswith(".whl")]
        out = {"package": name, "version": data["info"]["version"], "wheels": [{k: f[k] for k in ("filename", "url", "upload_time_iso_8601", "digests")} for f in wheels]}
        (ROOT / (name + "-pypi.json")).write_text(json.dumps(out, indent=2) + "\n")
        return out
    except Exception as exc: return {"package": name, "error": type(exc).__name__ + ": " + str(exc)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: results = list(pool.map(inspect, PACKAGES))
summary = {"observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "packages": results}
(ROOT / "registry-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
try:
    comment = json.loads(get("https://api.github.com/repos/Vulnetix/advisory-database/issues/comments/6455496971"))
    out = {k: comment.get(k) for k in ("html_url", "created_at", "updated_at", "body")}
    (ROOT / "vulnetix-comment.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("html_url", "created_at", "updated_at")}))
except Exception as exc: print("Comment read error:", type(exc).__name__, str(exc))
