"""Bounded unauthenticated GitHub discovery; public GET only, no secrets or source execution."""
from pathlib import Path
import json, urllib.request, urllib.parse, urllib.error, hashlib, datetime, time
ROOT=Path(__file__).parent
queries=[
 'alexar76 in:readme -user:alexar76',
 '"@aimarket/warden" in:readme -user:alexar76',
 '"histor.modelmarket.dev" in:readme -user:alexar76',
 '"aimarket-protocol" in:readme -user:alexar76',
 '"modelmarket.dev" in:readme -user:alexar76',
 '"histor-mcp-tool-definitions" in:readme -user:alexar76',
 '"aimarket-agent" in:readme -user:alexar76',
 '"@aimarket/agent" in:readme -user:alexar76',
 '"magic-ai-factory.com" in:readme -user:alexar76',
]
records=[];repositories={}
def read(url):
 r={'url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'GET'}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-external-use-review/1.0','Accept':'application/vnd.github+json'})
  with urllib.request.urlopen(req,timeout=30) as response:
   body=response.read();r.update(status=response.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),rate_remaining=response.headers.get('x-ratelimit-remaining'),rate_resource=response.headers.get('x-ratelimit-resource'))
  data=json.loads(body)
 except urllib.error.HTTPError as e:
  r.update(status=e.code,error=e.read().decode(errors='replace')[:300]);data=None
 except Exception as e:r['error']=str(e);data=None
 records.append(r);return data
search=[]
for q in queries:
 url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':100})
 d=read(url)
 if d is not None:
  row={'query':q,'total_count':d.get('total_count'),'incomplete_results':d.get('incomplete_results'),'repositories':[{'full_name':x['full_name'],'html_url':x['html_url'],'fork':x['fork'],'updated_at':x['updated_at'],'pushed_at':x['pushed_at'],'description':x.get('description')} for x in d.get('items',[])]}
  for x in row['repositories']:repositories[x['full_name']]=x
 else:row={'query':q,'error':records[-1]}
 search.append(row)
 time.sleep(1.1)
(ROOT/'github-repository-search.json').write_text(json.dumps(search,ensure_ascii=False,indent=2)+'\n')
details=[]
for name in ['alexar76/aicom','alexar76/metis','alexar76/warden','alexar76/histor']:
 d=read('https://api.github.com/repos/'+name+'/forks?per_page=100&sort=newest')
 if isinstance(d,list):
  row={'repository':name,'forks':[{'full_name':x['full_name'],'html_url':x['html_url'],'created_at':x['created_at'],'pushed_at':x['pushed_at'],'default_branch':x['default_branch']} for x in d]}
  for x in row['forks']:repositories.setdefault(x['full_name'],x)
 else:row={'repository':name,'error':records[-1]}
 details.append(row)
(ROOT/'github-forks.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
(ROOT/'http-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'queries':len(search),'repos_found':list(repositories),'search_summaries':[{k:r.get(k) for k in ['query','total_count','error']} for r in search],'forks':details,'http_statuses':{str(s):sum(r.get('status')==s for r in records) for s in {r.get('status') for r in records}}},ensure_ascii=False,indent=2))
