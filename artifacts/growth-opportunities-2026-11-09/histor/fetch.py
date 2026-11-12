import pathlib,urllib.request,urllib.error,json,datetime,hashlib,time,concurrent.futures
r=pathlib.Path(__file__).parent;urls={'landing':'https://histor.modelmarket.dev/','datasets':'https://histor.modelmarket.dev/datasets/','package-check':'https://histor.modelmarket.dev/api/v1/check?package=npm%3Amongodb-mcp-server','cache-churn':'https://histor.modelmarket.dev/datasets/cache-churn-2026-11-01/'}
def get(k,u):
 row={'key':k,'url':u,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};t=time.monotonic()
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'aicom-read-only-growth-audit/1.0'}),timeout=30)as x:b=x.read();row.update(status=x.status,final_url=x.url,content_type=x.headers.get('Content-Type'))
 except urllib.error.HTTPError as e:b=e.read();row.update(status=e.code,error=str(e))
 except Exception as e:row['error']=str(e);return row
 p=r/'raw'/(k+'.raw');p.write_bytes(b);row.update(file=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),latency_seconds=round(time.monotonic()-t,3));return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as ex:out=list(ex.map(lambda kv:get(*kv),urls.items()))
(r/'http-index.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
