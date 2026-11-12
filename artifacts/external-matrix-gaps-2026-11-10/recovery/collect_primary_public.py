"""Read only explicitly selected publisher web/raw surfaces; never GitHub REST."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
source_file = Path(sys.argv[1])
sources = json.loads(source_file.read_text())
rows = []
for source in sources:
    key, url = source["key"], source["url"]
    assert not url.startswith("https://api.github.com/")
    row = {**source, "method": "GET", "read_at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-External-Reference-Recovery/2026-11-10 (public read-only research)", "Accept": "text/html,text/plain,application/json;q=0.8,*/*;q=0.1"})
    try:
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            b = response.read(3_000_001)
            row.update(status=response.status, final_url=response.url, content_type=response.headers.get("Content-Type"),
                       bytes=len(b), truncated=len(b) > 3_000_000,
                       public_headers={k: response.headers.get(k) for k in ["Date", "Server", "Retry-After"] if response.headers.get(k)})
        p = HERE / "raw" / (key + ".raw")
        p.write_bytes(b)
        text = b.decode("utf-8", errors="replace")
        row.update(body_file=str(p.relative_to(HERE)), sha256=hashlib.sha256(b).hexdigest(),
                   challenge_shell="_cf_chl_opt" in text or "challenges.cloudflare.com" in text,
                   redirected_to_login="/login" in row["final_url"])
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error))
    rows.append(row)
(HERE / (source_file.stem + "-index.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
print(json.dumps([{k: r[k] for k in ["key", "status", "bytes", "truncated", "challenge_shell", "redirected_to_login", "error"] if k in r} for r in rows]))
