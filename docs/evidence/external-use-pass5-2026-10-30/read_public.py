"""GET-only fresh external-signal and external-fork checks."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import quote
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
import json,hashlib
ROOT=Path(__file__).resolve().parent
SINCE="2026-10-30T07:25:26Z"
QUERIES=[
("mentions-recent","mentions:alexar76 updated:>=2026-10-30 -user:alexar76"),
("incoming-issues-recent","user:alexar76 is:issue -author:alexar76 updated:>=2026-10-30"),
("external-domain-recent",'"modelmarket.dev" -user:alexar76 -author:alexar76 updated:>=2026-10-30'),
]
TASKS=[(name,"https://api.github.com/search/issues?q="+quote(q,safe="")+"&sort=updated&order=desc&per_page=100") for name,q in QUERIES]+[
("enterprise-repo","https://api.github.com/repos/th3artfuldodger/enterprise-factory"),
("enterprise-actions","https://api.github.com/repos/th3artfuldodger/enterprise-factory/actions/runs?per_page=20"),
("enterprise-deployments","https://api.github.com/repos/th3artfuldodger/enterprise-factory/deployments?per_page=20"),
("enterprise-readme","https://api.github.com/repos/th3artfuldodger/enterprise-factory/contents/README.md"),
]
def get(task):
 name,url=task;r={"name":name,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public external-signal audit; read-only)"}),timeout=25) as h:
   raw=h.read();r.update(status=h.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),content_type=h.headers.get("Content-Type",""),rate_remaining=h.headers.get("X-RateLimit-Remaining"))
  filename=name+(".json" if "json" in r["content_type"] else ".raw");(ROOT/filename).write_bytes(raw);r["body_file"]=filename
 except HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 return r
if __name__=="__main__":
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(get,TASKS))
 candidates=[]
 for r in rows[:3]:
  if r.get("status")==200:
   d=json.loads((ROOT/r["body_file"]).read_text())
   for item in d.get("items",[]):
    if item.get("updated_at","")>SINCE:
     candidates.append({k:item.get(k) for k in ["html_url","title","created_at","updated_at","comments","comments_url"]})
 (ROOT/"recent-candidates.json").write_text(json.dumps({"since_utc":SINCE,"candidates":candidates},ensure_ascii=False,indent=2)+"\n")
 for i,c in enumerate({x["comments_url"]:x for x in candidates if x.get("comments_url")}.values()):
  rows.append(get(("recent-comments-"+str(i),c["comments_url"]+"?per_page=100")))
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"reads":[{"name":r["name"],"status":r.get("status"),"bytes":r.get("bytes")} for r in rows],"candidates":candidates},ensure_ascii=False,indent=2))

