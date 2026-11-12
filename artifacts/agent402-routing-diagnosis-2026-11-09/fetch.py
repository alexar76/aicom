from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import hashlib,json
ROOT=Path(__file__).parent
TASKS={
 'source-commit':'https://api.github.com/repos/MikeyPetrillo/Agent402/commits/main',
 'source-tree':'https://api.github.com/repos/MikeyPetrillo/Agent402/git/trees/main?recursive=1',
 'index-modelmarket':'https://agent402.tools/api/index?seller=modelmarket.dev',
 'route-warden':'https://agent402.tools/api/route?task=scan%20MCP%20tool%20definitions&include=external&target=https%3A%2F%2Fmodelmarket.dev%2Fx402%2Fwarden-scan',
 'seller-modelmarket':'https://agent402.tools/api/leaderboard?seller=modelmarket.dev',
 'leaderboard':'https://agent402.tools/api/leaderboard',
 'transparency':'https://agent402.tools/transparency',
}
def fetch(item):
 key,url=item;row={'key':key,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 (public read-only diagnosis)','Accept':'application/json,text/html,text/plain,*/*'}),timeout=45) as r:
   data=r.read(30000000);row.update(status=r.status,final_url=r.url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),file=key+'.raw')
   (ROOT/row['file']).write_bytes(data)
 except HTTPError as e:
  data=e.read(1000000);row.update(status=e.code,error=str(e),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),file=key+'.raw');(ROOT/row['file']).write_bytes(data)
 except Exception as e:row['error']=str(e)
 return row
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
