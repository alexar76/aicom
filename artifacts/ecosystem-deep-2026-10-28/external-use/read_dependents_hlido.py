"""Public GET metadata for reverse dependency counts and a selected external review."""
from pathlib import Path
import json, urllib.request, urllib.error, urllib.parse, datetime, hashlib, base64
ROOT=Path(__file__).parent
index=[]
def get(url):
    rec={'method':'GET','url':url,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        accept='application/vnd.github+json' if 'api.github.com/' in url else 'application/json'
        req=urllib.request.Request(url,headers={'User-Agent':'AICOM-public-external-use-review/1.0','Accept':accept})
        with urllib.request.urlopen(req,timeout=25) as r:
            body=r.read();rec.update(status=r.status,bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
        try: obj=json.loads(body)
        except json.JSONDecodeError: obj=body.decode(errors='replace')
    except urllib.error.HTTPError as e:
        body=e.read();rec.update(status=e.code,bytes=len(body),sha256=hashlib.sha256(body).hexdigest());obj=None
    except Exception as e: rec.update(error=str(e));obj=None
    index.append(rec);return obj
out=[]
for system,name,version in [('npm','@aimarket/warden','0.8.2'),('npm','@aimarket/warden','0.15.0'),('pypi','aimarket-protocol','0.1.0'),('pypi','aimarket-histor','0.3.0')]:
    url='https://api.deps.dev/v3alpha/systems/'+system+'/packages/'+urllib.parse.quote(name,safe='')+'/versions/'+version+':dependents'
    out.append({'system':system,'name':name,'version':version,'result':get(url),'request':index[-1]})
repo='https://api.github.com/repos/ankitkapur1992-hlido/hlido-public/contents/'
review=get(repo+'review-registry-public.json')
selected=[]
if isinstance(review,dict) and review.get('content'):
    raw=base64.b64decode(review['content'])
    data=json.loads(raw)
    def walk(obj,path=''):
        if isinstance(obj,dict):
            if any('alexar76' in str(v) or ('AICOM' in str(v) and not isinstance(v,(dict,list))) for v in obj.values() if not isinstance(v,(dict,list))):
                selected.append({'json_path':path,'value':obj})
            else:
                for k,v in obj.items(): walk(v,path+'/'+k)
        elif isinstance(obj,list):
            for i,v in enumerate(obj): walk(v,path+'/'+str(i))
    walk(data)
    selected.append({'blob_sha':review.get('sha'),'html_url':review.get('html_url')})
paths={}
for p in ['scorecards','v1','api']:
    d=get(repo+p)
    if isinstance(d,list): paths[p]=[{'name':x.get('name'),'type':x.get('type'),'html_url':x.get('html_url'),'sha':x.get('sha')} for x in d if 'alexar76' in x.get('name','') or p!='scorecards']
(ROOT/'dependents-check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(ROOT/'hlido-selected.json').write_text(json.dumps({'registry':selected,'paths':paths},ensure_ascii=False,indent=2)+'\n')
(ROOT/'dependents-hlido-http-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'dependents':out,'hlido':selected,'paths':paths,'http_statuses':index},ensure_ascii=False,indent=2))
