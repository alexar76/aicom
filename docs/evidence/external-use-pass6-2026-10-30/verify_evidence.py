"""Verify local read-only audit captures; derive the payer attribution without executing remote code."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
REPORT = REPO / "docs/growth/external-use-pass6-2026-10-30.ru.md"
load = lambda name: json.loads((ROOT / name).read_text())

documents = {path.name: json.loads(path.read_text()) for path in ROOT.glob("*.json")}
sources = [row for path in sorted(ROOT.glob("http-*index.json")) for row in documents[path.name]]
statuses = Counter(row["status"] for row in sources)
verified = 0
for source in sources:
    assert source["method"] == "GET"
    if source["status"] != 200:
        assert source["name"] == "grepapp-warden" and source["status"] == 429
        continue
    body = (ROOT / source["body_file"]).read_bytes()
    assert len(body) == source["bytes"], source["name"]
    assert hashlib.sha256(body).hexdigest() == source["sha256"], source["name"]
    verified += 1

page = (ROOT / "aer-current.raw").read_text()
section = page.split("Who pays it (top organic agents)", 1)[1].split("</table>", 1)[0]
prefixes = re.findall(r"<code>(0x[0-9a-fA-F]+)…</code>", section)
assert len(prefixes) == 3
own_wallet = "0x097e3f339d0b023605e12a6b81e2d6cb7571475a"
ownership_sources = ["docs/pay-on-verified-demo.md", "docs/start-onboarding-demo.md"]
local_evidence = []
for relative in ownership_sources:
    body = (REPO / relative).read_bytes()
    assert own_wallet in body.decode().lower()
    local_evidence.append({"file": relative, "sha256": hashlib.sha256(body).hexdigest(),
                           "role": "Explicit disclosure that this buyer is our own funded test wallet"})
use_tested = load("usetested-current.json")
assert len(use_tested["receipts"]) == 1 and use_tested["measured"]["calls_tested"] == 1
test_receipt = use_tested["receipts"][0]
test_wallet = test_receipt["payer"].lower()
old_base_receipt = REPO / "artifacts/external-signals-2026-10-29/metrics/usetested-basescan.body"
old_base_raw = old_base_receipt.read_bytes()
assert test_wallet in old_base_raw.decode().lower()
local_evidence.append({"file": str(old_base_receipt.relative_to(REPO)),
                       "sha256": hashlib.sha256(old_base_raw).hexdigest(),
                       "role": "Previously captured public BaseScan transaction matching the UseTested payer"})
attributions = []
for prefix in prefixes:
    if own_wallet.startswith(prefix.lower()):
        kind = "our_funded_test_wallet"
        address = own_wallet
    elif test_wallet.startswith(prefix.lower()):
        kind = "previously_known_UseTested_single_paid_test"
        address = test_wallet
    else:
        kind = "unattributed_candidate"
        address = None
    attributions.append({"aer_displayed_prefix": prefix, "candidate_full_address": address,
                         "classification": kind, "match_basis": "Displayed prefix only; AER does not disclose the full wallet here"})
assert Counter(row["classification"] for row in attributions) == {
    "our_funded_test_wallet": 1, "previously_known_UseTested_single_paid_test": 1, "unattributed_candidate": 1}

sg = []
for path in sorted(ROOT.glob("sourcegraph-*.raw")):
    frames = path.read_text().split("\n\n")
    progress = [json.loads(line[6:]) for frame in frames if frame.startswith("event: progress")
                for line in frame.splitlines() if line.startswith("data: ")]
    assert progress and progress[-1]["done"]
    sg.append({"file": path.name, "returned_matches": progress[-1]["matchCount"],
               "skipped": progress[-1]["skipped"]})

repos = load("ecosystem-repos-1.json")
assert len(repos) < 100
github = [{"file": path.name, "total_count": documents[path.name]["total_count"],
           "returned_items": len(documents[path.name]["items"]),
           "incomplete_results": documents[path.name]["incomplete_results"]}
          for path in sorted(ROOT.glob("*.json"))
          if isinstance(documents[path.name], dict) and "incomplete_results" in documents[path.name]]
old_dev = json.loads((REPO / "docs/evidence/external-use-pass5-2026-10-30/dev-current-list.json").read_text())
old_counts = {article["id"]: article["comments_count"] for article in old_dev}
dev = load("dev-list-current.json")
changed_dev = [article["id"] for article in dev if article["comments_count"] != old_counts.get(article["id"], 0)]
old_peers = json.loads((REPO / "docs/evidence/external-signals-deeper-2026-10-30/root/hub-peers.json").read_text())
peers = load("hub-peers-current.json")
new_peer_urls = {key: [peer["url"] for peer in peers.get(key, [])
                       if peer["url"] not in {p["url"] for p in old_peers.get(key, [])}]
                 for key in ["peers", "pending"]}
rating = load("aer-free-snapshot.json")
query_index = load("query-index.json")
summary = {
    "observed_date": "2026-10-30", "timezone": "Europe/Moscow",
    "finding_kind": "attribution_correction_of_previously_known_aggregate_demand_signal",
    "aer": {key: rating[key] for key in ["as_of", "tier", "tier_raw", "organic_paying_agents", "paying_wallets_raw", "settled_usd_14d"]},
    "aer_displayed_top_payers_attribution": attributions,
    "aer_limits": ["Prefix matching, not disclosure of full AER wallet IDs", "Raw payment graph is not published in the open dataset", "No recomputation of AER rating or its hidden graph", "One unassigned prefix is not a verified outside customer or delivered workflow"],
    "known_UseTested_receipt": test_receipt,
    "local_ownership_and_chain_evidence": local_evidence,
    "new_independent_mentions_confirmed": 0,
    "new_independent_runtime_deployments_confirmed": 0,
    "github_searches": github,
    "sourcegraph": sg,
    "ecosystem_repository_count": len(repos),
    "repositories_with_forks": [{"repo": repo["full_name"], "forks": repo["forks_count"]} for repo in repos if repo["forks_count"]],
    "gateway_fork": {"name": "adity982/aimarket-mcp", "commits_returned": len(load("gateway-fork-history.json")),
                     "action_runs": load("gateway-fork-actions.json")["total_count"],
                     "interpretation": "One monorepo sync snapshot; no independent change or execution established"},
    "dev_delta": {"articles": len(dev), "changed_counters": changed_dev,
                  "limits": "Thread bodies not reread when counters unchanged; edits not covered"},
    "peer_delta": {"current_active_list": len(peers.get("peers", [])), "current_pending_list": len(peers.get("pending", [])), "new_urls": new_peer_urls,
                   "limits": "Our operator telemetry, not independent demand evidence"},
    "web_queries": query_index["current_queries"], "exact_prior_query_matches": query_index["exact_repeats"],
    "direct_public_gets": len(sources), "http_statuses": {str(k): v for k, v in statuses.items()},
    "body_hashes_verified": verified,
    "mutations": "Local audit documents and evidence only; no purchases, messages, paid APIs, foreign code execution, installs or GitHub/Gitea writes"
}
(ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
index = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
         "first_get_at_utc": min(row["retrieved_at_utc"] for row in sources),
         "last_get_at_utc": max(row["retrieved_at_utc"] for row in sources),
         "direct_public_gets": len(sources), "http_statuses": summary["http_statuses"],
         "body_hashes_verified": verified, "sources": sources,
         "local_evidence": local_evidence, "report": "../../growth/" + REPORT.name}
(ROOT / "audit-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
local_links = []
for target in re.findall(r"\]\(([^)]+)\)", REPORT.read_text()):
    if "://" in target or target.startswith("#"):
        continue
    path = (REPORT.parent / unescape(target).split("#", 1)[0]).resolve()
    assert path.is_file(), target
    local_links.append(target)
print(json.dumps({"public_gets": len(sources), "statuses": summary["http_statuses"],
                  "hashes_verified": verified, "web_queries": summary["web_queries"],
                  "payer_classes": dict(Counter(row["classification"] for row in attributions)),
                  "report_local_links_checked": len(local_links)}, ensure_ascii=False, indent=2))
