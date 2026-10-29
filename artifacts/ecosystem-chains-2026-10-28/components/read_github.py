from pathlib import Path
import urllib.request, urllib.parse,json,hashlib,time
from datetime import datetime,timezone
qs=["\"aimarket-logos\" in:readme -user:alexar76","\"aimarket-helios\" in:readme -user:alexar76","\"aimarket-skopos\" in:readme -user:alexar76","\"aimarket-metis\" in:readme -user:alexar76","\"oraclecore\" \"alexar76\" in:readme -user:alexar76","\"aimarket-oracle-gateway\" in:readme -user:alexar76","\"aimarket-hestia\" in:readme -user:alexar76","\"aimarket-emporion\" in:readme -user:alexar76"]
b=Path('artifacts/ecosystem-chains-2026-10-28/components');b.mkdir(parents=True,exist_ok=True)
records=[]
for q in qs:
 url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':100})
 rec={'query':q,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
   body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),total_count=d.get('total_count'),incomplete_results=d.get('incomplete_results'),items=[{'full_name':x['full_name'],'html_url':x['html_url'],'description':x['description'],'created_at':x['created_at'],'pushed_at':x['pushed_at'],'fork':x['fork']} for x in d.get('items',[])])
 except Exception as e:rec.update(status=getattr(e,'code',None),error=str(e))
 records.append(rec)
 print(q,rec.get('status'),rec.get('total_count'),[x['full_name'] for x in rec.get('items',[])],flush=True)
 time.sleep(1)
(b/'github-search.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
