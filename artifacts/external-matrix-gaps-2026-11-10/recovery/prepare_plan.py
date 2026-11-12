# -*- coding: utf-8 -*-
"""Prepare exact recovery targets and preserve original denial evidence offline."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTS = "artifacts/external-components-2026-11-10/products"
CORE = "artifacts/external-components-2026-11-10/core"
SPECS = [
    ("undercode-factory", CORE + "/foreign-source-index.json", "id", "undercode-factory", "cloudflare_managed_challenge", 6,
     "Known Factory release-note coverage; recover primary body and literal source href, metadata date and disclosure. Not a new hands-on review merely because accessible again."),
    ("esim-socket", PRODUCTS + "/sources-http-index.json", "key", "esim-socket", "cloudflare_managed_challenge", 7,
     "Read the exact package analysis page and distinguish automated npm metadata/static analysis from a user's eSIM operator deployment or review."),
    ("obsidian-readme", PRODUCTS + "/followup-http-index.json", "key", "obsidian-readme", "github_core_quota", 1,
     "Resolve closest remaining foreign Attested candidate: exact owner/domain/package links; distinguish dependency/client code from comparison list, generic memory term or unrelated app."),
    ("courses-curation-pr", PRODUCTS + "/followup-http-index.json", "key", "courses-curation-pr", "github_core_quota", 2,
     "Verify historical PR author, merged/merged_at/merged_by and title/body. Separate owner submission accepted by a foreign list from unsolicited review or learner use."),
    ("courses-curation-commit", PRODUCTS + "/followup-http-index.json", "key", "courses-curation-commit", "github_core_quota", 3,
     "Verify exact pinned commit author/committer and changed files/patch for moving the AIMarket Courses link into MOOC. A curation diff is documentation, not runtime integration."),
    ("attested-apiev-apis", PRODUCTS + "/followup-http-index.json", "key", "attested-apiev-apis", "github_core_quota", 4,
     "Read literal apis.yml if it exists: harvest provenance, own original URLs, generated artifact references. Generated profile/specs are not use of the Attested service."),
    ("treasury-search", CORE + "/github-search-index.json", "id", "github-search-5", "github_quota_body_resource_not_captured", 5,
     "Restore previously unread exact README-search result. Post-filter owner and exact identity; a successful zero only covers this query, not the entire Treasury user base.")
]
targets = []
for key, index_path, key_field, old_key, reason, priority, expected in SPECS:
    rows = json.loads((ROOT / index_path).read_text())
    old = next(x for x in rows if x.get(key_field) == old_key)
    relative = old.get("body_file", old.get("body_path"))
    body_path = (ROOT / index_path).parent / relative
    raw = body_path.read_bytes()
    headers = old.get("public_rate_headers", {})
    reset = headers.get("X-RateLimit-Reset")
    reset_utc = datetime.fromtimestamp(int(reset), timezone.utc).isoformat() if reset else None
    read_at = old.get("observed_at_utc", old.get("retrieved_at_utc"))
    text = raw.decode("utf-8", errors="replace")
    reset_past = (datetime.fromisoformat(reset_utc) < datetime.fromisoformat(read_at)) if reset_utc else None
    targets.append({
        "key": key, "exact_url": old["url"], "priority": priority,
        "prior_evidence": {"index": index_path, "body": str(body_path.relative_to(ROOT)), "captured_at_utc": read_at,
                           "status": old.get("status"), "sha256": old.get("sha256"),
                           "bytes_valid": len(raw) == old.get("bytes"), "sha256_valid": hashlib.sha256(raw).hexdigest() == old.get("sha256")},
        "reason": reason,
        "body_evidence": {"github_rate_limit_message": "API rate limit exceeded" in text,
                          "cloudflare_managed_challenge": all(s in text for s in ["Just a moment", "_cf_chl_opt", "challenges.cloudflare.com"])},
        "previous_rate_headers": headers or None,
        "previous_reset_utc": reset_utc, "previous_reset_before_capture": reset_past,
        "rate_header_limit": "Old reset is before the recorded capture; do not infer recovery from time. Current quota plus bounded real target response required." if reset_past else "No rate/reset headers were preserved for this source; do not invent one or borrow another resource's reset.",
        "expected_new_evidence": expected,
        "novelty_rule": "Recovery is a new primary read/artifact, not a new external relationship or publication. Compare literal content, author/event date and target with prior baseline.",
        "assignment": "root_search_bucket" if key == "treasury-search" else ("root_quota_probe_then_allocated_detail" if reason == "github_core_quota" else "one_ordinary_public_GET_authorized_by_root"),
        "status": "pending_coordinated_recovery",
        "prohibited": ["CAPTCHA or managed challenge solving", "robots bypass", "IP/proxy/account/authentication switching", "GitHub or other external writes"]})
assert all(x["prior_evidence"]["bytes_valid"] and x["prior_evidence"]["sha256_valid"] for x in targets)
plan = {"date_client": "2026-11-10", "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "preparation_network_requests": 0,
        "github_coordination": "Root controls current quota, exact Obsidian probe and Treasury/Search. This worker does not request api.github.com until root allocates specific reads.",
        "targets": sorted(targets, key=lambda x: x["priority"]),
        "integration_decision_rules": {
            "runtime_or_dependency_candidate": "Exact namespace/domain plus implementation import/dependency/endpoint call in foreign source; README claim alone remains unverified execution.",
            "documentation_or_comparison": "Link, source list or curation metadata with no implementation path is a reference, not integration.",
            "generated_profile": "API directory/spec/schema generation and harvest provenance are automated profiling, not user deployment.",
            "unrelated_homonym": "Generic attested memory or shared product name without our owner/domain/package markers is excluded.",
            "unread": "403/challenge/quota is unknown; never counted as absence or successful source verification."}}
(HERE / "recovery-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"targets": len(targets), "quota_denials": sum("github" in x["reason"] for x in targets),
                  "managed_challenges": sum(x["body_evidence"]["cloudflare_managed_challenge"] for x in targets),
                  "old_source_integrity": "passed", "network_requests": 0}))
