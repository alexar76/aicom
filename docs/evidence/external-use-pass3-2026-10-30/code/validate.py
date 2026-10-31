from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).parent
rows=[]
for n in ["http-index.json","http-version-index.json","http-followup-index.json","http-candidates-index.json"]:
 rows.extend(json.loads((ROOT/n).read_text()))
errors=[]
for r in rows:
 if r.get("file") and hashlib.sha256((ROOT/r["file"]).read_bytes()).hexdigest()!=r.get("sha256"):errors.append(r["key"])
summary={"date":"2026-10-30","timezone":"Europe/Moscow","web_queries":16,"captured_gets":len(rows),"new_independent_runtime_use_verified":False,"new_independent_mention_verified":False,"new_coverage":{"warden_versions_not_previously_queried":19,"known_versions_not_requeried":["0.8.2","0.15.0","0.22.2"],"new_direct_dependents":"Only own ARGUS aliases/versions; provenance checked","rust_reverse_dependents":0,"dart_registry_dependency_search":0,"fork_histories_closed":3,"fork_histories_result":"Each accessible default history contains public snapshot and coverage bot commit only","new_commit_searches":6,"sourcegraph_secondary_markers":"done=true, matchCount=0"},"repeated_findings_not_counted":["QuincyGB","traits-dev","Industrial Platform","RugSnare","MCPMoat","agent-exec","Enterprise Factory","awesome-list mirrors"],"limitations":["Registry graphs do not cover private or unpublished apps, manual installs or HTTP calls","Sourcegraph and GitHub searches are incomplete","Default fork histories only; no other branches or private state"],"report":"report.ru.md"}
(ROOT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
(ROOT/"verification-index.json").write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),"captured_gets":len(rows),"successful_bodies_verified":sum(r.get("status")==200 for r in rows),"hash_errors":errors,"reads":rows},ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"gets":len(rows),"hash_errors":errors,"statuses":{str(s):sum(r.get("status")==s for r in rows) for s in set(r.get("status") for r in rows)}},indent=2))
assert not errors

