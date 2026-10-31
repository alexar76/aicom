"""New public GET-only plugin/widget downstream evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote,urlencode
import json,hashlib
ROOT=Path(__file__).resolve().parent
def fetch(task):
 key,url=task;row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public read-only ecosystem adoption audit)","Accept":"application/json"}),timeout=25) as r:
   raw=r.read();row.update(status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  file=key+".raw";(ROOT/file).write_bytes(raw);row["file"]=file
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(status=None,error=str(e))
 return row
if __name__=="__main__":
 tasks=[]
 plugins=[("aimarket-safety","2.0.1"),("aimarket-channels","2.0.1"),("aimarket-tee","2.0.1"),("aimarket-reputation","2.0.1"),("aimarket-orchestrator","2.0.0"),("aimarket-streaming","2.0.1"),("aimarket-mcp-packager","2.1.3"),("aimarket-zk","2.1.1"),("aimarket-data-cap","3.0.0"),("aimarket-dataset","2.0.0")]
 for name,version in plugins:
  tasks.append(("deps-"+name,"https://deps.dev/_/s/pypi/p/"+quote(name,safe="")+"/v/"+quote(version,safe="")+"/dependents"))
 for name,version in [("@aimarket/widget","0.1.1"),("@aimarket/hub-client","0.0.1"),("@aimarket/sdk","0.0.1")]:
  tasks.append(("deps-npm-"+name.replace("@","").replace("/","-"),"https://deps.dev/_/s/npm/p/"+quote(name,safe="")+"/v/"+quote(version,safe="")+"/dependents"))
 queries=[
 ('"aimarket-safety" -user:alexar76',"commits","commit-safety"),
 ('"aimarket-channels" -user:alexar76',"commits","commit-channels"),
 ('"aimarket-mcp-packager" -user:alexar76',"commits","commit-packager"),
 ('"@aimarket/widget" -user:alexar76',"commits","commit-widget"),
 ('"aimarket-safety" in:readme -user:alexar76',"repositories","repo-safety"),
 ('"aimarket-mcp-packager" in:readme -user:alexar76',"repositories","repo-packager"),
 ]
 for q,kind,key in queries:
  tasks.append((key,"https://api.github.com/search/"+kind+"?"+urlencode({"q":q,"per_page":100,"sort":"updated" if kind=="repositories" else "committer-date","order":"desc"})))
 (ROOT/"scope.json").write_text(json.dumps({"plugin_versions":plugins,"api_queries":[{"q":q,"kind":kind,"key":key} for q,kind,key in queries],"note":"Plugin versions identify selected local published candidates; package metadata identity is checked for any external dependent before attribution."},indent=2)+"\n")
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,tasks))
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 for row in rows:
  print(row["key"],row.get("status"),end=" ")
  if row.get("status")==200:
   d=json.loads((ROOT/row["file"]).read_text())
   if row["key"].startswith("deps"):print(d.get("totalCount"),d.get("directSample"))
   else:print(d.get("total_count"),[(x.get("repository",{}).get("full_name") or x.get("full_name"),x.get("html_url"),x.get("commit",{}).get("message","")[:180]) for x in d.get("items",[])[:15]])
  else:print(row.get("error"))
 
