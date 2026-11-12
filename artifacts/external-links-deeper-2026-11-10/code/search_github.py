"""Unauthenticated public GitHub search GETs; never publishes or executes foreign code."""
import datetime,hashlib,json,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
QUERIES=[
('repositories','"alexar76" in:readme -user:alexar76'),
('repositories','"aimarket-hub" in:readme -user:alexar76'),
('repositories','"aimarket-agent" in:readme -user:alexar76'),
('repositories','"aimarket-mcp" in:readme -user:alexar76'),
('repositories','"attestedmemory.net" in:readme -user:alexar76'),
('repositories','"metis.modelmarket.dev" in:readme -user:alexar76'),
('repositories','"aimarket-oracle-gateway" in:readme -user:alexar76'),
('repositories','"@aimarket/agent" in:readme -user:alexar76'),
('commits','"aimarket-hub" -author:alexar76'),
('commits','"aimarket-agent" -author:alexar76')]

def get(kind,q,i):
 url='https://api.github.com/search/'+kind+'?'+urllib.parse.urlencode({'q':q,'per_page':30})
 row={'query_kind':kind,'query':q,'url':url,'method':'GET','retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 req=urllib.request.Request(url,headers={'User-Agent':'alexar76-public-source-audit','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
 try:
  try:r=urllib.request.urlopen(req,timeout=35)
  except urllib.error.HTTPError as e:r=e
  with r:body=r.read(5_000_001);row.update(status=r.code,final_url=r.url,rate_limit_remaining=r.headers.get('x-ratelimit-remaining'),rate_limit_resource=r.headers.get('x-ratelimit-resource'),retry_after=r.headers.get('retry-after'))
  file=ROOT/'bodies'/f'search-{i:02}.json';file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
  row.update(bytes=len(body),complete=len(body)<=5_000_000,sha256=hashlib.sha256(body).hexdigest(),body_path=str(file.relative_to(ROOT)))
  if row['status']==200:
   data=json.loads(body);row.update(total_count=data.get('total_count'),incomplete_results=data.get('incomplete_results'))
   if kind=='repositories':row['items']=[{k:v.get(k) for k in ('full_name','html_url','description','fork','default_branch','created_at','updated_at','pushed_at')} for v in data.get('items',[])]
   else:row['items']=[{'html_url':v['html_url'],'sha':v['sha'],'repository':v['repository']['full_name'],'message':v['commit']['message'],'date':v['commit']['author']['date'],'author':v.get('author',{}).get('login') if v.get('author') else None} for v in data.get('items',[])]
  else:row['error_body']=body.decode('utf-8','replace')[:1000]
 except Exception as e:row['error']=str(e)
 return row

if __name__=='__main__':
 rows=[]
 for i,(kind,q) in enumerate(QUERIES,1):
  r=get(kind,q,i);rows.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
  if r.get('status') in (403,429):break
  time.sleep(1)
 (ROOT/'github-searches.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
