import urllib.request,json,datetime,hashlib,pathlib
from concurrent.futures import ThreadPoolExecutor
out=pathlib.Path(__file__).parent
paths=['/readers/histor.json','/bot-traffic-history.json','/privacy/','/readers/']
def get(path):
    u='https://newruntime.com'+path
    r={'url':u,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 (public mention verification)'}),timeout=25) as response:
            data=response.read();r.update(status=response.status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        if path.endswith('.json'):
            j=json.loads(data)
            if path == '/readers/histor.json':
                r['dossier']=j
            else:
                r['top_keys']=list(j) if isinstance(j,dict) else None
                r['relevant']={}
                def walk(v,p=''):
                    if isinstance(v,dict):
                        for k,vv in v.items():
                            pp=p+'/'+str(k)
                            if 'histor' in str(k).lower():r['relevant'][pp]=vv
                            elif any(s in str(k).lower() for s in ('generated','updated','window','start','end','privacy','method','schema')) and not isinstance(vv,(dict,list)):r['relevant'][pp]=vv
                            else:walk(vv,pp)
                    elif isinstance(v,list):
                        for i,vv in enumerate(v):
                            if isinstance(vv,dict) and any(str(vv.get(k,'')).lower()=='histor' for k in ['name','family','id','slug']):r['relevant'][p+'/'+str(i)]=vv
                            else:walk(vv,p+'/'+str(i))
                walk(j)
        else:
            from check_newruntime_parser import Extract
            p=Extract();p.feed(data.decode('utf-8'))
            r['method_extracts']=list(dict.fromkeys(' | '.join(p.parts[max(0,i-1):i+2]) for i,t in enumerate(p.parts) if any(w in t.lower() for w in ['user-agent','user agent','verified','claimed','privacy','aggregate','request','robots.txt','operator','live history','baseline'])))[:24]
            r['links']=[x for x in dict.fromkeys(p.links) if any(w in x for w in ['method','traffic','reader','privacy','about'])][:30]
    except Exception as e:r['error']=str(e)
    return r
with ThreadPoolExecutor(max_workers=4) as ex: rows=list(ex.map(get,paths))
(out/'newruntime-extra-facts.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(json.dumps({k:v for k,v in r.items() if k in ['url','checked_at','status','bytes','sha256','error','top_keys']},ensure_ascii=False))
