"""Unauthenticated public search reads, no GitHub writes."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,time,urllib.request,urllib.parse,urllib.error

queries=[
 '"alexar76/warden" in:comments -user:alexar76 -author:alexar76',
 '"alexar76/argus" -user:alexar76 -author:alexar76',
 '"10.5281/zenodo.23512760" -user:alexar76 -author:alexar76',
 '"manifest_canonical" -user:alexar76 -author:alexar76',
 '"AWR/2" -user:alexar76 -author:alexar76',
 '"aimarket-histor" -user:alexar76 -author:alexar76',
]
rows=[]
for query in queries:
 url='https://api.github.com/search/issues?'+urllib.parse.urlencode({'q':query,'per_page':100})
 r={'query':query,'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Public source research','Accept':'application/vnd.github+json'}),timeout=25) as response:
   raw=response.read();r.update(status=response.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),rate_remaining=response.headers.get('X-RateLimit-Remaining'),rate_resource=response.headers.get('X-RateLimit-Resource'))
  d=json.loads(raw);r.update(total_count=d.get('total_count'),incomplete_results=d.get('incomplete_results'),items=[])
  for item in d.get('items',[]):
   r['items'].append({'url':item['html_url'],'title':item['title'],'author':item['user']['login'],'created_at':item['created_at'],'updated_at':item['updated_at'],'state':item['state'],'comments':item.get('comments'),'body':(item.get('body') or '')[:6000]})
 except urllib.error.HTTPError as e:r.update(status=e.code,error=str(e))
 except Exception as e:r.update(status=None,error=str(e))
 rows.append(r)
 if r['status'] in (403,429):break
 time.sleep(2)
Path(__file__).with_name('github-issue-refs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{'query':r['query'],'status':r['status'],'total_count':r.get('total_count'),'remaining':r.get('rate_remaining'),'items':[{'title':i['title'],'url':i['url'],'author':i['author']} for i in r.get('items',[])]} for r in rows],ensure_ascii=False))
