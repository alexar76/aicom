"""Bounded public GETs of native East Asian sources; no login, publishing or tool calls."""
import concurrent.futures,datetime,hashlib,json,pathlib,urllib.parse,urllib.request,urllib.error
R=pathlib.Path(__file__).parent;raw=R/'raw';raw.mkdir(exist_ok=True)
Q=urllib.parse.quote
tasks={
 'qiita-author':'https://qiita.com/api/v2/users/qwezzy721/items?per_page=100&page=1',
 'qiita-cost':'https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7',
 'qiita-cost-comments':'https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7/comments',
 'qiita-histor':'https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6',
 'qiita-histor-comments':'https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6/comments',
 'qiita-domain-search':'https://qiita.com/api/v2/items?query='+Q('modelmarket.dev')+'&per_page=100&page=1',
 'zenn-domain':'https://zenn.dev/api/search?q=modelmarket.dev&source=articles&order=latest',
 'zenn-alexar':'https://zenn.dev/api/search?q=alexar76&source=articles&order=latest',
 'zenn-attested-scraps':'https://zenn.dev/api/search?q=attestedmemory&source=scraps&order=latest',
 'hatena-cost':'https://b.hatena.ne.jp/entry/jsonlite/?url='+Q('https://qiita.com/qwezzy721/items/4dfe9dc2fbe9d69b1fb7',safe=''),
 'hatena-histor':'https://b.hatena.ne.jp/entry/jsonlite/?url='+Q('https://qiita.com/qwezzy721/items/b71aaeaae84fcb360fe6',safe=''),
 'hatena-histor-site':'https://b.hatena.ne.jp/entry/jsonlite/?url='+Q('https://histor.modelmarket.dev/',safe=''),
 'naver-domain':'https://search.naver.com/search.naver?query='+Q('"modelmarket.dev"'),
 'naver-alexar':'https://search.naver.com/search.naver?query='+Q('"alexar76"'),
 'hubwiz':'https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/',
 'juejin':'https://juejin.cn/post/7696713457148952630',
 'selectdataset':'https://www.selectdataset.com/dataset/d595b7ffd78438a48b6efa42e0861151/histor-mcp-tool-definitions',
 'papervault':'https://papers.ananclaw.com/search?q=alexar76',
 'gitee-public-search':'https://gitee.com/api/v5/search/repositories?q=alexar76&per_page=20&page=1',
}
def get(kv):
 k,u=kv;m={'name':k,'url':u,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'alexar76-external-readonly-audit/2026-11-09','Accept':'application/json,text/html;q=0.9,*/*;q=0.8'}),timeout=22)
 except urllib.error.HTTPError as e:r=e
 except Exception as e:m['error']=repr(e);return m
 with r:
  b=r.read(6_000_000);(raw/(k+'.raw')).write_bytes(b);m.update(status=r.code,final_url=r.url,headers=dict(r.headers),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
 return m
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(get,tasks.items()))
(R/'native-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps([{k:x[k] for k in ('name','status','error','bytes') if k in x} for x in rows],indent=2))
