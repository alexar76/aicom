"""Public GET-only package dissemination evidence. No installs or invokes."""
import concurrent.futures,datetime,hashlib,json,pathlib,urllib.request,urllib.error,urllib.parse
ROOT=pathlib.Path(__file__).parent
NPM=['@aimarket/warden','@aimarket/agent','@alexar76/argus3','@alexar76/awr-verify','@aimarket/widget','create-aimarket-agent']
PYPI=['aimarket-hub','aimarket-mcp','aimarket-histor','aimarket-agent','aimarket-gaia-gateway','aimarket-atlas','attested-memory','awr-verify','awr-emitter']
TASKS={}
for p in NPM:
 key=p.replace('@','').replace('/','-'); q=urllib.parse.quote(p,safe='')
 TASKS['npm-'+key]='https://registry.npmjs.org/'+q+'/latest'
 TASKS['downloads-'+key]='https://api.npmjs.org/downloads/range/2026-10-19:2026-11-08/'+q
for p in PYPI:
 TASKS['pypi-'+p]='https://pypi.org/pypi/'+p+'/json'
 TASKS['pypistats-'+p]='https://pypistats.org/api/packages/'+p+'/recent'
TASKS.update({
 'smallprint-warden':'https://smallprint.dev/a/npm/%40aimarket/warden',
 'protocolprobe-security':'https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security',
 'protocolprobe-memory':'https://protocolprobe.com/mcp/servers/io.github.alexar76/attested-memory',
 'glama-aimarket':'https://glama.ai/mcp/servers/alexar76/aimarket-mcp',
 'shortformkit':'https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/data/servers.json',
})
def fetch(kv):
 k,u=kv; m={'name':k,'url':u,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09','Accept':'application/json,text/html;q=0.9,*/*;q=0.8'}),timeout=25) as r:
   b=r.read(8_000_000); m.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
   (ROOT/(k+'.raw')).write_bytes(b)
 except urllib.error.HTTPError as e:
  b=e.read(1_000_000); (ROOT/(k+'.raw')).write_bytes(b); m.update(status=e.code,error=str(e),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 except Exception as e: m['error']=repr(e)
 return m
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(fetch,TASKS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 print(json.dumps([{k:r[k] for k in ('name','status','error') if k in r} for r in rows],indent=2))
