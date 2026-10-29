"""Read-only, bounded checks of the public hub operator recruitment path.

No credentials, paid calls, federation announcements, or remote writes.
Run from any directory. Output is stored beside this script.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

URLS = (
    "https://modelmarket.dev/.well-known/ai-market.json",
    "https://modelmarket.dev/ai-market/v2/stats/live",
    "https://modelmarket.dev/ai-market/v2/federation/peers",
    "https://verify.modelmarket.dev/demand.json",
    "https://pypi.org/pypi/aimarket-hub/json",
    "https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md",
    "https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.ru.md",
    "https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/operator-quickstart.md",
    "https://raw.githubusercontent.com/alexar76/aimarket-hub/main/docs/operator-quickstart.ru.md",
)
MAX_BYTES = 2_000_000


def check(url):
    item = {"url": url, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={"User-Agent": "aicom-operator-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read(MAX_BYTES + 1)
            item.update(status=response.status, final_url=response.url,
                        content_type=response.headers.get("Content-Type"), bytes=len(body))
        if len(body) > MAX_BYTES:
            item["error"] = "body_exceeds_limit"
            return item
        item["sha256"] = hashlib.sha256(body).hexdigest()
        if "raw.githubusercontent.com" in url:
            content = body.decode("utf-8")
            item["guide_checks"] = {
                "has_quickstart": "aimarket quickstart" in content,
                "has_doctor": "aimarket doctor" in content,
                "has_own_api_command": "aimarket add" in content,
            }
        elif "github.com" in url:
            item["has_guide_path"] = b"operator-quickstart" in body
        else:
            data = json.loads(body)
            if "pypi.org" in url:
                info = data["info"]
                item["data"] = {key: info.get(key) for key in
                                ("version", "requires_python", "license_expression")}
            elif "/.well-known/" in url:
                item["data"] = {key: data.get(key) for key in
                                ("name", "hub_version", "capabilities_count",
                                 "federated_capabilities_count", "mcp_endpoint", "free_trial")}
            else:
                item["data"] = data
    except urllib.error.HTTPError as error:
        item.update(status=error.code, error=str(error))
    except Exception as error:
        item["error"] = str(error)
    return item


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, URLS))
    output = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Unauthenticated HTTP GET only; no invokes, payments, or announcements",
        "checks": results,
    }
    destination = Path(__file__).with_name("public-entrypoints.json")
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for result in results:
        print(json.dumps({key: value for key, value in result.items() if key != "data"},
                         ensure_ascii=False))
    print(f"Saved {destination}")
