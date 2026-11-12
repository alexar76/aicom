"""Bounded public GETs of newly attributable catalogue candidates; no writes to services."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "agents-shipped-python": "https://agentsshipped.com/stack/python",
    "agents-shipped-nextjs": "https://agentsshipped.com/stack/nextjs",
    "anclum-zh-mcp": "https://anclum.com/zh/f/mcp/",
}

def fetch(item):
    name, url = item
    row = {"name": name, "url": url, "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-public-readonly-links-audit/2026-11-10"})
    try:
        response = urllib.request.urlopen(req, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    with response:
        body = response.read(4_000_001)
        row.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"))
    row["capture_limit_reached"] = len(body)>4_000_000
    file = ROOT / (name + ".raw")
    file.write_bytes(body)
    row.update(file=file.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return row

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(rows,ensure_ascii=False,indent=2))
