"""Read public growth/activation surfaces; no customer records, paid calls or external writes."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "hub-live-stats": "https://modelmarket.dev/ai-market/v2/stats/live",
    "ecosystem-status": "https://magic-ai-factory.com/api/public/ecosystem-status",
    "histor-watch": "https://histor.modelmarket.dev/watch",
    "histor-watch-plan": "https://histor.modelmarket.dev/api/v1/watch/plan",
}

def fetch(item):
    name, url = item
    row = {"name": name, "url": url, "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={"User-Agent": "AICOM-public-readonly-growth-audit/2026-11-09"})
    try:
        response = urllib.request.urlopen(request, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    with response:
        body = response.read(2_000_001)
        row.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"))
    if len(body) > 2_000_000:
        row["error"] = "response exceeded 2 MB limit"
        return row
    file = ROOT / (name + ".raw")
    file.write_bytes(body)
    row.update(file=file.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return row

if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-index.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))
