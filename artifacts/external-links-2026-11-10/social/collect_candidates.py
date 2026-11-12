"""Bounded public reading of candidate backlinks; no external writes."""
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    'vouch-trust-index': 'https://vouch-protocol.com/agent-trust-index/',
    'teckdeck-cache-churn': 'https://teckdeck.io/posts/we-found-331-mcp-tool-list-changes-in-one-week-that-only-moved-a-date-each-one-costs-a-prompt-cache-write',
    'model-context-problems': 'https://modelcontextproblem.com/',
    'agentrank-python': 'https://agentrank-ai.com/category/python/',
}

def fetch(item):
    name, url = item
    row={'name':name,'url':url,'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    request=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-readonly-audit/2026-11-10'})
    try:
        response=urllib.request.urlopen(request,timeout=25)
    except urllib.error.HTTPError as exc:
        response=exc
    except Exception as exc:
        row['error']=f'{type(exc).__name__}: {exc}'
        return row
    with response:
        body=response.read(4_000_001)
        row.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'))
    row['truncated']=len(body)>4_000_000
    path=ROOT/(name+'.raw')
    path.write_bytes(body)
    row.update(file=path.name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
    return row

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(fetch,TARGETS.items()))
    (ROOT/'http-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
