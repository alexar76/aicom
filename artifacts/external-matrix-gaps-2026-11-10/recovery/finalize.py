# -*- coding: utf-8 -*-
"""Offline reconciliation of denial recovery and publisher-source verification."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
own_index_files = ["web-recovery-index.json", "public-primary-sources-index.json", "obsidian-readme-source-index.json",
                   "obsidian-linked-example-index.json", "obsidian-linked-summary-index.json"]
rows = [r for name in own_index_files for r in json.loads((HERE / name).read_text())]
bykey = {r["key"]: r for r in rows}


def body(key):
    return (HERE / bykey[key]["body_file"]).read_text()


def evidence(key):
    return {k: v for k, v in bykey[key].items() if k not in {"provenance"}}


class Parse(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text_parts = []
        self.embedded = []
        self.in_embedded = False
        self.links = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "script" and d.get("data-target") == "react-app.embeddedData":
            self.in_embedded = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_embedded = False
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, text):
        if not self.skip:
            self.text_parts.append(text)
        if self.in_embedded:
            try:
                self.embedded.append(json.loads(text))
            except ValueError:
                pass

    @property
    def text(self):
        return " ".join(" ".join(self.text_parts).split())


pr = Parse()
pr.feed(body("courses-pr-web"))
commit = Parse()
commit.feed(body("courses-commit-web"))
route = commit.embedded[0]["payload"]["commitRoute"]
diffs = route["diffEntryData"]
assert len(diffs) == 1 and diffs[0]["path"] == "courses/free-courses-en.md"
assert diffs[0]["linesAdded"] == 1 and diffs[0]["linesDeleted"] == 0
added = [x["text"] for x in diffs[0]["diffLines"] if x.get("type") == "ADDITION"]
assert any("https://alexar76.github.io/aimarket-courses/" in x for x in added)
assert "eshellman merged" in pr.text and "#13393 Closed" in pr.text
assert "Pick one or the other, not both." in pr.text
course = {"classification": "historical_owner_submission_accepted_as_single_curated_course_portal",
          "pr_evidence": evidence("courses-pr-web"), "commit_evidence": evidence("courses-commit-web"),
          "pr_number": 13394, "pr_submitter": "alexar76", "merge_account": "eshellman", "merge_day": "2026-08-06",
          "pinned_commit": route["commit"]["oid"], "author_login": route["commit"]["authors"][0]["login"],
          "committer_login": route["commit"]["committer"]["login"],
          "commit_authored_date": route["commit"]["authoredDate"], "commit_committed_date": route["commit"]["committedDate"],
          "file": diffs[0]["path"], "additions": 1, "deletions": 0, "added_lines": added,
          "school_scope": "PR13394 conversation asks for one portal rather than two listings; owner closes companion SchoolPR13393 as duplicate. That companion PR was not read independently in this recovery.",
          "not_established": ["A new November reference", "Completion or testing of academies/notebooks", "Runtime integration", "Verified human/legal identity of all participants"],
          "novelty": "Newly recovered primary provenance for an existing historical link, not a new backlink relationship."}
(HERE / "course-curation-analysis.json").write_text(json.dumps(course, ensure_ascii=False, indent=2) + "\n")

readme = body("obsidian-canonical-readme")
raw = body("obsidian-team-memory-example")
summary = body("obsidian-team-memory-summary")
markers = ["alexar76", "attestedmemory.net", "attested-memory", "personal-attested-memory", "expert-memory-market", "AIMarket"]
matches = {key: {m: len(re.findall(re.escape(m), value, re.I)) for m in markers}
           for key, value in {"README": readme, "linked_raw_example": raw, "compiled_summary": summary}.items()}
assert not any(n for x in matches.values() for n in x.values())
assert "origin: internal-product-note" in raw and "Source: `raw/team-memory-os.md`" in summary
obsidian = {"classification": "internal_document_compilation_example_not_attributed_to_our_Team_Memory_OS",
            "evidence": [evidence(k) for k in ["obsidian-repo-web", "obsidian-canonical-readme", "obsidian-team-memory-example", "obsidian-team-memory-summary"]],
            "confirmed_default_branch": "main", "README_path_observed_on_repository_page": "README.md",
            "exact_marker_matches": matches,
            "generic_name_mentions": {"README_team_memory_os": readme.lower().count("team-memory-os")},
            "raw_frontmatter": {"source-type": "clipping", "captured-at": "2026-05-16", "origin": "internal-product-note"},
            "compiled_summary_claimed_date": "2026-05-16",
            "direction": "Repository README points to its own raw note and compiled wiki summary; no exact provenance points to alexar76's Attested products.",
            "scope": "Four publisher pages/files, not a full tree/dependency audit. No claim about every file in the repository.",
            "novelty": "An unread candidate is now classified in this bounded source chain; neither runtime adoption nor a new external link confirmed.",
            "besboy_attribution": "Not established: the note labels itself internal; it is not attributed to besboy3107 or our ecosystem."}
(HERE / "obsidian-analysis.json").write_text(json.dumps(obsidian, ensure_ascii=False, indent=2) + "\n")

y = yaml.safe_load(body("attested-published-apis-yaml"))
old_yaml = ROOT / "artifacts/external-signals-2026-11-09/root/apis-attested-source.raw"
same_old_yaml = hashlib.sha256(old_yaml.read_bytes()).hexdigest() == bykey["attested-published-apis-yaml"]["sha256"]
api = {"classification": "generated_API_profile_not_runtime_implementation", "evidence": evidence("attested-published-apis-yaml"),
       "literal_publisher_href_provenance": "artifacts/external-components-2026-11-10/products/raw/attested-apisio.raw:1831",
       "metadata": {k: y.get(k) for k in ["aid", "name", "x-type", "x-source", "x-tier", "x-tier-reason", "created", "modified"]},
       "api_records": len(y.get("apis", [])),
       "same_bytes_as_Nov9_capture": same_old_yaml, "Nov9_body": str(old_yaml.relative_to(ROOT)),
       "scope": "Profile/harvest metadata and generated artifact references; no import, dependency, actual client call or deployment established.",
       "location_correction": "Published source is artifacts.apis.io/attestedmemory-net/apis.yml. Original GitHub contents/apis.yml path remains unread/unverified; the two locations are not equated.",
       "novelty": "Known Nov9 artifact, identical bytes. Access restored through its actual published primary location; no new relationship or update."}
(HERE / "apis-profile-analysis.json").write_text(json.dumps(api, ensure_ascii=False, indent=2) + "\n")

root_dir = ROOT / "artifacts/external-matrix-gaps-2026-11-10/root"
core_rows = json.loads((root_dir / "plan-3-core-probe-index.json").read_text())
probe = next(x for x in core_rows if x["key"] == "obsidian-readme-retry")
search_rows = json.loads((root_dir / "plan-2-search-index.json").read_text())
treasury = next(x for x in search_rows if x["key"] == "readme-treasury")
tdata = json.loads((root_dir / treasury["file"]).read_text())
assert treasury["status"] == 200 and tdata["total_count"] == 0 and not tdata["incomplete_results"]
plan = json.loads((HERE / "recovery-plan.json").read_text())
old_treasury = next(x for x in plan["targets"] if x["key"] == "treasury-search")
assert parse_qs(urlsplit(old_treasury["exact_url"]).query)["q"] == parse_qs(urlsplit(treasury["url"]).query)["q"]
for target in plan["targets"]:
    key = target["key"]
    if key in {"undercode-factory", "esim-socket"}:
        target.update(status="still_managed_challenge_after_one_ordinary_retry", recovery_evidence=evidence(key))
    elif key == "obsidian-readme":
        target.update(status="content_recovered_via_publisher_web_and_raw_REST_still_quota403", analysis="obsidian-analysis.json")
    elif key in {"courses-curation-pr", "courses-curation-commit"}:
        target.update(status="content_recovered_via_publisher_GitHub_web_REST_not_recovered", analysis="course-curation-analysis.json")
    elif key == "attested-apiev-apis":
        target.update(status="actual_published_artifact_recovered_original_GitHub_location_unverified", analysis="apis-profile-analysis.json")
    elif key == "treasury-search":
        target.update(status="same_query_recovered_by_root_HTTP200_zero_results", recovery_source=str((root_dir / "plan-2-search-index.json").relative_to(ROOT)),
                      recovery_url=treasury["url"], query_same=True, page_size_change="30 to100; encoding differs, literal URLs not identical", total_count=0,
                      scope="This repository/README query only, not global absence of users or HTTP consumers.")
plan["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
plan["github_core_latest_control"] = {"index": str((root_dir / "plan-3-core-probe-index.json").relative_to(ROOT)), **probe,
                                      "interpretation": "REST control remains403/core0; old Date/reset cannot be used as proof of recovery. Public publisher pages were separately available, without login/challenge."}
(HERE / "recovery-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")

integrity = []
for row in rows:
    b = (HERE / row["body_file"]).read_bytes()
    integrity.append({"key": row["key"], "bytes_match": len(b) == row["bytes"], "sha256_match": hashlib.sha256(b).hexdigest() == row["sha256"]})
for row in [probe, treasury]:
    b = (root_dir / row["file"]).read_bytes()
    integrity.append({"key": "root-reused:" + row["key"], "bytes_match": len(b) == row["bytes"], "sha256_match": hashlib.sha256(b).hexdigest() == row["sha256"]})
assert all(x["bytes_match"] and x["sha256_match"] for x in integrity)
(HERE / "capture-integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")
findings = {"date_client": "2026-11-10", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "counts": {"worker_public_GETs": len(rows), "worker_GitHub_REST_GETs": 0,
                       "worker_statuses": dict(Counter(str(x["status"]) for x in rows)),
                       "publisher_content_gaps_resolved": 4, "same_query_gap_resolved_by_root": 1,
                       "still_managed_challenges": 2, "new_external_relationships_confirmed": 0, "new_runtime_adoptions_confirmed": 0},
            "recovered": {"obsidian": obsidian, "course_curation": course, "apis_profile": api,
                          "treasury": {"root_evidence": treasury, "source_index": str((root_dir / "plan-2-search-index.json").relative_to(ROOT)),
                                       "result": {"total_count": 0, "incomplete_results": False}, "scope": "Same exact q; per_page100 rather than30. No independent consumer found by this query only."}},
            "still_unknown": [{"key": key, "evidence": evidence(key), "reason": "Cloudflare managed challenge shell, not source article/package content; no JS/cookie/CAPTCHA handling or further retry."} for key in ["undercode-factory", "esim-socket"]],
            "REST_limit": {"control": probe, "source_index": str((root_dir / "plan-3-core-probe-index.json").relative_to(ROOT)),
                           "status": "Not recovered. Four content subjects were instead checked through separately accessible publisher web/raw surfaces.",
                           "rate_clock_limit": "Response Date/reset predate capture by nearly an hour; do not convert elapsed time into approval or quota availability."},
            "provenance_limits": ["Publication/merge dates are historical; recovery date is not a new publication.",
                                  "Metadata/source-list/profile generation is not runtime integration or product-quality evidence.",
                                  "Obsidian decision covers README and the linked raw/compiled example, not a complete code audit.",
                                  "Public publisher surfaces were ordinary unauthenticated GETs, not third-party mirrors/proxies or identity/IP changes."],
            "external_writes": False, "github_writes": False, "messages": False, "logins": False, "payments_or_tools_call": False,
            "challenge_execution": False, "foreign_code_execution": False, "capture_integrity": "capture-integrity.json"}
(HERE / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(findings["counts"], ensure_ascii=False))
