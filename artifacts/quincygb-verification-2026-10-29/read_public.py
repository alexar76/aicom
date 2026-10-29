"""Public GET-only capture of the seller's declared contract."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

OUT = Path(__file__).resolve().parent
TASKS = [
    ("route-root", "https://route-verdict-production.up.railway.app/"),
    ("route-health", "https://route-verdict-production.up.railway.app/health"),
    ("route-quote", "https://route-verdict-production.up.railway.app/quote"),
    ("route-manifest", "https://route-verdict-production.up.railway.app/.well-known/x402"),
    ("route-openapi", "https://route-verdict-production.up.railway.app/openapi.json"),
    ("route-skill", "https://route-verdict-production.up.railway.app/skill.md"),
    ("stall-readme", "https://raw.githubusercontent.com/QuincyGB/stall-row/master/README.md"),
]


def read(task):
    key, url = task
    result = {"key": key, "url": url, "method": "GET", "at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "aimarket-delivery-review/0.1 (+https://modelmarket.dev)", "Accept": "application/json, text/plain, */*"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(2_000_001)
            result.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        (OUT / (key + ".body")).write_bytes(raw)
        result["preview"] = raw.decode("utf-8", errors="replace")[:1500]
    except urllib.error.HTTPError as e:
        raw = e.read(100_000)
        (OUT / (key + ".body")).write_bytes(raw)
        result.update(status=e.code, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), preview=raw.decode("utf-8", errors="replace")[:1500])
    except Exception as e:
        result.update(status=None, error=str(e))
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(read, TASKS))
    (OUT / "http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
