"""Selected read-only public metadata. Never install or execute downloaded code."""
from pathlib import Path
import json, urllib.request, urllib.error, urllib.parse, datetime, hashlib, base64
ROOT=Path(__file__).parent
index=[];out=[]
def get(url):
    rec={'method':'GET','url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-external-use-review/1.0','Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=25) as r:
            body=r.read();rec.update(status=r.status,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
        try: obj=json.loads(body)
        except json.JSONDecodeError: obj=body.decode(errors='replace')
    except urllib.error.HTTPError as e:
        body=e.read();rec.update(status=e.code,bytes=len(body),sha256=hashlib.sha256(body).hexdigest());obj=None
    except Exception as e: rec.update(error=str(e));obj=None
    index.append(rec);return obj
for system,name,version in [('npm','@aimarket/warden','0.22.2'),('npm','@aimarket/agent','0.3.0')]:
    url='https://api.deps.dev/v3alpha/systems/'+system+'/packages/'+urllib.parse.quote(name,safe='')+'/versions/'+version+':dependents'
    out.append({'kind':'documented-dependents','name':name,'version':version,'result':get(url),'request':index[-1]})
for name in ['aimarket-protocol','aimarket-agent','aimarket-histor']:
    d=get('https://pypi.org/pypi/'+name+'/json')
    if isinstance(d,dict):
        info=d.get('info',{});version=info.get('version')
        out.append({'kind':'pypi-project-metadata','name':name,'info':{k:info.get(k) for k in ['name','version','project_urls','requires_dist']},'request':index[-1]})
        if version:
            url='https://api.deps.dev/v3alpha/systems/pypi/packages/'+name+'/versions/'+version+':dependents'
            out.append({'kind':'documented-dependents','name':name,'version':version,'result':get(url),'request':index[-1]})
for url in ['https://deps.dev/_/s/npm/p/%40aimarket%2Fwarden/v/0.8.2/dependents','https://www.npmjs.com/browse/depended/@aimarket/warden','https://api.github.com/repos/ankitkapur1992-hlido/hlido-public/contents/scorecards/alexar76-aimarket-plugins.json','https://api.github.com/repos/sep163/aimarket-agents/contents/requirements.txt','https://api.github.com/repos/bracha55555-hue/aimarket/contents/requirements.txt']:
    d=get(url)
    if isinstance(d,dict) and d.get('content'):
        raw=base64.b64decode(d['content']).decode(errors='replace')
        try: result=json.loads(raw)
        except json.JSONDecodeError: result=raw
        out.append({'kind':'selected-public-file','url':url,'blob_sha':d.get('sha'),'result':result,'request':index[-1]})
    elif isinstance(d,dict): out.append({'kind':'public-web-ui-api','url':url,'result':d,'request':index[-1]})
    else: out.append({'kind':'public-page','url':url,'json_result':None,'request':index[-1]})
(ROOT/'final-metadata.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(ROOT/'final-http-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
