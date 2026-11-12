"""Bounded, read-only public evidence collection for the 2026-11-09 audit."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "aer": "https://agenteconomy.report/s/modelmarket.dev.json",
    "aer-page": "https://agenteconomy.report/s/modelmarket.dev",
    "aer-methodology": "https://agenteconomy.report/s/methodology",
    "x402-volume": "https://x402-list.com/api/v1/services/aimarket/volume",
    "x402-buyers": "https://x402-list.com/api/v1/services/aimarket/buyers",
    "usetested": "https://usetested.com/v1/review?service=modelmarket.dev",
    "agenstry": "https://agenstry.com/agents/modelmarket.dev",
    "agent402-index": "https://agent402.tools/api/index?seller=modelmarket.dev",
    "hub-health": "https://modelmarket.dev/ai-market/v2/health",
    "hub-stats": "https://modelmarket.dev/ai-market/v2/stats/live",
    "hub-peers": "https://modelmarket.dev/ai-market/v2/federation/peers",
    "factory-status": "https://magic-ai-factory.com/api/public/ecosystem-status",
    "agent-exec-discovery": "https://agent-exec.448c.org/.well-known/ai-market.json",
    "machina-manifest": "https://mach402.dev/ai-market/v2/manifest",
}


def fetch(item):
    name, url = item
    row = {"name": name, "url": url, "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    req = urllib.request.Request(url, headers={"User-Agent": "AICOM-readonly-evidence-audit/2026-11-09", "Accept": "application/json,text/html;q=0.8"})
    try:
        response = urllib.request.urlopen(req, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    with response:
        row["status"] = response.status
        row["final_url"] = response.url
        row["content_type"] = response.headers.get("Content-Type")
        body = response.read(5_000_001)
    if len(body) > 5_000_000:
        row["error"] = "response exceeded 5 MB limit"
        return row
    destination = ROOT / (name + ".raw")
    destination.write_bytes(body)
    row.update(file=destination.name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    return row


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(fetch, TARGETS.items()))
    (ROOT / "http-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
