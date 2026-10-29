"""Capture public API rows for the fixed October 20 cohort; no production writes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import time
import urllib.request

ROOT = Path(__file__).parent
OUT = ROOT / "api-pages"
OUT.mkdir(exist_ok=True)
FIELDS = ("id", "target_id", "observed_at", "from_server_version", "to_server_version",
          "from_registry_version", "to_registry_version", "endpoint", "name")

def fetch(before):
    path = OUT / f"before-{before}.json.gz"
    if path.exists():
        with gzip.open(path, "rt") as f:
            return json.load(f)["changes"]
    url = f"https://histor.modelmarket.dev/api/v1/changes?limit=200&before={before}"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HISTOR-independent-review/1", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            data = json.loads(raw)
            with gzip.open(path, "wt") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            return data["changes"]
        except Exception:
            if attempt == 4:
                raise
            time.sleep(1 + attempt)

rows = {}
boundaries = list(range(23822, 1, -200))
with ThreadPoolExecutor(max_workers=4) as pool:
    tasks = {pool.submit(fetch, before): before for before in boundaries}
    for n, future in enumerate(as_completed(tasks), 1):
        for row in future.result():
            if 1 <= row["id"] <= 23821:
                rows[row["id"]] = {key: row.get(key) for key in FIELDS}
        if n % 20 == 0:
            print(json.dumps({"pages": n, "of": len(tasks), "rows": len(rows)}), flush=True)
assert set(rows) == set(range(1, 23822)), (len(rows), sorted(set(range(1, 23822)) - rows.keys())[:20])
path = ROOT / "live-version-pairs.jsonl.gz"
with gzip.open(path, "wt") as f:
    for key in sorted(rows):
        f.write(json.dumps(rows[key], ensure_ascii=False, separators=(",", ":")) + "\n")
print(json.dumps({"capturedAt": datetime.now(timezone.utc).isoformat(), "rows": len(rows),
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "path": str(path)}), flush=True)
