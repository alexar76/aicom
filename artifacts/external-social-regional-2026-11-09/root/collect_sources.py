"""Read selected public sources; no login, tool invokes or external writes."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "aiwithghost-legion": "https://aiwithghost.com/news/news-two-mcp-logs-matched-23-tools-five-days-later-every-name-had-changed/",
    "teckdeck-scraperwatch": "https://teckdeck.io/posts/we-stopped-reading-2195-mcp-servers-for-three-days-another-team-s-log-is-how-we-found-out",
    "ietf-own-message": "https://mailarchive.ietf.org/arch/msg/dawn/_bbNP5OUfVY7BpfGz0AACS0JgLw/",
    "witness-own-thread": "https://lists.witness-network.org/mailman3/hyperkitty/list/participate%40lists.witness-network.org/thread/J5ZRRQ2EQRVIFF7LL23TWMTL4AVCLYNZ/",
    "colony-candidate": "https://www.thecolony.ai/post/f4221371-7581-4dc3-a6d3-00ac9c905308",
}


def fetch(item):
    name, url = item
    row = {"name": name, "url": url, "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={"User-Agent": "AICOM-public-readonly-audit/2026-11-09"})
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
    path = ROOT / (name + ".raw")
    path.write_bytes(body)
    row.update(file=path.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return row


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
