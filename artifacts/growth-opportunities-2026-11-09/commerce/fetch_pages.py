from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).parent
TASKS={'home':'https://modelmarket.dev/','start':'https://modelmarket.dev/start','tools':'https://modelmarket.dev/tools/','docs':'https://modelmarket.dev/docs/'}
def get(item):
 key,url=item;row={'key':key,'url':url,'method':'GET','at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 (public page review; read-only)'}),timeout=40) as r:
   data=r.read(6000000);row.update(status=r.status,final_url=r.url,file=key+'.html',bytes=len(data),sha256=hashlib.sha256(data).hexdigest());(ROOT/row['file']).write_bytes(data)
 except HTTPError as e:
  data=e.read(1000000);row.update(status=e.code,error=str(e),file=key+'.html',bytes=len(data),sha256=hashlib.sha256(data).hexdigest());(ROOT/row['file']).write_bytes(data)
 except Exception as e:row['error']=str(e)
 return row
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(get,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
