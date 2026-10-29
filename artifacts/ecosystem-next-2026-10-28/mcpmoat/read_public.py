import concurrent.futures,datetime,hashlib,json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def get(url):
    row={'url':url,'method':'GET','retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public source research)','Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read();row.update(status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),rate_remaining=response.headers.get('X-RateLimit-Remaining'))
        return row,json.loads(raw)
    except urllib.error.HTTPError as e:
        row.update(status=e.code,error=str(e));return row,None
    except Exception as e:
        row.update(status=None,error=str(e));return row,None

if __name__=='__main__':
    urls=['https://api.github.com/repos/Ducarv/mcpmoat/branches/dev','https://api.github.com/repos/Ducarv/mcpmoat/git/trees/fc776bc2eb10376994b6d021a18f6230487bc033?recursive=1','https://api.github.com/repos/Ducarv/mcpmoat/issues?state=all&sort=updated&direction=desc&per_page=100']
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for (row,data),url in zip(pool.map(get,urls),urls):
            if data is not None:
                if '/branches/' in url:row['selected']={'sha':data.get('commit',{}).get('sha'),'name':data.get('name')}
                elif '/git/trees/' in url:row['selected']={'truncated':data.get('truncated'),'tree':[{'path':x['path'],'type':x['type'],'sha':x['sha']} for x in data.get('tree',[]) if x['type']=='blob']}
                else:row['selected']=[{k:item.get(k) for k in ['number','title','body','html_url','created_at','updated_at','closed_at','state','comments','pull_request']}|{'author':item.get('user',{}).get('login')} for item in data]
            rows.append(row)
    (ROOT/'discovery.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for row in rows:
        out={k:row[k] for k in ['url','status','rate_remaining'] if k in row}
        if '/trees/' in row['url']:out['paths']=[x['path'] for x in row.get('selected',{}).get('tree',[])]
        elif '/issues?' in row['url']:out['issues']=[{k:x[k] for k in ['number','title','comments','updated_at']} for x in row.get('selected',[])]
        else:out['selected']=row.get('selected')
        print(json.dumps(out,ensure_ascii=False))
