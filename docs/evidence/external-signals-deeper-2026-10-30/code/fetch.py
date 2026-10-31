"""Public GET-only deeper code search; no credentials or execution of remote code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import hashlib,json
ROOT=Path(__file__).parent
QUERIES={
 "issues-hub":("issues",'"aimarket-hub" -user:alexar76 -author:alexar76'),
 "issues-agent":("issues",'"aimarket-agent" -user:alexar76 -author:alexar76'),
 "issues-memory":("issues",'"attestedmemory.net" -user:alexar76 -author:alexar76'),
 "issues-awr":("issues",'"alexar76/awr" -user:alexar76 -author:alexar76'),
 "commits-identity":("commits",'"alexar76" -author:alexar76'),
 "commits-hub":("commits",'"aimarket-hub" -author:alexar76'),
 "commits-warden":("commits",'"@aimarket/warden" -author:alexar76'),
 "commits-memory":("commits",'"attestedmemory.net" -author:alexar76'),
}
TASKS={k:'https://api.github.com/search/'+kind+'?'+urlencode({'q':q,'per_page':100,'sort':'updated' if kind=='issues' else 'committer-date','order':'desc'}) for k,(kind,q) in QUERIES.items()}
TASKS.update({
 "sourcegraph-packages":"https://sourcegraph.com/search/stream?"+urlencode({"q":r'context:global patterntype:regexp (@aimarket/warden|aimarket-hub|aimarket-histor|aimarket-agent) -repo:^github.com/alexar76/ -file:(?i)readme archived:yes fork:yes count:200 timeout:40s',"v":"V3"}),
 "sourcegraph-domains":"https://sourcegraph.com/search/stream?"+urlencode({"q":r'context:global patterntype:regexp (modelmarket\.dev|attestedmemory\.net) -repo:^github.com/alexar76/ -file:(?i)readme archived:yes fork:yes count:200 timeout:40s',"v":"V3"}),
 "industrial-tree":"https://api.github.com/repos/industrial-platform-ai/industrial-platform-agent-tools/git/trees/main?recursive=1",
 "rugsnare-tree":"https://api.github.com/repos/Paraphern/rugsnare/git/trees/main?recursive=1",
 "mcpmoat-tree":"https://api.github.com/repos/Ducarv/mcpmoat/git/trees/dev?recursive=1",
 "codeberg-projects":"https://codeberg.org/api/v1/repos/search?q=aimarket&limit=50",
 "gitlab-projects-package":"https://gitlab.com/api/v4/projects?search=aimarket&simple=true&per_page=100",
})
def fetch(t):
 key,url=t;row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 (alexar76 public evidence audit; read-only)','Accept':'application/json,text/event-stream,text/plain,*/*'}),timeout=55) as r:
   raw=r.read(15000000); row.update(status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file=key+'.raw')
  (ROOT/row['file']).write_bytes(raw)
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e)
 return row
if __name__=='__main__':
 ROOT.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=4) as p:rows=list(p.map(fetch,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(rows,ensure_ascii=False,indent=2))

