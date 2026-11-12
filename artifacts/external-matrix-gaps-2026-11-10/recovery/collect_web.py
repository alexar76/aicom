"""One ordinary public GET for each prior Cloudflare-gated source; no challenge execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
rows = []
for key, url in [
    ("undercode-factory", "https://undercodenews.com/aicom-factory-just-updated-video/"),
    ("esim-socket", "https://socket.dev/npm/package/%40aimarket/esim-rails"),
]:
    row = {"key": key, "url": url, "method": "GET", "read_at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-External-Reference-Recovery/2026-11-10 (public read-only research)", "Accept": "text/html,application/json;q=0.8,*/*;q=0.1"})
    try:
        try:
            res = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            res = error
        with res:
            b = res.read(2_000_001)
            row.update(status=res.status, final_url=res.url, content_type=res.headers.get("Content-Type"), bytes=len(b),
                       truncated=len(b) > 2_000_000,
                       public_headers={k: res.headers.get(k) for k in ["Date", "Server", "cf-mitigated", "Retry-After"] if res.headers.get(k)})
        p = HERE / "raw" / (key + ".raw")
        p.write_bytes(b)
        text = b.decode("utf-8", errors="replace")
        row.update(body_file=str(p.relative_to(HERE)), sha256=hashlib.sha256(b).hexdigest(),
                   cloudflare_managed_challenge=all(s in text for s in ["Just a moment", "_cf_chl_opt", "challenges.cloudflare.com"]))
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error))
    rows.append(row)
(HERE / "web-recovery-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
print(json.dumps([{k: r.get(k) for k in ["key", "status", "bytes", "truncated", "cloudflare_managed_challenge", "error"] if k in r} for r in rows]))
