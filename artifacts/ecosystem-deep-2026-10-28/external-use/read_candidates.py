"""Selected public metadata and README reads. No source execution, account, or write APIs."""
from pathlib import Path
import json, urllib.request, urllib.error, hashlib, datetime, base64, re
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
for name in ['sep163/aimarket-agents','bracha55555-hue/aimarket','ankitkapur1992-hlido/hlido-public']:
    m=get('https://api.github.com/repos/'+name)
    if not isinstance(m,dict): continue
    r=get('https://api.github.com/repos/'+name+'/readme')
    row={'repository':name,'url':m.get('html_url'),'created_at':m.get('created_at'),'pushed_at':m.get('pushed_at'),'fork':m.get('fork'),'description':m.get('description'),'homepage':m.get('homepage'),'size':m.get('size'),'readme':None}
    if isinstance(r,dict) and r.get('content'):
        text=base64.b64decode(r['content']).decode(errors='replace')
        (ROOT/(name.replace('/','__')+'__README.txt')).write_text(text)
        lines=text.splitlines()
        matches=set()
        for i,s in enumerate(lines):
            if re.search(r'alexar76|modelmarket|aimarket|warden|histor|npm|dependencies|license|cooper112',s,re.I):
                matches.update(range(max(0,i-1),min(len(lines),i+2)))
        row['readme']={'url':r.get('html_url'),'blob_sha':r.get('sha'),'lines':len(lines),'matched_lines':[{'line':i+1,'text':lines[i]} for i in sorted(matches)][:100]}
    c=get('https://api.github.com/repos/'+name+'/contents/')
    if isinstance(c,list): row['root_entries']=[{'name':x.get('name'),'type':x.get('type'),'html_url':x.get('html_url')} for x in c]
    out.append(row)
packages=[]
for name in ['@aimarket/warden','@aimarket/agent','@aimarket-skill/refactoring-helper']:
    encoded=name.replace('@','%40').replace('/','%2F')
    d=get('https://registry.npmjs.org/'+encoded+'/latest')
    if isinstance(d,dict):
        packages.append({k:d.get(k) for k in ['name','version','description','repository','homepage','author','maintainers','dependencies','peerDependencies','optionalDependencies']})
(ROOT/'candidate-details.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
(ROOT/'package-metadata.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2)+'\n')
(ROOT/'candidate-http-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'repos':out,'packages':packages,'http_statuses':[{'url':i['url'],'status':i.get('status'),'error':i.get('error')} for i in index]},ensure_ascii=False,indent=2))
