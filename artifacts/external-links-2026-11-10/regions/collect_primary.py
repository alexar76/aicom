"""Read candidate public sources without executing their code or publishing."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent
TARGETS={
 "wpnews-comparison":"https://wpnews.pro/news/we-ran-three-mcp-security-scanners-on-a-tool-poisoning-benchmark-and-986-real",
 "dev-worker-mirror":"https://dev.clauneck.workers.dev/alexar76",
 "model-context-problems":"https://modelcontextproblems.com/",
 "mcp-index-flagged":"https://themcpindex.com/flagged",
}
def fetch(item):
 name,url=item
 row={"name":name,"url":url,"observed_at_utc":datetime.now(timezone.utc).isoformat()}
 try:
  response=urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"AICOM-public-readonly-audit/2026-11-10"}),timeout=25)
 except urllib.error.HTTPError as e:response=e
 except Exception as e:
  row['error']=f'{type(e).__name__}: {e}'
  return row
 with response:
  body=response.read(3_000_001)
  row.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'))
 row['truncated']=len(body)>3_000_000
 path=ROOT/(name+'.raw');path.write_bytes(body)
 row.update(file=path.name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
 return row
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as p:rows=list(p.map(fetch,TARGETS.items()))
 (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(rows,ensure_ascii=False,indent=2))
