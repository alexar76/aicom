import concurrent.futures
import datetime
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGES = [
    "aimarket-platon", "aimarket-oracle-core", "aimarket-logos", "aimarket-mcp",
    "aimarket-metis", "aimarket-treasury", "skopos-fleet", "aimarket-atlas",
    "aimarket-hestia", "aimarket-hub",
]
URLS = [
    (f"new-vulnetix-{n:06d}.json", f"https://raw.githubusercontent.com/Vulnetix/advisory-database/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-{n:06d}.json")
    for n in range(636, 645)
] + [(f"current-pypi-{p}.json", f"https://pypi.org/pypi/{p}/json") for p in PACKAGES]


def read(pair):
    name, url = pair
    result = {"file": name, "url": url, "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "alexar76-public-mentions-review", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            data = json.loads(body)
            result.update(status=response.status, sha256=hashlib.sha256(body).hexdigest())
        if name.startswith("current-pypi"):
            data = {"package": data["info"]["name"], "current_version": data["info"]["version"], "files": [{"filename": f["filename"], "upload_time_iso_8601": f.get("upload_time_iso_8601"), "sha256": f["digests"]["sha256"]} for f in data["urls"]]}
        (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        if name.startswith("current-pypi"):
            result.update(package=data["package"], current_version=data["current_version"], files=data["files"])
        else:
            cna = data.get("containers", {}).get("cna", {})
            result.update(metadata=data.get("cveMetadata", {}), title=cna.get("title"), affected=cna.get("affected", []), solutions=cna.get("solutions", []))
    except Exception as exc:
        result["error"] = str(exc)
    return result


with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results = list(pool.map(read, URLS))
(ROOT / "security-followups-index.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
for result in results:
    print(json.dumps(result, ensure_ascii=False))
