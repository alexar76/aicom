"""Verify public captures, derive scoped findings and rebuild indexes locally."""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
REPORT = REPO / "docs/growth/external-use-pass8-2026-10-30.ru.md"
docs = {path.name: json.loads(path.read_text()) for path in ROOT.glob("*.json")}
sources = [row for path in sorted(ROOT.glob("http-*index.json")) for row in docs[path.name]]
by_name = {row["name"]: row for row in sources}
for source in sources:
    assert source["method"] == "GET" and source["status"] == 200, source
    raw = (ROOT / source["body_file"]).read_bytes()
    assert len(raw) == source["bytes"]
    assert hashlib.sha256(raw).hexdigest() == source["sha256"], source["name"]

def body(name):
    return (ROOT / by_name[name]["body_file"]).read_text()

data = json.loads(body("shortformkit-data"))
expected = {"https://hub.attestedmemory.net/mcp": 13,
            "https://modelmarket.dev/tools/mcp/emporion": 8,
            "https://modelmarket.dev/tools/mcp/weather": 3}
observations = [row for row in data["servers"] if row["url"] in expected]
assert len(observations) == 3 and data["tested"] == "2026-10-26"
assert all(row["tools"] == expected[row["url"]] for row in observations)
assert all(len(row["tool_names"]) == row["tools"] for row in observations)
assert all("hub.attestedmemory.net/mcp" in body("shortformkit-" + lang) for lang in ["page", "ja", "ko"])

# Parse foreign source as text/AST; never import or execute it.
methods = set()
for node in ast.walk(ast.parse(body("shortformkit-probe"))):
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "method" and isinstance(value, ast.Constant):
                methods.add(value.value)
assert methods == {"initialize", "notifications/initialized", "tools/list"}, methods
assert 'if p["status"] == "open"' in body("shortformkit-build-directory")
assert "continue-on-error" not in body("shortformkit-workflow")
jobs = json.loads(body("shortformkit-run-jobs"))["jobs"]
assert len(jobs) == 1 and jobs[0]["conclusion"] == "success"
steps = [step for step in jobs[0]["steps"] if step["name"].startswith(("Fetch the registry", "Test every remote", "Build data"))]
assert len(steps) == 3 and all(step["conclusion"] == "success" for step in steps)
output = json.loads(body("shortformkit-output-commit"))
assert {file["filename"] for file in output["files"]} == {"README.md", "data/servers.csv", "data/servers.json"}

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.extend(value for key, value in attrs if key == "href")

article = Links()
article.feed(body("education-article"))
course_url = "https://github.com/alexar76/aimarket-courses/tree/main/orchestration-course"
assert course_url in article.urls
assert "September 22, 2026" in body("education-article") or "2026-09-22" in body("education-article")

graphs = [row for row in sources if row["name"].startswith("deps-")]
assert len(graphs) == 16
assert all(json.loads(body(row["name"]))["totalCount"] == 0 for row in graphs)
package_scope = docs["package-scope.json"]
for row in package_scope["selected"]:
    assert hashlib.sha256((REPO / row["manifest"]).read_bytes()).hexdigest() == row["manifest_sha256"]

prior_queries = set()
prior_json_files = 0
novelty = {"shortformkit_website_or_repository": [], "shortformkit_client_name_only": [], "education_article": []}

def query_strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ["q", "query"] and isinstance(item, str):
                prior_queries.add(item.strip())
            elif key in ["queries", "web_queries", "search_queries"] and isinstance(item, list):
                for row in item:
                    if isinstance(row, str):
                        prior_queries.add(row.strip())
                    else:
                        query_strings(row)
            elif isinstance(item, (list, dict)):
                query_strings(item)
    elif isinstance(value, list):
        for item in value:
            query_strings(item)

for parent in [REPO / "docs", REPO / "artifacts"]:
    for path in parent.rglob("*"):
        if not path.is_file() or ROOT in path.parents or path == REPORT or path.stat().st_size > 4000000 or path.suffix not in [".json", ".md", ".raw", ".body", ".html", ".txt"]:
            continue
        try:
            text = path.read_text()
        except UnicodeError:
            continue
        relative = str(path.relative_to(REPO))
        if re.search(r"shortformkit\.com|github\.com/(shortformkit|diegobruegger-prog)/free-remote-mcp-servers", text, re.I):
            novelty["shortformkit_website_or_repository"].append(relative)
        elif "shortformkit-mcpscan" in text.lower():
            novelty["shortformkit_client_name_only"].append(relative)
        if "thelearningstandard.org/news/how-autonomous-ai-agents-are-redefining-student-research-skills" in text:
            novelty["education_article"].append(relative)
        if path.suffix == ".json" and any(marker in relative for marker in ["external", "ecosystem"]):
            try:
                query_strings(json.loads(text))
                prior_json_files += 1
            except ValueError:
                pass

queries = []
for path in sorted(ROOT.glob("search-*.json")):
    group = docs[path.name]
    result = group["result"]
    text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
    state = "error" if result.get("isError") else "blocked_batch" if "Blocked by robots.txt" in text else "returned"
    queries.extend({"query": query, "file": path.name, "status": state, "exact_prior_match": query.strip() in prior_queries} for query in group["queries"])
unique = {row["query"] for row in queries}
returned = {row["query"] for row in queries if row["status"] == "returned"}
query_index = {"attempted_query_executions": len(queries), "unique_query_strings": len(unique),
               "returned_batch_query_strings": len(returned), "unrecovered_query_strings": sorted(unique - returned),
               "exact_prior_query_repeats": sorted(unique & prior_queries), "prior_query_strings": len(prior_queries),
               "prior_json_files_parsed": prior_json_files, "rows": queries,
               "limits": "Batch membership does not certify individual query execution. Literal structured-field deduplication only. Three unaffected queries recovered separately; Weibo not retried."}
(ROOT / "query-index.json").write_text(json.dumps(query_index, ensure_ascii=False, indent=2) + "\n")
(ROOT / "novelty-check.json").write_text(json.dumps({"prior_matches": novelty, "limits": "Accessible external audit text files under4MB; previous grow docs also read manually. A prior shortformkit-mcpscan name in AEfact reader stats is not evidence about our endpoints."}, ensure_ascii=False, indent=2) + "\n")

summary = {
    "observed_date": "2026-10-30", "display_timezone": "Europe/Amsterdam",
    "findings": [
        {"kind": "new_evidence_of_external_automated_protocol_observation", "operator": "ShortformKit",
         "event_date": data["tested"], "rows": observations, "run_url": jobs[0]["html_url"],
         "run_head_sha": jobs[0]["head_sha"], "output_sha": output["sha"],
         "methods_in_published_probe": sorted(methods), "tool_execution_claimed": False,
         "languages": ["en", "ja", "ko"], "operator_count": 1,
         "limits": ["Published dataset and successful CI steps, not raw per-endpoint HTTP transcripts", "No tools/call; no application workflow, installation, payment, signature verification or memory operation established", "Probe reads one tools/list page", "Own prose calls it two requests, code also sends initialized notification", "Prior client name in unrelated AEfact stats not counted as a new operator mention"]},
        {"kind": "new_external_bibliographic_reference_to_ecosystem_course",
         "url": by_name["education-article"]["url"], "event_date": "2026-09-22", "cited_course": course_url,
         "limits": ["Course appears in Sources; main text does not evaluate it", "Human editorial review, course completion, lab execution or institutional adoption not established", "Separate domains do not establish distinct beneficial owners"]}
    ],
    "new_independent_runtime_deployments_confirmed": 0,
    "new_independent_social_posts_confirmed": 0,
    "package_graphs": {"selected_package_versions": len(package_scope["selected"]), "new_graphs_read": len(graphs),
                       "graphs_with_dependents": 0, "skipped_previously_read": package_scope["skipped_previous_exact_graph_urls"],
                       "limits": "Specific package versions and one index; no statement about private apps, manual installs or HTTP clients"},
    "pull_requests": {"broad_total": docs["external-pull-requests.json"]["total_count"],
                      "first_page_returned": len(docs["external-pull-requests.json"]["items"]),
                      "first_page_authors": dict(Counter(item["user"]["login"] for item in docs["external-pull-requests.json"]["items"])),
                      "without_dependabot_total": docs["external-pr-without-dependabot.json"]["total_count"],
                      "interpretation": "Three known contributor docs PRs; fourth changes the ecosystem's Pages site, not an outside runtime deployment"},
    "web_search": {key: value for key, value in query_index.items() if key != "rows"},
    "direct_public_gets": len(sources), "http_statuses": dict(Counter(str(row["status"]) for row in sources)),
    "body_hashes_verified": len(sources),
    "mutations": "Local audit artifacts only. No purchases, paid APIs, invokes, messages, installs, foreign code execution, deployments, authentication changes or GitHub/Gitea writes by us."
}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
index = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "display_timezone": "Europe/Amsterdam",
         "direct_public_gets": len(sources), "body_hashes_verified": len(sources), "sources": sources,
         "report": "../../growth/" + REPORT.name}
(ROOT / "audit-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
local_links = []
for target in re.findall(r"\]\(([^)]+)\)", REPORT.read_text()):
    if "://" in target or target.startswith("#"):
        continue
    assert (REPORT.parent / unescape(target).split("#", 1)[0]).resolve().is_file(), target
    local_links.append(target)
print(json.dumps({"gets": len(sources), "hashes_verified": len(sources), "observer_rows": len(observations),
                  "new_package_graphs": len(graphs), "course_citation": course_url,
                  "web_attempts": len(queries), "unique_queries": len(unique), "returned_query_strings": len(returned),
                  "novelty_prior_matches": novelty, "local_links_checked": len(local_links)}, ensure_ascii=False, indent=2))
