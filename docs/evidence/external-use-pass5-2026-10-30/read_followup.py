from read_public import get,ROOT,SINCE
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import base64,json
initial=json.loads((ROOT/"enterprise-actions.json").read_text())
run=next(x for x in initial.get("workflow_runs",[]) if x.get("id")==38629232333)
sha=run["head_sha"];workflow=run["path"].split("@",1)[0]
tasks=[
("enterprise-ci-jobs","https://api.github.com/repos/th3artfuldodger/enterprise-factory/actions/runs/38629232333/jobs?per_page=100"),
("enterprise-ci-workflow","https://api.github.com/repos/th3artfuldodger/enterprise-factory/contents/"+workflow+"?ref="+sha),
("histor-pr14-current","https://api.github.com/repos/basitalisandhu/agent-skills-state-2026/pulls/14"),
("mcp-new-comments","https://api.github.com/repos/modelcontextprotocol/modelcontextprotocol/issues/3431/comments?since="+quote(SINCE,safe="")+"&per_page=100"),
("agentdojo-new-comments","https://api.github.com/repos/ethz-spylab/agentdojo/issues/235/comments?since="+quote(SINCE,safe="")+"&per_page=100"),
("vulnetix-new-comments","https://api.github.com/repos/Vulnetix/advisory-database/issues/5/comments?since="+quote(SINCE,safe="")+"&per_page=100"),
("dev-current-list","https://dev.to/api/articles?username=alexar76&per_page=100"),
]
with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,tasks))
r=next(x for x in rows if x["name"]=="enterprise-ci-workflow")
if r.get("status")==200:
 d=json.loads((ROOT/r["body_file"]).read_text());text=base64.b64decode(d["content"]).decode();(ROOT/"enterprise-ci-workflow.yml").write_text(text)
baseline=json.loads((ROOT.parents[0]/"external-signals-2026-10-30/social/complete-summary.json").read_text())
old={x["id"]:x.get("metadata_comments",x.get("read_comments",0)) for x in baseline["threads"]}
dev=next(x for x in rows if x["name"]=="dev-current-list")
changed=[]
if dev.get("status")==200:
 articles=json.loads((ROOT/dev["body_file"]).read_text())
 for a in articles:
  count=a.get("comments_count",0)
  if count>old.get(a["id"],0):
   changed.append({k:a.get(k) for k in ["id","url","title","comments_count","published_at"]})
 for a in changed:
  rows.append(get(("dev-comments-"+str(a["id"]),"https://dev.to/api/comments?a_id="+str(a["id"]))))
(ROOT/"changed-dev-threads.json").write_text(json.dumps({"previous_scope_articles":62,"current_scope_articles":len(articles) if dev.get("status")==200 else None,"changed_threads":changed},ensure_ascii=False,indent=2)+"\n")
(ROOT/"http-followup-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps([{"name":r["name"],"status":r.get("status"),"bytes":r.get("bytes")} for r in rows],indent=2))

