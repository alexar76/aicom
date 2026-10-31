"""Validate saved audit captures and their claims locally; no network access."""
from collections import Counter
from datetime import datetime, timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
REPORT = REPO / "docs/growth/external-use-pass7-2026-10-30.ru.md"
documents = {path.name: json.loads(path.read_text()) for path in ROOT.glob("*.json")}
sources = [row for path in sorted(ROOT.glob("http-*index.json")) for row in documents[path.name]]
statuses = Counter(row["status"] for row in sources)
for row in sources:
    assert row["method"] == "GET"
    if row["status"] != 200:
        assert row["status"] == 401, row
        continue
    body = (ROOT / row["body_file"]).read_bytes()
    assert len(body) == row["bytes"], row["name"]
    assert hashlib.sha256(body).hexdigest() == row["sha256"], row["name"]

payer = documents["payer-attribution.json"]
assert len(payer["operator_table_matches"]) == 1
payment = payer["operator_table_matches"][0]
assert payment["amount_usdc"] == "0.03" and payment["official_base_usdc"]
assert payment["tx"] == "0xb1c54f290cd1ec7cd98e0537f0068aee15ceec978f2313ba33fb048c15913dd5"
assert payment["payer"] == payer["candidate_address"] and payment["recipient"] == payer["operator_address"]
detail = (ROOT / "unattributed-payment-tx.raw").read_text()
description = re.search(r'<meta name="Description" content="([^"]+)"', detail).group(1)
assert "Success" in description and "0.03 USDC" in description
assert all(value in detail.lower() for value in [payment["tx"], payment["payer"], payment["recipient"], "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"])
event = datetime.strptime(payment["date_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

prior_matches = []
for parent in [REPO / "docs", REPO / "artifacts"]:
    for path in parent.rglob("*"):
        if not path.is_file() or ROOT in path.parents or path.suffix not in [".json", ".md", ".body", ".html", ".raw", ".txt"]:
            continue
        if path.stat().st_size > 4000000:
            continue
        # Reports for this pass deliberately link the newly verified payment.
        if path == REPORT or path.name == "external-use-pass6-2026-10-30.ru.md":
            continue
        try:
            if payment["tx"] in path.read_text().lower():
                prior_matches.append(str(path.relative_to(REPO)))
        except UnicodeError:
            pass

scope = documents["query-index.json"]
searches = [{"name": row["name"], "total": documents[row["body_file"]]["total_count"],
             "incomplete": documents[row["body_file"]]["incomplete_results"]}
            for row in sources if row["status"] == 200 and "api.github.com/search/" in row["url"]]
fresh_cutoff = "2026-10-30T12:14:35Z"
fresh_candidates = [item["html_url"] for name in ["incoming-fresh.json", "mentions-fresh.json"]
                    for item in documents[name]["items"] if item["updated_at"] > fresh_cutoff]

summary = {
    "observed_date": "2026-10-30", "display_timezone": "Europe/Amsterdam",
    "finding_kind": "new_transaction_evidence_for_previously_unattributed_AER_prefix",
    "payment": {key: value for key, value in payment.items() if key != "raw"},
    "event_at_utc": event.isoformat(),
    "event_at_amsterdam": event.astimezone(ZoneInfo("Europe/Amsterdam")).isoformat(),
    "explorer_transaction_description": description,
    "prior_exact_transaction_mentions_found": prior_matches,
    "prior_scan_limits": "Accessible docs/artifacts text files under 4 MB; exclusions: this pass and its predecessor link",
    "payer_recent_page": {key: payer[key] for key in ["payer_table_rows", "outbound_official_usdc_rows", "unique_outbound_recipients", "outbound_by_day", "outbound_amounts"]},
    "attribution_limits": ["AER only reveals a prefix, matched to the full address in the explorer", "The event happened on25Oct; it is not a new payment30Oct", "Beneficial owner and independence from us have not been established", "No HTTP endpoint, request input, delivered response, application workflow or repeat purchase of our service was established", "Single 50-row payer page is not the complete history", "Roundhouse actor labels and payment catalog grouping are observer inferences, not identified customers"],
    "new_independent_runtime_use_confirmed": False,
    "new_independent_social_or_regional_mentions_confirmed": False,
    "github_searches": searches,
    "fresh_issue_window": {"after_utc": fresh_cutoff, "returned_candidates": fresh_candidates},
    "web_search": {key: value for key, value in scope.items() if key != "queries"},
    "direct_public_gets": len(sources), "http_statuses": {str(key): value for key, value in statuses.items()},
    "body_hashes_verified": statuses[200],
    "access_limits": ["Four stargazer GETs401; no authentication changes or retries", "Roundhouse advertised API GET401; no keys or paid requests used", "Four web query strings in an error batch and four in a robots-blocked batch are not successful coverage", "Apple guide matched generic historical text rather than the ecosystem"],
    "mutations": "Local audit files only. No purchases, paid APIs, invokes, messages, installs, foreign code execution, deployments, authentication changes or GitHub/Gitea writes."
}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
index = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "display_timezone": "Europe/Amsterdam",
         "first_get_at_utc": min(row["retrieved_at_utc"] for row in sources),
         "last_get_at_utc": max(row["retrieved_at_utc"] for row in sources),
         "direct_public_gets": len(sources), "http_statuses": summary["http_statuses"],
         "body_hashes_verified": statuses[200], "sources": sources,
         "report": "../../growth/" + REPORT.name}
(ROOT / "audit-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
local_links = []
for target in re.findall(r"\]\(([^)]+)\)", REPORT.read_text()):
    if "://" in target or target.startswith("#"):
        continue
    assert (REPORT.parent / unescape(target).split("#", 1)[0]).resolve().is_file(), target
    local_links.append(target)
print(json.dumps({"gets": len(sources), "statuses": summary["http_statuses"], "body_hashes_verified": statuses[200],
                  "payment_usdc": payment["amount_usdc"], "event_at_amsterdam": summary["event_at_amsterdam"],
                  "prior_exact_transaction_mentions": len(prior_matches), "local_links_checked": len(local_links)}, indent=2))
