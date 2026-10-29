"""Read-only public GET observations; no announces, invokes, or approvals."""

import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import urllib.error
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent
URLS = {
    "discovery-aimarket": "https://mach402.dev/.well-known/ai-market.json",
    "discovery-x402": "https://mach402.dev/.well-known/x402",
    "manifest-fallback": "https://mach402.dev/ai-market/manifest",
    "health": "https://mach402.dev/health",
    "openapi": "https://mach402.dev/openapi.json",
    "hub-assay": "https://modelmarket.dev/ai-market/v2/federation/assay?url=https%3A%2F%2Fmach402.dev",
    "hub-peers": "https://modelmarket.dev/ai-market/v2/federation/peers",
}


def check(item):
    name, url = item
    record = {
        "url": url,
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "method": "GET",
    }
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AIMarket-integration-readonly-check/1.0",
                "Accept": "application/json",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(2_000_001)
            record.update(
                status=response.status,
                final_url=response.url,
                headers=dict(response.headers),
                body_sha256=hashlib.sha256(body).hexdigest(),
                body_truncated=len(body) > 2_000_000,
            )
            try:
                record["json"] = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                record["text"] = body[:8000].decode("utf-8", errors="replace")
    except Exception as error:
        record["error"] = str(error)
    (OUT / (name + ".json")).write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    )
    summary = {
        key: value for key, value in record.items()
        if key in ("url", "checked_at_utc", "status", "error")
    }
    if "json" in record and isinstance(record["json"], dict):
        data = record["json"]
        if name in ("discovery-aimarket", "discovery-x402", "manifest-fallback", "hub-assay", "health"):
            summary["data"] = data
        elif name == "openapi":
            summary["info"] = data.get("info")
            summary["paths"] = list(data.get("paths", {}))
        elif name == "hub-peers":
            summary["top_keys"] = list(data)
            summary["pending"] = data.get("pending")
            summary["machina"] = [
                peer for peer in data.get("peers", [])
                if peer.get("url", "").rstrip("/") == "https://mach402.dev"
            ]
    return summary


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        for result in pool.map(check, URLS.items()):
            print(json.dumps(result, ensure_ascii=False))
