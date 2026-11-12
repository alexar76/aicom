"""Read exact public follow-up URLs; no code execution or login."""
import concurrent.futures,datetime,hashlib,json,pathlib,urllib.request,urllib.error
R=pathlib.Path(__file__).parent;raw=R/'raw'
tasks={'aeee-script':'https://aeee.us/daily/static/app.js?v=20260428-daily-v6','i3omb-compare':'https://git.i3omb.com/gronod/gitea-mcp/compare/v0.1.9...main'}
def get(kv):
 k,u=kv;m={'name':k,'url':u,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09'}),timeout=22)
 except urllib.error.HTTPError as e:r=e
 except Exception as e:m['error']=repr(e);return m
 with r:
  b=r.read(8_000_000);(raw/(k+'.raw')).write_bytes(b);m.update(status=r.code,headers=dict(r.headers),final_url=r.url,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 return m
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(get,tasks.items()))
(R/'followup-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(rows,indent=2))
