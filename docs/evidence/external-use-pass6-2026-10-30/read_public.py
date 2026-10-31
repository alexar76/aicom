"""Bounded public GET-only follow-up; no credentials, installs or foreign code execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import hashlib
import json

ROOT = Path(__file__).resolve().parent
QUERIES = {
    "commits-histor-origin": ("commits", '"histor.modelmarket.dev" -user:alexar76 -author:alexar76'),
    "commits-protocol": ("commits", '"aimarket-protocol" -user:alexar76'),
    "commits-memory-identity": ("commits", '"attested-memory" "alexar76" -user:alexar76'),
    "commits-pingblip": ("commits", '"PingBlip" -user:alexar76'),
    "commits-school": ("commits", '"edu.modelmarket.dev" -user:alexar76'),
    "repos-warden-config": ("repositories", '"@aimarket/warden" in:readme fork:false -user:alexar76'),
    "repos-histor-client": ("repositories", '"histor.modelmarket.dev" in:readme fork:false -user:alexar76'),
    "repos-factory-origin": ("repositories", '"magic-ai-factory.com" in:readme fork:false -user:alexar76'),
}
TASKS = [(name, "https://api.github.com/search/" + kind + "?" + urlencode({
    "q": query, "per_page": 100, "sort": "committer-date" if kind == "commits" else "updated", "order": "desc"
})) for name, (kind, query) in QUERIES.items()]
TASKS.append(("sourcegraph-secondary-clients", "https://sourcegraph.com/search/stream?" + urlencode({
    "q": r'context:global patterntype:regexp (aimarket-metis|aimarket-symmartys|@aimarket/esim-rails|@aimarket/domain-operator-kit|aimarket-protocol|X-AIMarket-Crawler) -repo:^github.com/alexar76/ archived:yes fork:yes count:100 timeout:35s', "v": "V3"
})))

def get(task):
    name, url = task
    row = {"name": name, "url": url, "method": "GET", "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (public signal audit; read-only)", "Accept": "application/json,text/event-stream,text/plain,*/*"}), timeout=45) as response:
            raw = response.read(20000001)
            if len(raw) > 20000000:
                raise ValueError("Response exceeds 20 MB capture limit")
            row.update(status=response.status, final_url=response.url, bytes=len(raw),
                       sha256=hashlib.sha256(raw).hexdigest(), content_type=response.headers.get("Content-Type", ""))
        filename = name + (".json" if "json" in row["content_type"] else ".raw")
        (ROOT / filename).write_bytes(raw)
        row["body_file"] = filename
    except HTTPError as error:
        row.update(status=error.code, error=str(error))
    except Exception as error:
        row.update(status=None, error=str(error))
    return row

if __name__ == "__main__":
    (ROOT / "github-query-scope.json").write_text(json.dumps(QUERIES, ensure_ascii=False, indent=2) + "\n")
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(get, TASKS))
    (ROOT / "http-code-index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    for row in rows:
        out = {k: row.get(k) for k in ("name", "status", "bytes", "error")}
        if row.get("body_file", "").endswith(".json"):
            data = json.loads((ROOT / row["body_file"]).read_text())
            if isinstance(data, dict) and "items" in data:
                out.update(total_count=data.get("total_count"), incomplete_results=data.get("incomplete_results"),
                           items=[{"repo": item.get("repository", {}).get("full_name", item.get("full_name")),
                                   "url": item.get("html_url"), "title": item.get("commit", {}).get("message", "")[:500]}
                                  for item in data["items"]])
        print(json.dumps(out, ensure_ascii=False))
