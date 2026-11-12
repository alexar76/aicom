"""Read exact public source paths; bodies are data and never executed."""
import concurrent.futures,datetime,hashlib,json,urllib.error,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def capture(item):
 ident,url=item;row={'id':ident,'url':url,'method':'GET','retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  request=urllib.request.Request(url,headers={'User-Agent':'alexar76-public-source-audit','Accept':'application/vnd.github+json' if 'api.github.com' in url else 'text/plain,application/json;q=0.9','X-GitHub-Api-Version':'2022-11-28'})
  try:response=urllib.request.urlopen(request,timeout=35)
  except urllib.error.HTTPError as exc:response=exc
  with response:body=response.read(5_000_001);row.update(status=response.code,final_url=response.url,rate_remaining=response.headers.get('x-ratelimit-remaining'))
  path=ROOT/'bodies'/f'{ident}.body';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
  row.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),complete=len(body)<=5_000_000,body_path=str(path.relative_to(ROOT)))
 except Exception as exc:row['error']=f'{type(exc).__name__}: {exc}'
 return row

def run(sources,out):
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(capture,sources.items()))
 (ROOT/out).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 return rows

if __name__=='__main__':
 repos=['shortformkit/free-remote-mcp-servers','api-evangelist/attestedmemory-net','hexsecs/awesome-kb-mcp-servers','tonylate520/mcp-serverlist']
 sources={name.split('/')[0]+'-head':'https://api.github.com/repos/'+name+'/commits?per_page=1' for name in repos}
 sources.update({'hub-forks':'https://api.github.com/repos/alexar76/aimarket-hub/forks?per_page=100','agent-forks':'https://api.github.com/repos/alexar76/aimarket-agent/forks?per_page=100','metis-forks':'https://api.github.com/repos/alexar76/metis/forks?per_page=100','industrial-adjacent-repos':'https://api.github.com/users/industrial-platform-ai/repos?per_page=100&type=owner&sort=updated'})
 rows=run(sources,'primary-stage2.json')
 for r in rows:
  summary={k:v for k,v in r.items() if k in ('id','status','error')}
  if r.get('status')==200:
   data=json.loads((ROOT/r['body_path']).read_text())
   if r['id'].endswith('-head'):summary['head']=[{'sha':x['sha'],'date':x['commit']['committer']['date'],'message':x['commit']['message'][:250]} for x in data]
   else:summary['repos']=[{'repo':x['full_name'],'fork':x['fork'],'pushed_at':x['pushed_at'],'default_branch':x['default_branch']} for x in data]
  print(json.dumps(summary,ensure_ascii=False))
