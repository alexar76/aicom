"""Capture public reference sources; stop GitHub searches on any limit response."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent


def fetch(key, url):
    row = {"key": key, "url": url, "method": "GET", "observed_at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-Component-References-Audit/2026-11-10 (public read-only research)", "Accept": "application/vnd.github+json,application/json,text/html,text/plain;q=0.8,*/*;q=0.1"})
    try:
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read(2_000_001)
            row.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"),
                       bytes=len(data), truncated=len(data) > 2_000_000,
                       public_rate_headers={k: response.headers.get(k) for k in ["X-RateLimit-Remaining", "X-RateLimit-Reset", "X-RateLimit-Resource", "Retry-After"] if response.headers.get(k) is not None})
        path = HERE / "raw" / (key + ".raw")
        path.write_bytes(data)
        row.update(body_file=str(path.relative_to(HERE)), sha256=hashlib.sha256(data).hexdigest())
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error))
    return row


if __name__ == "__main__":
    p = Path(sys.argv[1])
    items = json.loads(p.read_text())
    rows = []
    stop_searches = False
    for key, url in items:
        is_search = url.startswith("https://api.github.com/search/")
        if is_search and stop_searches:
            rows.append({"key": key, "url": url, "not_requested": True, "reason": "GitHub search rate limit or access failure earlier in batch; no retry or bypass."})
            continue
        row = fetch(key, url)
        rows.append(row)
        if is_search and row.get("status") in {403, 429}:
            stop_searches = True
        if key == "github-rate-limit" and row.get("status") == 200:
            r = json.loads((HERE / row["body_file"]).read_text())
            if r.get("resources", {}).get("search", {}).get("remaining") == 0:
                stop_searches = True
    (HERE / (p.stem + "-http-index.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([{k: r[k] for k in ["key", "status", "bytes", "truncated", "not_requested", "error"] if k in r} for r in rows]))
