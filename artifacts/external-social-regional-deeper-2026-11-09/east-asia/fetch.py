"""Second East Asian pass: new public native queries and candidate source GETs only."""
import concurrent.futures,datetime,hashlib,json,pathlib,urllib.parse,urllib.request,urllib.error
R=pathlib.Path(__file__).parent;raw=R/'raw';raw.mkdir(exist_ok=True)
tasks={
 'fjojo-daily':'https://fjojo.pro/daily',
 'nccsec-index':'https://nccsec.cn/',
 'aeee-daily':'https://aeee.us/daily/',
 'aiproducthub-1105':'https://aiproducthub.cn/newsflash/2026-11-05/',
}
for name,q in [('hf-slug','"histor-mcp-tool-definitions"'),('package','"@aimarket/warden"'),('histor-external','HISTOR MCP -user:qwezzy721'),('tokens-external','"34,374" MCP -user:qwezzy721')]:
 tasks['qiita-'+name]='https://qiita.com/api/v2/items?'+urllib.parse.urlencode({'query':q,'per_page':100,'page':1})
for name,q,source in [('hf-articles','histor-mcp-tool-definitions','articles'),('hf-scraps','histor-mcp-tool-definitions','scraps'),('package-articles','@aimarket/warden','articles'),('package-scraps','@aimarket/warden','scraps')]:
 tasks['zenn-'+name]='https://zenn.dev/api/search?'+urllib.parse.urlencode({'q':q,'source':source,'order':'latest'})
for name,q in [('hf-slug','histor-mcp-tool-definitions'),('package','@aimarket/warden')]:
 tasks['gitee-'+name]='https://gitee.com/api/v5/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':20,'page':1})
def get(kv):
 k,u=kv;m={'name':k,'url':u,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09','Accept':'application/json,text/html;q=0.9,*/*;q=0.8'}),timeout=22)
 except urllib.error.HTTPError as e:r=e
 except Exception as e:m['error']=repr(e);return m
 with r:
  b=r.read(8_000_000);(raw/(k+'.raw')).write_bytes(b);m.update(status=r.code,headers=dict(r.headers),final_url=r.url,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 return m
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(get,tasks.items()))
(R/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps([{k:x[k] for k in ('name','status','error','bytes') if k in x} for x in rows],indent=2))
