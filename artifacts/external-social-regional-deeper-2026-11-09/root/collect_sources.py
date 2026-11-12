"""Read selected public pages; save bounded bodies and provenance. No external writes."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "gemivo-cache-churn": "https://ainews.gemivo.de/news/we-found-331-mcp-tool-list-changes-in-one-week-that-only-cmw03yqv3005",
    "gemivo-attested-memory": "https://ainews.gemivo.de/news/how-to-give-an-ai-agent-a-record-it-can-t-rewrite-cmw0rjg6p00b",
    "gemivo-about": "https://ainews.gemivo.de/mehr",
    "awr-other-codepantry": "https://agentworkreceipt.com/",
    "awr-russian-wiki": "https://wiki.aination.center/wiki/" + urllib.parse.quote("Синаполис/Agent_Tokenization_Verification_Model_v0", safe="/"),
}


def fetch(item):
    name, url = item
    row = {"name": name, "url": url, "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-public-readonly-audit/2026-11-09"})
    try:
        response = urllib.request.urlopen(req, timeout=25)
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
    path = ROOT / (name + ".raw")
    path.write_bytes(body)
    row.update(file=path.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return row


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
