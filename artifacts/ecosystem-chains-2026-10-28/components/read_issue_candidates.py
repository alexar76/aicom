from pathlib import Path
import urllib.request,json,hashlib
from datetime import datetime,timezone
urls=['https://api.github.com/repos/datafund/swarm_connect/issues/467','https://api.github.com/repos/datafund/swarm_connect/issues/467/comments?per_page=100','https://api.github.com/repos/Nikolife2016/pulsefeed-x402/issues/3/comments?per_page=100&page=1','https://api.github.com/repos/Nikolife2016/pulsefeed-x402/issues/3/comments?per_page=100&page=2']
records=[]
for url in urls:
 rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
   body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
   xs=d if isinstance(d,list) else [d]
   rec['records']=[{'html_url':x.get('html_url'),'user':x.get('user',{}).get('login'),'created_at':x.get('created_at'),'updated_at':x.get('updated_at'),'body':x.get('body')} for x in xs if not isinstance(d,list) or any(s in (x.get('body') or '').lower() for s in ['alexar76','modelmarket','aimarket'])]
 except Exception as e:rec.update(status=getattr(e,'code',None),error=str(e))
 records.append(rec)
 print(json.dumps(rec,ensure_ascii=False),flush=True)
Path('artifacts/ecosystem-chains-2026-10-28/components/issue-candidates.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
