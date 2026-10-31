"""Verify local audit snapshots and regenerate their index; no network or code execution."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent.parent / "growth/external-use-pass5-2026-10-30.ru.md"
INDEX = ROOT / "audit-index.json"

documents = {p.name: json.loads(p.read_text()) for p in ROOT.glob("*.json")}
source_files = sorted(ROOT.glob("http-*index.json"))
sources = [row for p in source_files for row in documents[p.name]]
statuses = Counter(row["status"] for row in sources)
verified = 0
for row in sources:
    assert row["method"] == "GET", row["name"]
    if row["status"] != 200:
        assert row["status"] == 403 and row["name"] == "enterprise-backend-logs", row
        continue
    body = (ROOT / row["body_file"]).read_bytes()
    assert len(body) == row["bytes"], row["name"]
    assert hashlib.sha256(body).hexdigest() == row["sha256"], row["name"]
    verified += 1

searches = [documents[p.name] for p in sorted(ROOT.glob("search-*.json"))]
query_count = sum(len(group["queries"]) for group in searches)
summary = documents["summary.json"]
assert summary["web_queries"] == query_count
assert summary["direct_gets"] == len(sources)
assert summary["new_independent_production_deployments_confirmed"] == 0
assert all(job["conclusion"] == "success" for job in summary["finding"]["jobs"])
assert all(step["conclusion"] == "success" for job in summary["finding"]["jobs"] for step in job["selected_steps"])
assert not set(["aimarket-hub", "acex", "plugins"]) & {
    entry["path"] for entry in documents["enterprise-root-tree.json"]["tree"]
}
assert summary["response_delta"]["dev"]["new_external_added_comments"] == 0

index = {
    "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    "report": "../../growth/" + REPORT.name,
    "finding_kind": summary["finding"]["kind"],
    "event_at_utc": summary["finding"]["event_at_utc"],
    "web_search_queries": query_count,
    "direct_public_gets": len(sources),
    "statuses": {str(k): v for k, v in sorted(statuses.items())},
    "body_hashes_verified": verified,
    "json_files_parsed_before_index_write": len(documents),
    "http_index_files": [p.name for p in source_files],
    "sources": sources,
    "limitations": summary["finding"]["limits"],
    "organic_demand_from_our_paid_tests_counted": False,
}
INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")

local_links = []
for target in re.findall(r"\]\(([^)]+)\)", REPORT.read_text()):
    if "://" in target or target.startswith("#"):
        continue
    path = (REPORT.parent / target.split("#", 1)[0]).resolve()
    assert path.is_file(), target
    local_links.append(target)
print(json.dumps({"gets": len(sources), "statuses": dict(statuses),
                  "body_hashes_verified": verified, "search_queries": query_count,
                  "report_local_links_checked": len(local_links)}, indent=2))
