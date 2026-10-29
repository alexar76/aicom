"""Capture selected public GitHub responses using unauthenticated GET only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

OUT = Path(__file__).resolve().parent
SINCE = "2026-10-28T15:00:45Z"
TASKS = [
    ("mcp3431", "https://api.github.com/repos/modelcontextprotocol/modelcontextprotocol/issues/3431/comments?per_page=100", "comments"),
    ("vulnetix5", "https://api.github.com/repos/Vulnetix/advisory-database/issues/5/comments?per_page=100", "comments"),
    ("agentmesh561", "https://api.github.com/repos/google/agentmesh/issues/561/comments?per_page=100", "comments"),
    ("skills-pr14", "https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14", "pull"),
    ("skills-pr14-comments", "https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/issues/14/comments?per_page=100", "comments"),
    ("skills-pr14-reviews", "https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14/reviews?per_page=100", "reviews"),
]


def read(task):
    key, url, kind = task
    result = {"key": key, "url": url, "method": "GET", "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    request = urllib.request.Request(url, headers={"User-Agent": "public-ecosystem-research", "Accept": "application/vnd.github+json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            result.update(status=response.status, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), next_page=response.headers.get("Link"), rate_remaining=response.headers.get("X-RateLimit-Remaining"))
        (OUT / (key + ".json")).write_bytes(raw)
        data = json.loads(raw)
        if kind in ("comments", "reviews"):
            fields = ["id", "html_url", "created_at", "updated_at", "submitted_at", "state", "body"]
            selected = [{k: row.get(k) for k in fields} | {"author": row.get("user", {}).get("login")} for row in data]
            result["visible_count"] = len(data)
            result["created_since"] = [row for row in selected if (row.get("created_at") or row.get("submitted_at") or "") > SINCE]
            result["updated_since"] = [row for row in selected if (row.get("updated_at") or "") > SINCE and (row.get("created_at") or "") <= SINCE]
            result["latest"] = selected[-2:]
        else:
            result["selected"] = {k: data.get(k) for k in ["html_url", "state", "merged", "merged_at", "updated_at", "comments", "review_comments", "merge_commit_sha"]}
            result["selected"]["head_sha"] = data.get("head", {}).get("sha")
            result["selected"]["base_sha"] = data.get("base", {}).get("sha")
    except urllib.error.HTTPError as error:
        result.update(status=error.code, error=str(error))
    except Exception as error:
        result.update(status=None, error=str(error))
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(read, TASKS))
    result = {"since_utc": SINCE, "records": records}
    (OUT / "current-response-delta.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
