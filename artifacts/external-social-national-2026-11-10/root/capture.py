"""Public GET-only evidence, preserving quota headers; stops a batch on API quota."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parent
LIMIT=4_000_000

def get(key,url):
    row={'key':key,'url':url,'method':'GET','observed_at_utc':datetime.now(timezone.utc).isoformat()}
    req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-gap-research/2026-11-10','Accept':'application/json,text/html,text/plain;q=0.9,*/*;q=0.1'})
    try:r=urllib.request.urlopen(req,timeout=25)
    except urllib.error.HTTPError as e:r=e
    except Exception as e:
        row['error']=f'{type(e).__name__}: {e}';return row
    with r:
        b=r.read(LIMIT+1)
        row.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),headers={k:r.headers.get(k) for k in ['Date','X-RateLimit-Limit','X-RateLimit-Remaining','X-RateLimit-Reset','X-RateLimit-Resource','Retry-After'] if r.headers.get(k) is not None})
    row['truncated']=len(b)>LIMIT;b=b[:LIMIT];file=ROOT/(key+'.raw');file.write_bytes(b)
    row.update(file=file.name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
    return row

if __name__=='__main__':
    plan=ROOT/sys.argv[1];rows=[]
    for key,url in json.loads(plan.read_text()).items():
        r=get(key,url);rows.append(r)
        print(json.dumps({k:v for k,v in r.items() if k not in ['sha256']},ensure_ascii=False),flush=True)
        if r.get('status') in [403,429] and url.startswith('https://api.github.com/'):break
    (ROOT/(plan.stem+'-index.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
