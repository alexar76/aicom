"""Read-only snapshot of active relevant Vulnetix OSV records at an immutable commit."""
import concurrent.futures, datetime, hashlib, json, time, urllib.request
from pathlib import Path
OUT=Path(__file__).resolve().parent
CACHE=Path('/private/tmp/aicom-security-review-20261030/vulnetix-osv');CACHE.mkdir(exist_ok=True)
sha=json.loads((OUT/'vulnetix-head.json').read_text())['sha']
rows=json.loads((Path('/private/tmp/aicom-security-review-20261030/vulnetix-manifest.json')).read_text())['records']
families={'PYPI','NPM','GO','CARGO','VULN-PYPI','VULN-NPM','VULN-GO','VULN-CARGO'}
selected=[r for r in rows if r['family'] in families and r['state']=='published']
def get(r):
 path=r['paths']['osv'];url=f'https://raw.githubusercontent.com/Vulnetix/advisory-database/{sha}/{path}'
 dest=CACHE/(r['id']+'.json')
 for attempt in range(3):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'aicom-security-review'}),timeout=20) as resp:data=resp.read()
   d=json.loads(data);assert d['id']==r['id'];dest.write_bytes(data)
   return {'id':r['id'],'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'classification':r['classification']}
  except Exception as e:
   if attempt==2:return {'id':r['id'],'url':url,'error':str(e)}
   time.sleep(1)
print('records',len(selected),flush=True)
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
 for row in pool.map(get,selected):
  results.append(row)
  if len(results)%100==0:print('downloaded',len(results),'errors',sum('error' in r for r in results),flush=True)
(OUT/'vulnetix-osv-provenance.json').write_text(json.dumps({'commit':sha,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':results},indent=2)+'\n')
print('done',len(results),sum('error' in r for r in results),flush=True)
