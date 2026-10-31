from pathlib import Path
from datetime import datetime,timezone
import json,re
ROOT=Path(__file__).resolve().parent
def load(name):return json.loads((ROOT/(name+".json")).read_text())
jobs=load("enterprise-ci-jobs")["jobs"]
workflow=(ROOT/"enterprise-ci-workflow.yml").read_text()
runs=load("enterprise-actions")["workflow_runs"]
run=next(x for x in runs if x["id"]==38629232333)
def walk(rows):
 for row in rows:
  yield row
  yield from walk(row.get("children",[]))
baseline_path=ROOT.parent/"external-signals-2026-10-30/social/raw/dev-comments-4804987.json"
old=list(walk(json.loads(baseline_path.read_text())))
current=list(walk(load("dev-comments-4804987")))
old_ids={x["id_code"] for x in old}
added=[{"id_code":x["id_code"],"created_at":x.get("created_at"),"author":x.get("user",{}).get("username")} for x in current if x["id_code"] not in old_ids]
out={
"observed_date":"2026-10-30","timezone":"Europe/Moscow",
"finding":{"kind":"new_verification_of_previously_known_external_fork_CI","repository":"th3artfuldodger/enterprise-factory","event_at_utc":run["created_at"],"event_at_msk":"2026-10-14 23:06","run":run["html_url"],"run_head_sha":run["head_sha"],"jobs":[{"name":j["name"],"url":j["html_url"],"conclusion":j["conclusion"],"selected_steps":[{"name":s["name"],"conclusion":s["conclusion"]} for s in j.get("steps",[]) if any(term in s["name"] for term in ["Fetch excluded satellite","Install backend","Factory pytest","Prod startup","Install","Build"])]} for j in jobs],"workflow_has_continue_on_error":"continue-on-error" in workflow,"frontend_build_command":"next build","root_tree_satellites_present":[],"backend_wrapper_caveat":"When coverage data exists, the CI wrapper may terminate a hung pytest process and succeed on coverage JSON generation; no claim all assertions passed. Backend logs GET403, no retry/bypass.","production_deployments_returned":len(load("enterprise-deployments")),"homepage_points_to_own_ecosystem":True,"limits":["Known fork from26Oct, not a new project or deployment30Oct","New evidence is non-skipped CI job steps, workflows and pinned source; no live foreign app endpoint","Backend checkout names main; exact checkout bytes not independently recovered from forbidden logs","Public account distinct from alexar76; beneficial ownership not investigated","No revenue, organic clients or successful autonomous production build established"]},
"response_delta":{"since_utc":"2026-10-30T07:25:26Z","github_search_candidates":len(load("recent-candidates")["candidates"]),"mcp_new_or_edited_comments":len(load("mcp-new-comments")),"agentdojo_new_or_edited_comments":len(load("agentdojo-new-comments")),"vulnetix_new_or_edited_comments":len(load("vulnetix-new-comments")),"histor_pr14":{"state":load("histor-pr14-current")["state"],"merged":load("histor-pr14-current")["merged"]},"dev":{"articles":62,"changed_thread":4804987,"previous_comments":len(old),"current_comments":len(current),"added_comments":added,"new_external_added_comments":sum(x["author"]!="alexar76" for x in added),"limits":"Unchanged DEV counters were not reread; comment edits without count change not covered."}},
"web_queries":sum(len(json.loads(p.read_text())["queries"]) for p in ROOT.glob("search-*.json")),"direct_gets":sum(len(json.loads(p.read_text())) for p in ROOT.glob("http-*index.json")),"new_independent_production_deployments_confirmed":0,
"mutations":"Local evidence only. No paid calls, messages, installations, foreign-code execution, GitHub/Gitea writes, account changes or deployments."
}
(ROOT/"summary.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"known_fork_ci_jobs":len(jobs),"added_dev":added,"new_external_comments":out["response_delta"]["dev"]["new_external_added_comments"]},ensure_ascii=False,indent=2))

