"""Read-only follow-up: resolve current version graphs and date package counts."""
import concurrent.futures,datetime,hashlib,json,pathlib,urllib.request,urllib.parse
import fetch
R=pathlib.Path(__file__).parent
tasks={
 'pypi-awr':'https://pypi.org/pypi/awr/json',
 'pypistats-awr':'https://pypistats.org/api/packages/awr/recent',
 'pypistats-api-docs':'https://pypistats.org/api/',
 'shortformkit-full':'https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/data/servers.json',
}
for name in ['aimarket-hub','aimarket-mcp','aimarket-histor','aimarket-agent','aimarket-atlas','aimarket-gaia-gateway','attested-memory','awr-emitter']:
 tasks['overall-'+name]='https://pypistats.org/api/packages/'+name+'/overall?mirrors=false'
for p in R.glob('npm-*.raw'):
 d=json.loads(p.read_text()); n=d['name']; v=d['version']; k=p.stem.removeprefix('npm-')
 tasks['deps-npm-'+k]='https://deps.dev/_/s/npm/p/'+urllib.parse.quote(n,safe='')+'/v/'+v+'/dependents'
for p in R.glob('pypi-*.raw'):
 try:
  d=json.loads(p.read_text()); n=d['info']['name']; v=d['info']['version']
 except Exception: continue
 tasks['deps-pypi-'+n]='https://deps.dev/_/s/pypi/p/'+urllib.parse.quote(n,safe='')+'/v/'+v+'/dependents'
def more(kv):
 if kv[0]!='shortformkit-full': return fetch.fetch(kv)
 k,u=kv; m={'name':k,'url':u,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09'}),timeout=30) as r:
  b=r.read(24_000_000); m.update(status=r.status,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),final_url=r.url,content_type=r.headers.get('Content-Type'));(R/(k+'.raw')).write_bytes(b)
 return m
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(more,tasks.items()))
(R/'followup-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps([{k:r[k] for k in ('name','status','error','bytes') if k in r} for r in rows],indent=2))
