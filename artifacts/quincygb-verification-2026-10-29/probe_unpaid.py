"""Explicitly unsigned calls: collect HTTP 402 terms without paying."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

OUT = Path(__file__).resolve().parent
TARGET = "https://modelmarket.dev/x402/histor-check"
TASKS = [
    ("route-check-unpaid", "https://route-verdict-production.up.railway.app/v1/check", {"resource_url": TARGET}),
    ("recheck-unpaid", "https://stall-row-production.up.railway.app/v1/recheck", {"url": TARGET, "watch_id": "aimarket-independent-review-2026-10-29"}),
    ("target-unpaid", TARGET, {"name": "io.github.alexar76/warden"}),
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read(task):
    key, url, body = task
    row = {"key": key, "url": url, "method": "POST", "request": body, "payment_attached": False, "at_utc": datetime.now(timezone.utc).isoformat()}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": "aimarket-delivery-review/0.1 (+https://modelmarket.dev; unsigned probe)"}, method="POST")
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=25)
    except urllib.error.HTTPError as error:
        response = error
    except Exception as error:
        row["error"] = str(error)
        return row
    with response:
        raw = response.read(2_000_001)
        row.update(status=response.code, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), headers={k: v for k, v in response.headers.items() if k.lower() in ["content-type", "payment-required", "payment-response", "x-payment-response", "location"]})
    (OUT / (key + ".body")).write_bytes(raw)
    row["body"] = json.loads(raw) if raw.lstrip().startswith((b"{", b"[")) else raw.decode("utf-8", errors="replace")[:2000]
    for k, v in row["headers"].items():
        if k.lower() == "payment-required":
            try:
                row["payment_required_decoded"] = json.loads(base64.b64decode(v))
            except Exception as error:
                row["decode_error"] = str(error)
    return row


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(read, TASKS))
    (OUT / "unpaid-probes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for r in rows:
        d = r.get("payment_required_decoded") or r.get("body") or {}
        print(json.dumps({"key": r["key"], "status": r.get("status"), "error": r.get("error"), "accepts": d.get("accepts") if isinstance(d, dict) else None, "resource": d.get("resource") if isinstance(d, dict) else None}, ensure_ascii=False))
