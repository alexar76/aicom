from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,time
from datetime import datetime,timezone
qs=['"alexar76" -user:alexar76','"@aimarket/warden" -user:alexar76']
records=[]
for q in qs:
 url='https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':q,'per_page':100,'sort':'updated'})
 rec={'query':q,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
   body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),total_count=d.get('total_count'),incomplete_results=d.get('incomplete_results'),items=[{'html_url':x['html_url'],'title':x['title'],'created_at':x['created_at'],'updated_at':x['updated_at'],'user':x['user']['login'],'comments':x['comments'],'state':x['state'],'body_excerpt':(x.get('body') or '')[:700]} for x in d.get('items',[])])
 except Exception as e:rec.update(status=getattr(e,'code',None),error=str(e))
 records.append(rec);print(json.dumps(rec,ensure_ascii=False),flush=True);time.sleep(1)
Path('artifacts/ecosystem-chains-2026-10-28/components/github-issue-search-followup.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
