"""Read explicit public source URLs; no accounts, writes or service invocations."""
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

def get(item):
    key,url=item
    row={'key':key,'url':url,'observed_at_utc':datetime.now(timezone.utc).isoformat()}
    req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-component-research/2026-11-10','Accept':'application/json,text/html,text/plain;q=0.9,*/*;q=0.1'})
    try:r=urllib.request.urlopen(req,timeout=20)
    except urllib.error.HTTPError as e:r=e
    except Exception as e:
        row['error']=f'{type(e).__name__}: {e}';return row
    with r:
        b=r.read(LIMIT+1);row.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),remaining=r.headers.get('X-RateLimit-Remaining'),retry_after=r.headers.get('Retry-After'))
    row['truncated']=len(b)>LIMIT;b=b[:LIMIT]
    file=ROOT/(key+'.raw');file.write_bytes(b)
    row.update(file=file.name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    return row

if __name__=='__main__':
    plan=ROOT/sys.argv[1];items=json.loads(plan.read_text())
    # Search requests are kept sequential to respect a shared public quota.
    if any('/search/' in u for u in items.values()):
        rows=[]
        for item in items.items():
            row=get(item);rows.append(row)
            if row.get('status') in (403,429):break
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(get,items.items()))
    (ROOT/(plan.stem+'-index.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for r in rows:print(r['key'],r.get('status'),r.get('bytes'),r.get('error',''))
