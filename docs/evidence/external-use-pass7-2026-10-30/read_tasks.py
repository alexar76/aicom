"""Capture explicit public GET tasks without credentials or remote-code execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent

def get(task):
    name, url = task
    row = {"name": name, "url": url, "method": "GET", "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (public ecosystem signal audit; read-only)",
                                          "Accept": "application/json,text/html,text/plain,*/*"}), timeout=30) as response:
            raw = response.read(15000001)
            if len(raw) > 15000000:
                raise ValueError("Capture exceeds 15 MB bound")
            row.update(status=response.status, final_url=response.url, bytes=len(raw),
                       sha256=hashlib.sha256(raw).hexdigest(), content_type=response.headers.get("Content-Type", ""))
        row["body_file"] = name + (".json" if "json" in row["content_type"] else ".raw")
        (ROOT / row["body_file"]).write_bytes(raw)
    except HTTPError as error:
        row.update(status=error.code, error=str(error))
    except Exception as error:
        row.update(status=None, error=str(error))
    return row

if __name__ == "__main__":
    scope = Path(sys.argv[1])
    tasks = json.loads(scope.read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(get, tasks))
    index_path = ROOT / ("http-" + scope.stem + "-index.json")
    index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for row in rows:
        result = {key: row.get(key) for key in ["name", "status", "error", "bytes"]}
        if row.get("body_file", "").endswith(".json"):
            data = json.loads((ROOT / row["body_file"]).read_text())
            if isinstance(data, dict) and "items" in data:
                result.update(total=data["total_count"], incomplete=data["incomplete_results"],
                              items=[{"repo": item.get("repository", {}).get("full_name", item.get("full_name")),
                                      "url": item.get("html_url"), "title": item.get("title", item.get("commit", {}).get("message", ""))[:650]}
                                     for item in data["items"]])
            elif isinstance(data, list) and row["name"].startswith("stars-"):
                result["accounts"] = [account["login"] for account in data]
        print(json.dumps(result, ensure_ascii=False))
