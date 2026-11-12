"""Read-only bounded captures of selected public review/discussion sources."""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent

SOURCES = [
    ("dangmua-threads", "https://dangmua.com/blog/claude-message-threads-beta-cuts-request-size-not-your-bill"),
    ("dangmua-blog", "https://dangmua.com/blog"),
    ("dangmua-about", "https://dangmua.com/about"),
    ("scraperwatch-changes", "https://scraperwatch.com/mcp-changes/"),
    ("scraperwatch-home", "https://scraperwatch.com/"),
    ("fplcat-agents", "https://fplcat.com/blog/ai-agents-playing-fantasy-premier-league"),
    ("fplcat-blog", "https://fplcat.com/blog"),
    ("hlido-passport", "https://hlido.eu/passport/alexar76-aimarket-plugins/"),
    ("quincygb-articles", "https://dev.to/api/articles?username=quincygb&per_page=100"),
    ("martin-articles", "https://dev.to/api/articles?username=martinpisacreta&per_page=100"),
    ("paul-articles", "https://dev.to/api/articles?username=paul_irolla_6b5ae261d0224&per_page=100"),
    ("agentembassy-articles", "https://dev.to/api/articles?username=agentembassy&per_page=100"),
    ("hn-modelmarket-comments", "https://hn.algolia.com/api/v1/search_by_date?query=%22modelmarket.dev%22&tags=comment&hitsPerPage=100"),
    ("hn-alexar76-comments", "https://hn.algolia.com/api/v1/search_by_date?query=%22alexar76%22&tags=comment&hitsPerPage=100"),
    ("dev-comments-marketplace", "https://dev.to/api/comments?a_id=4951998"),
    ("dev-comments-x402", "https://dev.to/api/comments?a_id=4804987"),
    ("dev-comments-histor-comparison", "https://dev.to/api/comments?a_id=4954137"),
]


def fetch(item):
    key, url = item
    result = {"key": key, "url": url, "method": "GET", "observed_at_utc": datetime.now(timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={"User-Agent": "AICOM-External-References-Audit/2026-11-10 (public read-only research)", "Accept": "text/html,application/json,text/plain;q=0.9,*/*;q=0.1"})
    try:
        try:
            response = urllib.request.urlopen(request, timeout=18)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(1_500_001)
            result.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"),
                          captured_bytes=len(body), truncated=len(body) > 1_500_000)
        path = HERE / "raw" / (key + ".raw")
        path.write_bytes(body)
        result.update(body_file=str(path.relative_to(HERE)), sha256=hashlib.sha256(body).hexdigest())
    except Exception as error:
        result.update(error=str(error), error_type=type(error).__name__)
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sources = json.loads(Path(sys.argv[1]).read_text())
        suffix = Path(sys.argv[1]).stem
        workers = 1
    else:
        sources = SOURCES
        suffix = "initial"
        workers = 3
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(fetch, sources))
    (HERE / ("http-" + suffix + "-index.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([{k: r.get(k) for k in ["key", "status", "captured_bytes", "truncated", "error"] if k in r} for r in rows], ensure_ascii=False))
