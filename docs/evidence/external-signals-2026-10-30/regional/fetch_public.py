from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,datetime,concurrent.futures
root=Path('docs/evidence/external-signals-2026-10-30/regional')
root.mkdir(parents=True,exist_ok=True)
targets=[
('qiita-items','https://qiita.com/api/v2/items?query='+urllib.parse.quote('user:qwezzy721')+'&per_page=100'),
('qiita-tool-cost','https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7'),
('qiita-tool-cost-comments','https://qiita.com/api/v2/items/4dfe9dc2fbe9d69b1fb7/comments'),
('qiita-histor','https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6'),
('qiita-histor-comments','https://qiita.com/api/v2/items/b71aaeaae84fcb360fe6/comments'),
('ananclaw-search','https://papers.ananclaw.com/search?q=alexar76'),
('hubwiz','https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/'),
('author-today','https://author.today/work/650555'),
('mcp-catalog','https://mcp-catalog.ru/servers/alexar76/aimarket-mcp'),
('yandex-search','https://yandex.ru/search/?text='+urllib.parse.quote('"modelmarket.dev"')),
('baidu-search','https://www.baidu.com/s?wd='+urllib.parse.quote('"modelmarket.dev"')),
('naver-search','https://search.naver.com/search.naver?query='+urllib.parse.quote('"modelmarket.dev"')),
]
def run(pair):
 name,url=pair
 row=dict(name=name,url=url,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (external-signal-audit; read-only)'})
  with urllib.request.urlopen(req,timeout=25) as r:
   body=r.read();row.update(status=r.status,final_url=r.url,content_type=r.headers.get('content-type'),sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
  suffix='.json' if 'json' in row['content_type'] else '.html'
  (root/(name+suffix)).write_bytes(body)
  row['file']=name+suffix
 except Exception as e:row['error']=type(e).__name__+': '+str(e)
 return row
rows=list(concurrent.futures.ThreadPoolExecutor(max_workers=6).map(run,targets))
(root/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rows,ensure_ascii=False,indent=2))

