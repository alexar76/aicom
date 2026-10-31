"""Public GET-only follow-up: publisher feeds and exact HN comment searches."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
ROOT=Path(__file__).resolve().parent
TASKS=[
("bsky-authorfeed","https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?"+urlencode({"actor":"alexar76.bsky.social","limit":100})),
]
for q in ['histor.modelmarket.dev','@aimarket/warden','attestedmemory.net','"We installed 12,915"','"Same MCP version"']:
 TASKS.append(("hn-"+str(len(TASKS)),"https://hn.algolia.com/api/v1/search?"+urlencode({"query":q,"tags":"comment","hitsPerPage":100,"typoTolerance":"false"})))
for user in ["quincygb","paul_irolla_6b5ae261d0224","swarmagentoperator","heyitsjakub","launchgatecheck","galagent"]:
 TASKS.append(("dev-feed-"+user,"https://dev.to/api/articles?"+urlencode({"username":user,"per_page":100})))
def get(task):
 key,url=task;r={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 public evidence read-only"}),timeout=25) as x:
   raw=x.read();r.update(status=x.status,final_url=x.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  (ROOT/"raw").mkdir(exist_ok=True);filename="raw/"+key+".json";(ROOT/filename).write_bytes(raw);r["file"]=filename
 except HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 return r
if __name__=="__main__":
 ROOT.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=2) as p:rows=list(p.map(get,TASKS))
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps([{"key":r["key"],"status":r.get("status"),"bytes":r.get("bytes")} for r in rows]))

