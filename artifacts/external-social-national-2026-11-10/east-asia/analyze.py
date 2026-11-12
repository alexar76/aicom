# -*- coding: utf-8 -*-
"""Offline evidence summary. Does not make network requests."""
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STAMP = datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


queries = read_json(HERE / "query-index.json")
for q in queries:
    n = int(q["id"][2:])
    q["submitted"] = True
    q["result_scope"] = "Shared batch response; no separate per-query completeness guarantee."
    if n <= 8:
        q["state"] = "returned_results_exact_filters_expanded_no_new_independent_candidate"
    elif 13 <= n <= 20:
        q["state"] = "partial_batch_robots_unknown_coverage"
        q["blocked_domain"] = "blog.naver.com" if n <= 16 else "cafe.naver.com"
        q["absence_inference_allowed"] = False
    elif 21 <= n <= 24:
        q["state"] = "returned_batch_empty_bounded_query_scope"
    else:
        q["state"] = "returned_results_no_new_independent_candidate_confirmed"
save("query-index.json", queries)

sources = sum((read_json(HERE / ("sources-%02d-index.json" % n)) for n in range(1, 4)), [])
by_key = {s["key"]: s for s in sources}
integrity = []
for s in sources:
    data = (HERE / s["body_file"]).read_bytes()
    integrity.append({"key": s["key"], "body_file": s["body_file"], "status": s["status"],
                      "expected_bytes": s["bytes"], "actual_bytes": len(data),
                      "expected_sha256": s["sha256"], "actual_sha256": sha(data),
                      "verified": len(data) == s["bytes"] and sha(data) == s["sha256"],
                      "truncated": s["truncated"]})

baseline_comment_file = ROOT / "artifacts/external-social-regional-2026-11-09/east-asia/raw/qiita-cost-comments.raw"
current = read_json(HERE / "qiita-known-cost-comments.raw")
baseline = read_json(baseline_comment_file)
old_by_id = {c["id"]: c for c in baseline}
comment_comparison = []
for c in current:
    old = old_by_id.get(c["id"])
    comment_comparison.append({
        "id": c["id"], "author": c["user"]["id"], "created_at": c["created_at"], "updated_at": c["updated_at"],
        "body_sha256": sha(c["body"].encode("utf-8")), "body_equal_baseline": old is not None and old["body"] == c["body"],
        "created_at_equal_baseline": old is not None and old["created_at"] == c["created_at"],
        "updated_at_equal_baseline": old is not None and old["updated_at"] == c["updated_at"],
        "ownership": "ecosystem_author" if c["user"]["id"] == "qwezzy721" else "external_account_no_affiliation_established",
    })

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)


link_sets = {}
for key in ("naver-hub", "naver-attested", "pingblip-itch-profile"):
    p = LinkParser()
    p.feed((HERE / by_key[key]["body_file"]).read_text(encoding="utf-8"))
    link_sets[key] = set(p.links)

DEV = "https://dev.to/alexar76/our-multica-agents-now-work-in-an-agent-market-they-buy-remember-review-sellers-and-sell-their-174f"
targets = {
    "naver-hub": ["https://github.com/alexar76/aimarket-school", "https://pub.dev/packages/aimarket_agent", "https://pypi.org/project/aimarket-hub/", DEV, "https://www.npmjs.com/package/@aimarket/esim-rails", "https://mcpverify.ai/archive"],
    "naver-attested": ["https://github.com/alexar76/attested-memory", DEV],
    "pingblip-itch-profile": ["https://pingblip.com/", "https://pingblip.itch.io/pingblip", "https://itch.io/profile/pingblip"],
}
edges = []
for key, urls in targets.items():
    for url in urls:
        edges.append({"source": by_key[key]["url"], "source_key": key, "target": url,
                      "literal_html_href_verified": url in link_sets[key],
                      "retrieved_at_utc": by_key[key]["retrieved_at_utc"],
                      "relation": "own_profile_distribution" if key.startswith("pingblip") else "search_index_result_not_endorsement",
                      "target_read_in_this_branch": False,
                      "limitation": "Href verified; target not fetched in this branch. PingBlip game was read in today's products audit." if key.startswith("pingblip") else "Search href is not a local author's recommendation; archive target is a generic index candidate, not a verified product review."})

novelty_terms = {
    "pingblip-profile": "https://pingblip.itch.io/",
    "paper-vault-operator": "papers.ananclaw.com",
    "paper-vault-exact-filter-url": by_key["paper-vault-education-list"]["url"],
    "qiita-known-cost-article": "4dfe9dc2fbe9d69b1fb7",
    "qiita-external-comment-id": "a71ae02460f429b7606e",
    "hubwiz-known-article": "hubwiz.com/blog/agent-security-nine-incidents-six-controls",
    "juejin-known-article": "7696713457148952630",
    "naver-previous-search": "search.naver.com/search.naver?query=%22modelmarket.dev%22",
}
novelty = []
for key, term in novelty_terms.items():
    cmd = ["rg", "-l", "-F", term, "artifacts", "docs", "-g", "!**/external-social-national-2026-11-10/**", "-g", "*.json", "-g", "*.md", "-g", "*.raw"]
    run = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if run.returncode not in (0, 1):
        raise RuntimeError(run.stderr)
    matches = sorted(run.stdout.splitlines())
    novelty.append({"key": key, "term": term, "match_mode": "literal substring in existing artifacts/docs, current national-social run excluded",
                    "previous_match_count": len(matches), "previous_files": matches,
                    "interpretation": "known source/relation; not new" if matches else "exact string not previously found; not sufficient for a new independent relation"})
save("novelty-check.json", novelty)

native_keys = ["qiita-other-domain", "qiita-attested", "zenn-domain-articles", "zenn-attested-scraps", "gitee-identity"]
native = []
for key in native_keys:
    value = read_json(HERE / by_key[key]["body_file"])
    result = value if isinstance(value, list) else value.get("articles", value.get("scraps"))
    native.append({"key": key, "url": by_key[key]["url"], "status": by_key[key]["status"],
                   "retrieved_at_utc": by_key[key]["retrieved_at_utc"], "returned_count": len(result),
                   "response": value, "state": "explicit_empty_native_response",
                   "limit": "Only this query/endpoint at capture time; no inference about all authors, all markers, or national audience."})

search_files = []
for n in range(1, 9):
    name = "search-%02d.json" % n
    data = (HERE / name).read_bytes()
    response = read_json(HERE / name)
    assert isinstance(response, str)
    search_files.append({"file": name, "bytes": len(data), "sha256": sha(data), "response_characters": len(response),
                         "query_ids": [q["id"] for q in queries if q["batch_file"] == name],
                         "contains_robots_block": "Blocked by robots.txt" in response,
                         "empty_returned_batch": response.startswith("Empty search results")})

verification = {
    "verified_at_utc": STAMP, "mode": "offline verification of saved responses; no network requests",
    "primary_get_count": len(sources), "http_status_counts": dict(Counter(str(s["status"]) for s in sources)),
    "all_body_hashes_and_lengths_valid": all(x["verified"] for x in integrity), "body_integrity": integrity,
    "literal_edges": edges, "all_selected_hrefs_present": all(e["literal_html_href_verified"] for e in edges),
    "native_api_results": native, "qiita_baseline_file": str(baseline_comment_file.relative_to(ROOT)),
    "qiita_id_sets_equal": set(old_by_id) == {c["id"] for c in current}, "qiita_comment_comparison": comment_comparison,
    "search_response_files": search_files,
}
assert verification["all_body_hashes_and_lengths_valid"]
assert verification["all_selected_hrefs_present"]
assert verification["qiita_id_sets_equal"] and all(x["body_equal_baseline"] for x in comment_comparison)
save("verification.json", verification)

findings = {
    "audit_date": "2026-11-10", "compiled_at_utc": STAMP,
    "scope": "East/Southeast Asian public web/platform surfaces CN/JP/KR/VN/ID/TH; country labels describe queries and platforms, not owner nationality.",
    "new_independent_reviews_discussions_or_integrations_confirmed": 0,
    "confidence": {"captured_response_facts": "high", "national_absence_claim": "not made"},
    "items": [
        {"id": "EA-F01", "type": "known_external_technical_comment_unchanged", "source": "https://qiita.com/qwezzy721/items/4dfe9dc2fbe9d69b1fb7", "comment_id": "a71ae02460f429b7606e",
         "primary_source": by_key["qiita-known-cost-comments"]["url"], "author": "Skillselion", "created_at": "2026-10-24T17:10:34+09:00", "updated_at": "2026-10-24T17:10:34+09:00",
         "ownership": "external public account; affiliation/real identity not established", "language": "Japanese", "owner_country": None,
         "evidence": "The same two comment IDs and full bodies as 9 Nov. Skillselion discusses cache-prefix order, cache-write cost and TTL; ecosystem author's reply is the other comment.",
         "scope": "Technical discussion, no verified installation/use of an ecosystem package", "novelty": "known before this pass; no new comment or body change", "confidence": "high"},
        {"id": "EA-F02", "type": "native_search_empty", "primary_sources": [by_key[k]["url"] for k in native_keys],
         "ownership": "platform search responses", "published_at": None, "owner_country": None,
         "evidence": "Five HTTP200 native API responses explicitly return zero records for the exact queries.", "scope": "Queries and endpoints only", "novelty": "bounded recheck, not a new external source", "confidence": "high"},
        {"id": "EA-F03", "type": "search_index_visibility_of_own_sources", "primary_sources": [by_key[k]["url"] for k in ("naver-hub", "naver-attested")],
         "author": "Naver search index, no article author", "ownership": "external search surface indexing ecosystem-authored destinations", "published_at": None, "owner_country": None,
         "evidence": "Literal HTML hrefs lead to alexar76 School/Attested GitHub, package registries and own DEV article; no Korean author review validated.",
         "scope": "Discoverability; not recommendation, adoption or a country-specific audience count", "novelty": "same relation class already in 9 Nov; changed index snapshot not new independent adoption", "confidence": "high"},
        {"id": "EA-F04", "type": "own_game_distribution", "primary_source": by_key["pingblip-itch-profile"]["url"],
         "author": "PingBlip profile", "ownership": "ecosystem-owned distribution/profile", "published_at": None, "owner_country": None,
         "source_to_target": ["https://pingblip.com/", "https://pingblip.itch.io/pingblip"],
         "evidence": "Profile HTTP200 contains exact hrefs to own PingBlip website and itch game.",
         "scope": "Own game listing; Japanese search wording does not establish Japanese authorship or player review", "novelty": "profile known since October; game and own launch topic read earlier today by products audit", "confidence": "high"},
        {"id": "EA-F05", "type": "known_catalog_search_candidate_primary_unavailable", "primary_source": by_key["paper-vault-education-list"]["url"],
         "author": None, "ownership": "known Paper Vault/Ananclaw catalog operator; current content not read", "published_at": None, "owner_country": None,
         "evidence": "Search result points to a filtered tutorial list; direct GET502 with empty body.",
         "scope": "Unverified current card, no evidence of learner review or real use", "novelty": "operator/School catalog known in prior audits; a different filter URL is not a new publication", "confidence": "high for HTTP status; unknown for current page content"},
    ],
    "known_baseline_not_represented_as_new": [
        {"url": "https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/", "type": "known Chinese-language research summary; no rerun established"},
        {"url": "https://juejin.cn/post/7696713457148952630", "type": "known benchmark summary, identified by rare WARDEN/mcp-shield/mcp-audit table fingerprint"},
        {"url": "https://qiita.com/qwezzy721/items/b71aaeaae84fcb360fe6", "type": "own Japanese translation"},
        {"url": "https://www.selectdataset.com/dataset/d595b7ffd78438a48b6efa42e0861151/histor-mcp-tool-definitions", "type": "known automated dataset-card summary"},
        {"url": "https://dangmua.com/blog/claude-message-threads-beta-cuts-request-size-not-your-bill", "type": "Vietnamese-site article already primary-read by reviews audit earlier today; no new independent rerun"},
    ],
    "limitations": ["32 query strings were submitted in eight shared batches, not 32 guaranteed complete result sets.",
        "Eight input strings in two batches have partial coverage due to blog.naver.com/cafe.naver.com robots blocks; no bypass or retry.",
        "Search sometimes expands exact/site/OR filters and ignores exclusions; irrelevant homonyms and generic results are not evidence.",
        "No private/login/CAPTCHA content, local social groups or personalized search was accessed.",
        "No country of author/owner inferred from language, domain, query formulation or interface locale.",
        "Package/catalog metadata and search index links are not measured usage, installs, readership or independent validation.",
        "No Github API, auth, external writes, messages, invocations or execution of third-party code in this branch."],
}
save("findings.json", findings)
save("coverage.json", {"date": "2026-11-10", "query_strings_submitted": len(queries), "shared_batches": 8,
    "query_counts_by_surface_language_region": dict(Counter(q["region"] for q in queries)),
    "non_histor_query_strings": 31, "histor_research_query_strings": 1,
    "web_result_states": dict(Counter(q["state"] for q in queries)), "native_explicit_empty": native,
    "native_unread_or_unknown": [{"surface": "blog.naver.com", "state": "robots_blocked", "batch": "search-04.json"},
        {"surface": "cafe.naver.com", "state": "robots_blocked", "batch": "search-05.json"},
        {"surface": by_key["paper-vault-education-list"]["url"], "state": "HTTP502 current content unknown"}],
    "new_independent_positive_findings": 0, "notes": "Returned native empty and blocked/unknown states deliberately remain separate."})
print(json.dumps({"queries": len(queries), "primary_gets": len(sources), "hashes_valid": True,
    "hrefs_valid": True, "qiita_id_and_bodies_equal": True, "new_independent": 0}, ensure_ascii=False))
