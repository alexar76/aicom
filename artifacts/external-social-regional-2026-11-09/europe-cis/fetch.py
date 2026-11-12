from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from datetime import datetime,timezone
from urllib.parse import urlencode
import hashlib,json
ROOT=Path(__file__).parent
TASKS={
 'habr-native-domain':'https://habr.com/kek/v2/articles/?'+urlencode({'query':'"modelmarket.dev"','fl':'ru','hl':'ru'}),
 'habr-native-identity':'https://habr.com/kek/v2/articles/?'+urlencode({'query':'"alexar76"','fl':'ru','hl':'ru'}),
 'habr-candidate':'https://habr.com/ru/amp/publications/1076614/',
 'radyz-known':'https://radyz.cz/rychle-zpravy/histor-otevrel-dataset-zmen-nastroju-mcp-nikoli-seznam-skodlivych-serveru/',
 'mcp-catalog-known':'https://mcp-catalog.ru/servers/alexar76/aimarket-mcp',
 'radyz-native-search':'https://radyz.cz/?s=HISTOR',
}
def get(item):
 key,url=item;row={'key':key,'url':url,'method':'GET','at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 (public read-only evidence audit)','Accept':'application/json,text/html,*/*'}),timeout=45) as r:
   data=r.read(8000000);row.update(status=r.status,final_url=r.url,file=key+'.raw',bytes=len(data),sha256=hashlib.sha256(data).hexdigest());(ROOT/row['file']).write_bytes(data)
 except HTTPError as e:
  data=e.read(1000000);row.update(status=e.code,error=str(e),file=key+'.raw',bytes=len(data),sha256=hashlib.sha256(data).hexdigest());(ROOT/row['file']).write_bytes(data)
 except Exception as e:row['error']=str(e)
 return row
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(get,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
