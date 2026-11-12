"""Capture explicit public GET evidence. No authentication, POST or tool calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent
LIMIT=4_000_000

def fetch(item):
    key,url=item
    r={'key':key,'url':url,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-readonly-integration-research/2026-11-10','Accept':'text/html,application/json,text/plain;q=0.9,*/*;q=0.1'})
    try: response=urllib.request.urlopen(req,timeout=20)
    except urllib.error.HTTPError as e: response=e
    except Exception as e:
        r['error']=f'{type(e).__name__}: {e}';return r
    with response:
        body=response.read(LIMIT+1)
        r.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'))
    r['truncated']=len(body)>LIMIT;body=body[:LIMIT]
    file=ROOT/(key+'.raw');file.write_bytes(body)
    r.update(file=file.name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
    return r

if __name__=='__main__':
    plan=ROOT/sys.argv[1]
    items=json.loads(plan.read_text())
    with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,items.items()))
    out=ROOT/(plan.stem+'-index.json');out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for r in rows: print(r['key'],r.get('status'),r.get('bytes'),r.get('error',''))
