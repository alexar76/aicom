# -*- coding: utf-8 -*-
"""Offline coverage and source attribution for the remaining product families."""
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
captures = json.loads((HERE / "sources-http-index.json").read_text()) + json.loads((HERE / "followup-http-index.json").read_text())
bykey = {x["key"]: x for x in captures}


def body(key):
    return (HERE / bykey[key]["body_file"]).read_text()


def ev(key):
    r = bykey[key]
    return {k: r[k] for k in ["key", "url", "observed_at_utc", "status", "body_file", "sha256", "truncated", "public_rate_headers"] if k in r}


def provenance(paths, markers):
    result = []
    for path in paths:
        for line, text in enumerate((ROOT / path).read_text().splitlines(), 1):
            hits = [m for m in markers if m.lower() in text.lower()]
            if hits:
                result.append({"file": path, "line": line, "markers": hits, "source_text": text[:650]})
    return result


class HTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)


def html(key):
    p = HTML()
    p.feed(body(key))
    return p


SPECS = [
    ("attested-memory", "Attested Memory: Hub / Personal / Team / Expert",
     ["Attested Memory Hub", "Personal Attested Memory", "Team Memory OS", "Expert Memory Market"],
     ["attested-memory", "personal-attested-memory", "team-memory-os", "expert-memory-market", "attestedmemory.net", "alexar76/attested-memory"],
     ["attested/attested-memory-hub/README.md", "attested/attested-memory-hub/clients/python/pyproject.toml", "personal-attested-memory/pyproject.toml", "team-memory-os/pyproject.toml", "expert-memory-market/README.md", "expert-memory-market/pyproject.toml"],
     [1,2,3,4,27,32], ["gh-repos-attested"], ["attested-apisio", "attested-apiev-repo", "attested-apiev-readme", "attested-dependents"],
     "Known automated API profile and catalog/protocol presence remain. Personal/Team/Expert are searched separately by exact package/product names; no new attributed foreign runtime or independent product review confirmed. Besboy Team Memory OS and Starlight attested memory are not linked to our identity in the fetched READMEs."),
    ("cite-desks", "Cite Desks / Emberline and peer desks",
     ["Emberline", "Tideline", "Solrecord", "Seamark", "Plinth", "Smokeproof", "shared Kernel"],
     ["cite-desks", "emberlinedesk.com", "desk.modelmarket.dev", "tideline.modelmarket.dev", "solrecord.modelmarket.dev", "seamark.modelmarket.dev", "plinthdesk.com", "smokeproof.modelmarket.dev"],
     ["cite-desks/README.md"], [5,6,28,35], ["gh-repos-operator-desks"], [],
     "No new precisely attributed external review or implementation confirmed. Search returned own publishing/mirrors and same-name Cite Desk projects. Grouped GitHub search is tokenized and broader than literal identity; unreviewed hits are not proof of adoption or its absence. Child desk names/domains have per-marker local provenance; not every child has an individual native-code query."),
    ("domain-operator-kit", "Domain Operator Kit", ["Domain operator node", "buyer MCP client", "Vercel connector"],
     ["@aimarket/domain-operator-kit", "alexar76/domain-operator-kit", "domains.modelmarket.dev", "domains.quote@v1"],
     ["domain-kit/README.md", "domain-kit/package.json"], [7,8], ["gh-repos-operator-desks", "gh-commits-operators"], ["domain-glama", "domain-glama-renew"],
     "External Glama description/schema assessment confirmed, including renew parameter-documentation criticism. This is automated metadata feedback, not a human review or actual domain registration. No independent implementation confirmed in the bounded search."),
    ("esim-operator-kit", "eSIM Operator Kit", ["esim-rails seller node", "storefront"],
     ["@aimarket/esim-rails", "alexar76/esim-operator-kit", "esim.modelmarket.dev", "esim-shop.modelmarket.dev"],
     ["esim-kit/README.md", "esim-kit/rails/package.json"], [9,10], ["gh-repos-operator-desks", "gh-commits-operators"], ["esim-socket", "npm-esim-latest", "esim-dependents"],
     "Socket is a search-only catalog/security-analysis candidate: direct GET403, unread. Current version-scoped dependents graph0.4.0 has no recorded dependents. No outside operator or independent review confirmed; graph does not cover CLI/Git installs."),
    ("pingblip", "PingBlip", ["browser game", "World portal", "MemeForge"],
     ["PingBlip", "pingblip.com", "world.pingblip.com", "forge.pingblip.com"],
     ["pingblip/README.md"], [11,12,29,30], ["gh-repos-pingblip"], ["pingblip-game", "pingblip-announcement"],
     "Own itch game page and own launch topic accessible; game HTML has no reader comments, topic shows posts1to1. Automated tag discovery is not a review. No new foreign player story or code integration confirmed. GitHub README search by exact domain returned0; that does not cover private/unindexed code."),
    ("linkedin-coach", "LinkedIn Profile Coach", ["Flutter desktop/mobile app"],
     ["alexar76/linked-in-profile-coach", "linkedin_profile_coach", "LinkedIn Profile Coach"],
     ["coach/README.md", "coach/pubspec.yaml"], [13,14,34], ["gh-repos-apps"], [],
     "No new correctly attributed outside review or implementation in returned web/native-search sample. Generic LinkedIn coach matches excluded. Grouped GitHub README search returned0; no live app-store analytics accessed."),
    ("desktop", "AIMarket Desktop", [],
     ["alexar76/aimarket-desktop", "aicom_desktop_core", "AIMarket Desktop"],
     ["desktop-integrations/README.md"], [15,16,33], ["gh-repos-apps"], [],
     "Ten desktop/IDE SKUs locally inventoried. Family/core markers and selected SKU names searched; no new exact foreign review or implementation confirmed. Not ten independent exhaustive native searches."),
    ("landing", "AI landing generator", ["aicom-landing CLI", "hosted generator"],
     ["aicom-landing", "magic-ai-factory.com/landing-page-generation", "@aimarket/landing"],
     ["aicom-landing/README.md", "aicom-landing/package.json"], [17,18], ["gh-repos-apps"], ["npm-landing-latest", "landing-dependents"],
     "Own registry/wiki/topic mirrors dominate results. No new outside generated-site attribution, review or dependency confirmed; current0.2.0 dependents graph0. Alias @aimarket/landing is namespace metadata, not a separate implementation."),
    ("school", "AIMarket School", ["13 clip lessons and notebooks"],
     ["alexar76/aimarket-school", "edu.modelmarket.dev", "AIMarket School"],
     ["school/README.md"], [19,31], ["gh-repos-education", "gh-repos-education-page2"], [],
     "Known Ananclaw repository card surfaced; no new independent lesson review, completed learner project or code reuse confirmed. Grouped education search has broad unrelated hits; no full traversal of their code."),
    ("courses", "AIMarket Courses", ["13 academies", "orchestration-course"],
     ["alexar76/aimarket-courses", "aimarket-courses", "orchestration-course"],
     ["courses/README.md"], [20,31], ["gh-repos-education", "gh-repos-education-page2", "gh-commits-education"],
     ["courses-ebookfoundation", "courses-learningstandard", "courses-learningstandard-about", "courses-curation-pr", "courses-curation-commit"],
     "External course links confirmed in canonical EbookFoundation list and known Learning Standard article. Search commit provenance is owner-authored, not a benchmark. PR/commit detail GET403 so no new maintainer/merge claim. Prior S-AI coursework issue known from fresh baseline, execution remains unverified."),
    ("create-agent", "create-aimarket-agent", ["Python scaffolder", "TypeScript/npm scaffolder"],
     ["create-aimarket-agent", "alexar76/create-aimarket-agent"],
     ["create-aimarket-agent/README.md", "create-aimarket-agent/pyproject.toml", "create-aimarket-agent/npm/package.json"], [21,22], ["gh-repos-education", "gh-repos-education-page2"], ["npm-create-latest", "create-dependents"],
     "No new foreign generated project or independent tutorial confirmed in selected search. npm latest at read0.1.1, local sources0.1.2; dependents graph checks the published0.1.1 only. A generator can be used without remaining as a package dependency."),
    ("playground", "AIMarket Playground", ["bounded golden path", "provider/consumer starters"],
     ["alexar76/aimarket-playground", "play.modelmarket.dev", "aimarket-provider-check"],
     ["aimarket-playground/README.md"], [23,24], ["gh-repos-education", "gh-repos-education-page2"], [],
     "No new attributable foreign starter project, independent review or runtime integration confirmed. Own golden path, crosslinks and shared-name playgrounds excluded; no public invoke performed."),
    ("usecases", "AIMarket Use-cases Portal", ["onboarding portal and direction boards"],
     ["alexar76/use-cases-portal", "use.modelmarket.dev", "use-cases-portal"],
     ["use-cases-portal/README.md"], [25,26], ["gh-repos-education", "gh-repos-education-page2"], [],
     "No new exact external review or integration confirmed. GitHub topic mirror merely reproduces own repository metadata; generic use-case portal repository matches excluded from confirmed links.")
]

queries = []
for p in sorted(HERE.glob("search-*.json")):
    d = json.loads(p.read_text())
    for n, q in enumerate(d["args"]["search_query"], 1):
        queries.append({"id": len(queries) + 1, "batch_file": p.name, "position_in_batch": n, "query": q,
                        "batch_is_error": d["result"].get("isError", False),
                        "limit": "Batch response is not exhaustive per-query execution; exact/exclusion matching may be broadened."})
(HERE / "query-index.json").write_text(json.dumps(queries, ensure_ascii=False, indent=2) + "\n")
ghsummary = {}
for key in [x for x in bykey if x.startswith("gh-")]:
    r = bykey[key]
    if r.get("status") == 200:
        d = json.loads(body(key))
        ghsummary[key] = {"evidence": ev(key), "total_count": d.get("total_count"), "returned_items": len(d.get("items", [])),
                          "incomplete_results": d.get("incomplete_results"),
                          "limit": "Tokenized metadata/README or commit-message search; results require exact identity and ownership checks. Not authenticated code search."}
    else:
        ghsummary[key] = {"evidence": ev(key), "unknown": True}

families = []
for ident, title, subs, markers, paths, qids, ghkeys, primary, result in SPECS:
    if ident == "desktop":
        subs = [re.sub(r"^###\s*", "", line) for line in (ROOT / paths[0]).read_text().splitlines() if line.startswith("### ")]
    families.append({"id": ident, "name": title, "subcomponents": subs, "identity_markers": markers,
                     "metadata_provenance": provenance(paths, markers), "web_query_ids": qids,
                     "github_searches": {key: ghsummary[key] for key in ghkeys},
                     "primary_captures": [ev(key) for key in primary],
                     "result": result, "new_confirmed_independent_review": False, "new_confirmed_runtime_adoption": False,
                     "confidence": "High for captured pages or exact non-match in fetched README; limited for general absence, unreviewed hits or403."})
coverage = {"date_client": "2026-11-10", "families": families, "family_count": len(families),
            "excluded_topic": "HISTOR not investigated; incidental result text excluded.",
            "baseline": ["artifacts/external-links-2026-11-10/review.ru.md", "artifacts/external-links-deeper-2026-11-10/report.ru.md",
                         "docs/growth/external-use-pass8-2026-10-30.ru.md", "artifacts/external-signals-2026-11-09/report.ru.md"],
            "shared_limits": ["Public bounded sample, not the full internet or private code.",
                              "Each family has its own coverage row even when a grouped query includes several names.",
                              "Only selected plausible GitHub README candidates were read; all returned repositories were not cloned/scanned.",
                              "Grouped repository search frequently matches separate words in hyphenated names and is not an exact identity detector.",
                              "Subcomponents are inventoried explicitly; not every SKU/desk/lesson has an independent exhaustive code query."]}
(HERE / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")

decoded = {}
for key in ["besboy-team-readme", "starlight-readme", "attested-apiev-readme"]:
    d = json.loads(body(key))
    text = base64.b64decode(d["content"]).decode()
    decoded[key] = text
    (HERE / (key + ".md")).write_text(text)
falsepositives = []
for key, interpretation in [
    ("besboy-team-readme", "Team Memory OS is a distinct Russian stdlib/SQLite knowledge app with different API/routes; shared generic name alone does not establish our ecosystem."),
    ("starlight-readme", "Attested memory is used as a general concept in the Starlight project; no exact owner/domain/package identity links to our Attested Memory in fetched README.")]:
    matches = re.findall(r"(?i)alexar76|attestedmemory\.net|personal-attested-memory|expert-memory-market|aimarket", decoded[key])
    assert not matches
    falsepositives.append({"evidence": ev(key), "decoded_file": key + ".md", "exact_identity_matches": matches, "decision": interpretation,
                           "scope": "Fetched README only; the full repository tree was not scanned."})
(HERE / "false-positives.json").write_text(json.dumps(falsepositives, ensure_ascii=False, indent=2) + "\n")

depgraphs = []
for key in ["attested-dependents", "esim-dependents", "landing-dependents", "create-dependents"]:
    d = json.loads(body(key))
    depgraphs.append({"evidence": ev(key), **d,
                      "limit": "Version-scoped recorded dependency graph, not users/installations. Does not cover unrecorded/Git/CLI/generator use."})
(HERE / "dependency-graphs.json").write_text(json.dumps(depgraphs, ensure_ascii=False, indent=2) + "\n")

course_line = next(s for s in body("courses-ebookfoundation").splitlines() if "AIMarket Courses" in s)
course_href = "https://alexar76.github.io/aimarket-courses/"
assert course_href in course_line
learning_href = "https://github.com/alexar76/aimarket-courses/tree/main/orchestration-course"
assert learning_href in html("courses-learningstandard").links
novelty = {}
for url in [bykey[k]["url"] for k in ["courses-ebookfoundation", "courses-learningstandard", "attested-apisio", "domain-glama", "domain-glama-renew", "pingblip-game", "pingblip-announcement"]]:
    r = subprocess.run(["rg", "-l", "-F", url, "docs", "artifacts", "-g", "*.md", "-g", "*.json", "-g", "*.raw", "-g", "*.txt",
                        "-g", "!artifacts/external-components-2026-11-10/**"], cwd=ROOT, capture_output=True, text=True)
    novelty[url] = {"prior_matches": r.stdout.splitlines()[:25], "rg_exit": r.returncode,
                    "scope": "Prior docs/artifacts selected text extensions; entire current per-components pass excluded. A new capture route is not a new external relationship."}
(HERE / "novelty-check.json").write_text(json.dumps(novelty, ensure_ascii=False, indent=2) + "\n")

integrity = []
for r in captures:
    if r.get("body_file"):
        b = (HERE / r["body_file"]).read_bytes()
        integrity.append({"key": r["key"], "bytes_match": len(b) == r["bytes"], "sha256_match": hashlib.sha256(b).hexdigest() == r["sha256"]})
assert all(x["bytes_match"] and x["sha256_match"] for x in integrity)
(HERE / "capture-integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")

findings = {"date_client": "2026-11-10", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "counts": {"families": len(families), "web_query_strings": len(queries), "primary_gets": sum(not x.get("not_requested") for x in captures),
               "http_statuses": dict(Counter(str(x.get("status", "unknown")) for x in captures)),
               "github_repo_search_requests": len([k for k in ghsummary if "repos" in k]),
               "github_commit_search_requests": len([k for k in ghsummary if "commits" in k]),
               "new_confirmed_independent_product_reviews": 0, "new_confirmed_runtime_adoptions": 0,
               "dependency_graphs": len(depgraphs), "dependency_graphs_with_recorded_dependents": sum(x.get("totalCount", 0) > 0 for x in depgraphs)},
    "substantive_or_curated_references": [
        {"component": "AIMarket Courses", "source": "EbookFoundation/free-programming-books canonical course list", "evidence": ev("courses-ebookfoundation"),
         "target": course_href, "literal_markdown_line": course_line, "type": "curated_external_course_link_owner_submission_provenance",
         "event_provenance": {"commit_search": ev("gh-commits-education"), "commit": "b197a1cf7f8c62153dacc22a351253ae88ec840c", "commit_author_login": "alexar76", "commit_date": "2026-08-06T16:01:39+03:00", "subject": "Move AIMarket Courses into 0 - MOOC section (#13394)"},
         "novelty": "Current canonical list directly verified. The repository/fork coursework references were already in fresh baseline; not a newly published independent review.",
         "ownership_confidence": "High for foreign organization/source file and exact target; no new individual maintainer endorsement verified.",
         "limit": "Owner-authored move commit appears in official and fork histories. PR/commit detailed GET403, so no fresh merger/comment claim; clones not additional audiences or new users."},
        {"component": "AIMarket Courses / orchestration-course", "source": "The Learning Standard educational article", "evidence": ev("courses-learningstandard"),
         "target": learning_href, "event_date": "2026-09-22T22:45:39.837Z", "author_byline": "The Learning Standard (Organization)",
         "type": "external_topical_article_source_list", "novelty": "Known and verified Oct30; current exact href reconfirmed.",
         "ownership_confidence": "External publishing surface confirmed; legal ownership/human editorial work not independently verified.",
         "limit": "Course cited in Sources, not proof of taking the course, validating notebooks or adopting the protocol. About says active invariant evaluations have not yet been published; no course quality certification claimed."}
    ],
    "automated_presence_not_reviews": [
        {"component": "Attested Memory Hub / family", "evidence": [ev("attested-apisio"), ev("attested-apiev-repo"), ev("attested-apiev-readme")],
         "type": "generated_third_party_API_profile", "novelty": "Known APIs.io presence, reconfirmed. API Evangelist README explicitly describes third-party profiling, not operating our API.",
         "ownership_confidence": "Foreign GitHub organization and publisher self-disclosure; independent legal ownership unverified.",
         "limit": "Generated contracts/schemas/skills and scoring do not establish foreign use of our client, Personal/Team/Expert products or paid delivery."},
        {"component": "Domain Operator Kit", "evidence": [ev("domain-glama"), ev("domain-glama-renew")],
         "type": "automated_tool_description_assessment", "observed_schema_date_claim": "2026-10-20", "novelty": "Domain card already appears in accumulated search evidence; current tool-specific assessment is preserved without claiming new publication.",
         "ownership_confidence": "Foreign hosted assessment surface; human review not established.",
         "scope": "Seven-tool metadata assessed; renew feedback points to missing parameter/output/failure documentation. No domain registration, DNS change or Vercel attach performed."},
        {"component": "eSIM Operator Kit", "evidence": ev("esim-socket"), "type": "unread_search_candidate", "limit": "Direct403, no content/security claim adopted."}
    ],
    "own_distribution_not_external_reviews": [
        {"component": "PingBlip", "evidence": [ev("pingblip-game"), ev("pingblip-announcement")], "type": "owner_game_page_and_owner_launch_thread",
         "current_observation": "Game HTML exposes no reader comments; launch topic shows viewing posts1to1 and owner PingBlip. No new independent player review established.",
         "novelty": "Known October distribution surfaces, not new."}
    ],
    "exclusions": falsepositives,
    "limits": coverage["shared_limits"] + ["GitHub core rate-limit403 affected one candidate README and three detail requests; no credential/account/proxy switch, retry or bypass.",
        "Search-page1+page2 education returned all36 records, but their code was not cloned or comprehensively reviewed.",
        "Some commit search results were owner-authored despite requested exclusion; actual author/repository identity was checked and own syncs/fork copies excluded manually.",
        "No authenticated code search, private repositories, app analytics, payments or customer interviews.",
        "No confirmed new adoption in this sample is not proof of no users; package dependents omit many installation/use modes."],
    "coverage": "coverage.json", "capture_integrity": "capture-integrity.json", "external_writes": False, "github_writes": False,
    "messages": False, "logins": False, "payments_or_tools_call": False, "foreign_code_execution": False}
(HERE / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(findings["counts"], ensure_ascii=False))
