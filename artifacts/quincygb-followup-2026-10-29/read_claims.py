"""Capture public response and named fix commit, GET only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

OUT = Path(__file__).resolve().parent
TASKS = [
    ("issue13-comments", "https://api.github.com/repos/alexar76/aicom/issues/13/comments?per_page=100"),
    ("route-fix-commit", "https://api.github.com/repos/QuincyGB/route-verdict/commits/5a36f74"),
]


def read(task):
    key, url = task
    row = {"key": key, "url": url, "method": "GET", "at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aimarket-review-followup/0.1", "Accept": "application/vnd.github+json"}, method="GET")
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read()
            row.update(status=response.status, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), pagination=response.headers.get("Link"))
        (OUT / (key + ".json")).write_bytes(raw)
        d = json.loads(raw)
        if isinstance(d, list):
            row["comments"] = [{"author": c.get("user", {}).get("login"), **{k: c.get(k) for k in ["html_url", "created_at", "updated_at", "body"]}} for c in d]
        else:
            row.update(sha=d.get("sha"), message=d.get("commit", {}).get("message"), date=d.get("commit", {}).get("committer", {}).get("date"), files=[{k: f.get(k) for k in ["filename", "status", "raw_url", "patch"]} for f in d.get("files", [])])
    except urllib.error.HTTPError as error:
        row.update(status=error.code, error=str(error))
    except Exception as error:
        row.update(status=None, error=str(error))
    return row


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(read, TASKS))
    (OUT / "claims-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
