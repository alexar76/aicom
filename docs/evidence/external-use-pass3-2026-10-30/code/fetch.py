"""New public-only code/use probes, excluding prior exact queries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import hashlib,json
ROOT=Path(__file__).parent
QUERIES={
 "commits-awr-verify":'"@alexar76/awr-verify" -user:alexar76',
 "commits-awr-emitter":'"awr-emitter" -user:alexar76',
 "commits-bridges":'"aimarket-bridges" -user:alexar76',
 "commits-gateway":'"aimarket-mcp" -user:alexar76',
 "commits-oracle":'"aimarket-oracle-gateway" -user:alexar76',
 "commits-dart":'"aimarket_agent" -user:alexar76',
}
TASKS={k:"https://api.github.com/search/commits?"+urlencode({"q":q,"per_page":100,"sort":"committer-date","order":"desc"}) for k,q in QUERIES.items()}
TASKS.update({
 "sourcegraph-secondary-packages":"https://sourcegraph.com/search/stream?"+urlencode({"q":r'context:global patterntype:regexp (aimarket-bridges|aimarket_oracle_gateway|awr-emitter|@alexar76/awr-(verify|emit)|aimarket_agent) -repo:^github.com/alexar76/ -file:(?i)readme archived:yes fork:yes count:200 timeout:40s',"v":"V3"}),
 "warden-registry":"https://registry.npmjs.org/%40aimarket%2Fwarden",
 "dart-dependents":"https://pub.dev/packages?q=dependency%3Aaimarket_agent",
})
def fetch(task):
 key,url=task;row={"key":key,"url":url,"method":"GET","retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (public evidence audit; read-only)","Accept":"application/json,text/event-stream,text/plain,*/*"}),timeout=55) as r:
   raw=r.read(20000000);row.update(status=r.status,final_url=r.url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),file=key+".raw")
  (ROOT/row["file"]).write_bytes(raw)
 except HTTPError as e:row.update(status=e.code,error=str(e))
 except Exception as e:row.update(error=str(e))
 return row
if __name__=="__main__":
 ROOT.mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,TASKS.items()))
 (ROOT/"http-index.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(rows,ensure_ascii=False,indent=2))

