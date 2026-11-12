"""Public package metadata and reverse graph capture, no auth or execution."""
import concurrent.futures,datetime,hashlib,json,urllib.error,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def capture(item):
 ident,url=item;row={'id':ident,'url':url,'method':'GET','retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'alexar76-public-component-research/2026-11-10','Accept':'application/json,text/plain;q=0.9,text/html;q=0.8'})
  try:response=urllib.request.urlopen(req,timeout=35)
  except urllib.error.HTTPError as exc:response=exc
  with response:body=response.read(6_000_001);row.update(status=response.code,final_url=response.url,content_type=response.headers.get('content-type'))
  path=ROOT/'bodies'/f'{ident}.body';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
  row.update(bytes=len(body),complete=len(body)<=6_000_000,sha256=hashlib.sha256(body).hexdigest(),body_path=str(path.relative_to(ROOT)))
 except Exception as exc:row['error']=f'{type(exc).__name__}: {exc}'
 return row
def run(sources,out):
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(capture,sources.items()))
 (ROOT/out).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 return rows

if __name__=='__main__':
 sources={n+'-pypi':'https://pypi.org/pypi/'+n+'/json' for n in ['aimarket-hub','aimarket-agent','aimarket-bridges','ai-service-mesh','aimarket-treasury','aimarket-mcp-packager','aimarket-tee']}
 sources.update({'sdk-npm':'https://registry.npmjs.org/%40aimarket%2Fagent','widget-npm':'https://registry.npmjs.org/%40aimarket%2Fwidget','sdk-dart':'https://pub.dev/api/packages/aimarket_agent','sdk-rust-reverse':'https://crates.io/api/v1/crates/aimarket-agent/reverse_dependencies?page=1&per_page=100'})
 rows=run(sources,'package-metadata-index.json');versions=[]
 for r in rows:
  summary={'id':r['id'],'status':r.get('status'),'bytes':r.get('bytes'),'complete':r.get('complete'),'error':r.get('error')}
  if r.get('status')==200:
   data=json.loads((ROOT/r['body_path']).read_text())
   if r['id'].endswith('-pypi'):summary.update(name=data['info']['name'],published_version=data['info']['version']);versions.append({'id':r['id'],'system':'pypi','name':data['info']['name'],'version':data['info']['version']})
   elif r['id'].endswith('-npm'):summary.update(name=data['name'],published_version=data['dist-tags']['latest']);versions.append({'id':r['id'],'system':'npm','name':data['name'],'version':data['dist-tags']['latest']})
   elif r['id']=='sdk-dart':summary.update(name=data['name'],published_version=data['latest']['version'])
   else:summary['data']=data
  print(json.dumps(summary,ensure_ascii=False))
 (ROOT/'published-version-scopes.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2)+'\n')
