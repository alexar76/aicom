"""Bounded public community reads: no authentication, posting or GitHub API."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
source = Path(sys.argv[1])
rows = []
for key, url in json.loads(source.read_text()):
    assert not url.startswith("https://api.github.com/")
    row = {"key": key, "url": url, "method": "GET", "read_at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-Public-Social-References-Audit/2026-11-10 (read-only research)", "Accept": "application/json,text/html,text/plain;q=0.8,*/*;q=0.1"})
    try:
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            b = response.read(2_000_001)
            row.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"),
                       bytes=len(b), truncated=len(b) > 2_000_000,
                       public_headers={k: response.headers.get(k) for k in ["Date", "Server", "Retry-After"] if response.headers.get(k)})
        p = HERE / "raw" / (key + ".raw")
        p.write_bytes(b)
        row.update(body_file=str(p.relative_to(HERE)), sha256=hashlib.sha256(b).hexdigest())
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error))
    rows.append(row)
(HERE / (source.stem + "-index.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
print(json.dumps([{k: r[k] for k in ["key", "status", "bytes", "truncated", "error"] if k in r} for r in rows]))
