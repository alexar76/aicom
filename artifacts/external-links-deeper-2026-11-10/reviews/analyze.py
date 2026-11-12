# -*- coding: utf-8 -*-
"""Summarize captured review evidence; all work below is offline."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
rows = []
for name in ["http-initial-index.json", "http-followup-index.json"]:
    rows += json.loads((HERE / name).read_text())
bykey = {r["key"]: r for r in rows}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.skip = 0
        self.parts = []
        self.meta = {}
        self.in_ld = False
        self.ld_body = ""
        self.ld = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append({"href": d["href"], "rel": d.get("rel")})
        if tag == "meta" and d.get("content"):
            self.meta[d.get("name", d.get("property", ""))] = d["content"]
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "script" and d.get("type") == "application/ld+json":
            self.in_ld = True
            self.ld_body = ""

    def handle_endtag(self, tag):
        if tag == "script" and self.in_ld:
            try:
                self.ld.append(json.loads(self.ld_body))
            except ValueError:
                pass
            self.in_ld = False
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_ld:
            self.ld_body += data
        if not self.skip:
            self.parts.append(data)

    @property
    def text(self):
        return " ".join(" ".join(self.parts).split())


def page(key):
    p = Page()
    p.feed((HERE / bykey[key]["body_file"]).read_text())
    return p


def evidence(key):
    r = bykey[key]
    return {"url": r["url"], "read_at_utc": r["observed_at_utc"], "status": r.get("status"),
            "body_file": r.get("body_file"), "sha256": r.get("sha256"), "truncated": r.get("truncated")}


def own_href(url):
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    h = p.hostname or ""
    return (h == "modelmarket.dev" or h.endswith(".modelmarket.dev")
            or h in {"magic-ai-factory.com", "attestedmemory.net", "hub.attestedmemory.net", "alexar76.github.io"}
            or (h in {"github.com", "dev.to", "huggingface.co"} and p.path.startswith("/alexar76/")))


def links(key):
    p = page(key)
    return [{**x, "absolute_url": urljoin(bykey[key]["url"], x["href"])} for x in p.links
            if own_href(urljoin(bykey[key]["url"], x["href"]))]


queries = []
for p in sorted(HERE.glob("search-*.json")):
    d = json.loads(p.read_text())
    queries.append({"response_file": p.name,
                    "response_saved_at_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                    "queries": d["args"]["search_query"],
                    "tool_is_error": d["result"].get("isError", False),
                    "batch_empty": "Empty search results" in str(d["result"]),
                    "limit": "A successful batch response does not guarantee exhaustive execution or exact literal matching of every query."})
(HERE / "query-index.json").write_text(json.dumps(queries, ensure_ascii=False, indent=2) + "\n")

integrity = []
for r in rows:
    if r.get("body_file"):
        b = (HERE / r["body_file"]).read_bytes()
        integrity.append({"key": r["key"], "bytes_match": len(b) == r["captured_bytes"],
                          "hash_match": hashlib.sha256(b).hexdigest() == r["sha256"]})
assert all(x["bytes_match"] and x["hash_match"] for x in integrity)
(HERE / "capture-integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")

dang = page("dangmua-threads")
article = next(o for o in dang.ld if o.get("@type") == "Article")
source = ROOT / "modelmarket-blog/posts/331-mcp-tool-list-changes-only-moved-a-date/body.md"
original = source.read_text()
fingerprints = ["10,712", "4,491", "331", "237", "218"]
assert all(s in dang.text and s in original for s in fingerprints)
assert not links("dangmua-threads")
assert not [x for x in dang.links if x["href"].startswith(("http:", "https:"))]
novelty = {}
for term in ["dangmua.com", "dangmua.com/blog/claude-message-threads-beta-cuts-request-size-not-your-bill"]:
    proc = subprocess.run(["rg", "-l", "-F", term, "docs", "artifacts", "-g", "*.md", "-g", "*.json", "-g", "*.txt", "-g", "*.raw",
                           "-g", "!artifacts/external-links-deeper-2026-11-10/**"], cwd=ROOT, capture_output=True, text=True)
    novelty[term] = {"prior_matching_files": proc.stdout.splitlines(), "rg_exit": proc.returncode,
                     "scope": "Prior docs/artifacts in selected text extensions; all branches of current deeper pass excluded."}
(HERE / "novelty-check.json").write_text(json.dumps(novelty, ensure_ascii=False, indent=2) + "\n")


def flatten(items):
    for x in items:
        yield x
        yield from flatten(x.get("children", []))


comment_deltas = []
for key, aid in [("dev-comments-marketplace", 4951998), ("dev-comments-histor-comparison", 4954137), ("dev-comments-x402-retry", 4804987)]:
    current = list(flatten(json.loads((HERE / bykey[key]["body_file"]).read_text())))
    prior_path = ROOT / f"artifacts/external-signals-2026-11-09/audience/raw/devto-comments-{aid}.raw"
    old = list(flatten(json.loads(prior_path.read_text())))
    before = {x["id_code"] for x in old}
    after = {x["id_code"] for x in current}
    new = [x for x in current if x["id_code"] not in before]
    comment_deltas.append({"article_id": aid, "baseline_file": str(prior_path.relative_to(ROOT)),
                           "current_evidence": evidence(key), "baseline_comments": len(old), "current_comments": len(current),
                           "new_comment_ids": [x["id_code"] for x in new],
                           "new_external_comment_ids": [x["id_code"] for x in new if x["user"]["username"].lower() != "alexar76"],
                           "removed_comment_ids": sorted(before - after)})
(HERE / "dev-comment-delta.json").write_text(json.dumps(comment_deltas, ensure_ascii=False, indent=2) + "\n")

external_articles = []
for key in ["quincygb-watch-article", "quincygb-fleet-article", "martin-receipts-article", "martin-mcp-review-article", "paul-claudemd-article"]:
    a = json.loads((HERE / bykey[key]["body_file"]).read_text())
    body = a["body_markdown"]
    matches = re.findall(r"(?i)\b(?:HISTOR|AIMarket|alexar76|WARDEN)\b|modelmarket\.dev|attestedmemory\.net|magic-ai-factory\.com", body)
    external_articles.append({"source_url": a["url"], "title": a["title"], "author_username": a["user"]["username"],
                              "published_at": a["published_at"], "edited_at": a.get("edited_at"),
                              "exact_identity_matches_in_article_body": matches, "evidence": evidence(key),
                              "decision": "No direct exact ecosystem identification in fetched article body; shared topic or existing author contact not counted as a review of us."})
assert not any(x["exact_identity_matches_in_article_body"] for x in external_articles)
(HERE / "external-author-articles.json").write_text(json.dumps(external_articles, ensure_ascii=False, indent=2) + "\n")

findings = {
    "date_client": "2026-11-10", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "baseline": ["artifacts/external-links-2026-11-10/review.ru.md",
                 "artifacts/external-social-regional-deeper-2026-11-09/report.ru.md",
                 "artifacts/external-social-regional-deeper-2026-11-09/social/report.ru.md",
                 "artifacts/external-social-regional-deeper-2026-11-09/regions/report.ru.md"],
    "scope": "Independent reviews, outside technical discussion and named research reuse. Catalogs, own articles and same-name projects excluded.",
    "counts": {"search_strings_submitted": sum(len(x["queries"]) for x in queries), "search_batches": len(queries),
               "primary_gets": len(rows), "unique_get_urls": len({r["url"] for r in rows}),
               "http_statuses": dict(Counter(str(r.get("status", "error")) for r in rows)),
               "new_external_non_catalog_research_mentions": 1, "new_confirmed_html_backlink_pages": 0,
               "new_confirmed_independent_full_product_reviews": 0, "new_confirmed_runtime_adoptions": 0,
               "new_external_comments_in_three_rechecked_dev_threads": sum(len(x["new_external_comment_ids"]) for x in comment_deltas)},
    "new_findings": [{
        "source_url": article["url"], "title": article["headline"] if "headline" in article else dang.meta.get("og:title"),
        "component": "HISTOR", "classification": "external_editorial_synthesis_reuses_named_historical_research_without_backlink",
        "published_at_claim": article["datePublished"], "modified_at_claim": article["dateModified"],
        "evidence": evidence("dangmua-threads"), "author": article["author"],
        "ownership_confidence": {"external_publication_surface": "high", "publisher_owner_independence": "unverified", "human_author_or_fact_checking": "unverified"},
        "direct_html_hrefs_to_ecosystem": [], "all_absolute_external_anchor_hrefs": [],
        "named_attribution": "HISTOR is explicitly named; historical figures are attributed to its accounting.",
        "direction": "Our named research results are reused in an external article about Claude Message Threads; no direct source URL establishes whether the path was original or an intermediary.",
        "comparison": {"local_first_party_article": str(source.relative_to(ROOT)), "local_article_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "shared_numeric_fingerprints": fingerprints, "shared_measurement_window": "25 October to 1 November 2026",
                       "scope": "Text-to-text comparison only, no new production query or independent empirical replication."},
        "novelty": "Exact source domain and URL absent in checked prior docs/artifacts outside current deeper pass; historical article from Nov3, newly identified Nov10.",
        "limits": ["Not a full product review or independently rerun benchmark.", "Not an HTML backlink and no new installation/customer/payment is established.",
                   "Publisher uses an organizational byline; a human writer/editor or relationship to ecosystem owner has not been verified.",
                   "The article is a topical synthesis with broader Threads discussion; a lack of explicit aggregator label does not prove independent reporting."]
    }],
    "known_reconfirmed": [
        {"source_url": bykey["scraperwatch-changes"]["url"], "classification": "outside_comparison_writeup", "evidence": evidence("scraperwatch-changes"),
         "event_date": "2026-11-01", "correction_date": "2026-11-02", "literal_own_hrefs": links("scraperwatch-changes"),
         "ownership": "About page claims independent project, automated public-data rankings and affiliate disclosure; ownership not independently verified.",
         "scope": "Outside-check section still acknowledges HISTOR and robots correction. Already in fresh baseline; no new date/review established."},
        {"source_url": bykey["fplcat-agents"]["url"], "classification": "operator_blog_about_inbound_crawlers", "evidence": evidence("fplcat-agents"),
         "published_date": "2026-10-13", "modified_date": "2026-10-13", "literal_own_hrefs": links("fplcat-agents"),
         "scope": "Same historical 39 requests by histor/0.1.0 and direct HISTOR link. Observation of our crawler is not adoption of HISTOR."},
        {"source_url": bykey["hlido-review"]["url"], "classification": "historical_public_surface_review", "evidence": evidence("hlido-review"),
         "published_date": "2026-08-05", "modified_date": "2026-08-05", "claimed_retest_due": "2026-11-05",
         "literal_own_hrefs": links("hlido-review"), "author": "Hlido Editor", "score_not_adopted_as_our_quality_measure": 60,
         "scope": "Known review, still dated August despite passed re-test date. JSON-LD marks compositeWithTrainedAlgorithmicMedia. Not a new November hands-on review or current compliance validation."},
        {"source_url": "https://github.com/lets-order-some-fries/trovark/issues/22#issuecomment-5682361982", "classification": "historical_external_static_analysis", "evidence": evidence("trovark-issue22-comments"),
         "event_date": "2026-09-15T14:49:23Z", "comments_returned": 1,
         "scope": "One unchanged historical author comment covering aimarket-plugins; no later comment in current returned complete one-comment list."}
    ],
    "negative_or_unresolved": [
        {"kind": "outside_author_article_bodies", "file": "external-author-articles.json", "fully_read": 5,
         "decision": "No exact ecosystem identity in these bodies. They are not counted as reviews merely because authors previously replied to us."},
        {"kind": "three_DEV_comment_threads", "file": "dev-comment-delta.json", "decision": "Zero new comment IDs against Nov9 baseline in three selected threads."},
        {"kind": "HackerNews_exact_comment_search", "urls": [bykey[k]["url"] for k in ["hn-modelmarket-comments", "hn-alexar76-comments"]],
         "hits": [0, 0], "decision": "Only exact quoted comment markers checked. Known external HN questions can omit these markers; no global absence claim."},
        {"kind": "unresolved_rate_limited_sources", "keys": ["agentembassy-articles", "quincygb-shovels-article"], "status": 429,
         "decision": "Unread; no negative conclusion. Initial x402 comments429 recovered by one later GET200."},
        {"kind": "guessed_source_navigation", "keys": ["dangmua-blog", "dangmua-about"], "status": 410,
         "decision": "Guessed navigation paths, not published backlinks. Real homepage and linked feed were read separately."},
        {"kind": "fplcat_adjacent_comparison", "url": bykey["fplcat-assistants-article"]["url"], "evidence": evidence("fplcat-assistants-article"),
         "decision": "Adjacent AI-assistant comparison has no exact link/name for our ecosystem; excluded."},
        {"kind": "search_noise", "decision": "Own DEV/Pages/wiki mirrors, catalog cards, historical/Siemens tool-list homonyms and histor.dev were excluded. Search exclusions/literal matches were not consistently obeyed by the engine."}
    ],
    "limits": ["Public indexed sample and selected native APIs, not the whole internet or closed discussions.",
               "No new confirmed independent full product review in this sample is not evidence that none exists.",
               "External organizational bylines and about-page independence claims are not verified legal ownership or human review.",
               "Search response dates and primary read dates are separate from publication/measurement event dates.",
               "Ratings and old counts quoted by outsiders are not our current telemetry and were not re-measured here.",
               "Initial default sandbox had no DNS access; public GET captures were made after authorized read-only network escalation. No denied-read result was treated as absence."],
    "external_writes": False, "github_writes": False, "messages": False, "logins": False,
    "payments_or_tool_invocations": False, "foreign_code_executed": False,
    "capture_integrity": "capture-integrity.json"
}
(HERE / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(findings["counts"], ensure_ascii=False))
