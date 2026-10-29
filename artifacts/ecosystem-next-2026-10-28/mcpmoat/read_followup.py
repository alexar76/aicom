import concurrent.futures,datetime,hashlib,json,re,urllib.request,urllib.error
from pathlib import Path
from read_public import get
ROOT=Path(__file__).resolve().parent
COMMIT='fc776bc2eb10376994b6d021a18f6230487bc033'
PATHS=['README.md','docs/PRD.md','docs/ARCHITECTURE.md','docs/README.md','docs/limits.md','docs/pins.md','docs/scan-output.md','go.mod','internal/report/json.go','internal/report/diff.go','internal/pins/diff.go','internal/rules/set.go','internal/rules/finding.go']
def textget(path):
    url=f'https://raw.githubusercontent.com/Ducarv/mcpmoat/{COMMIT}/{path}'
    row={'path':path,'url':url,'method':'GET','commit_sha':COMMIT,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public source research)'}),timeout=25) as response:
            raw=response.read();row.update(status=response.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        body=raw.decode();lines=body.splitlines()
        needles=r'warden|alexar76|ruleset|rule_set|rule.set|digest|severity|blocking|advisory|description|added|removed|version|hold.?out|held.?out'
        selected=[i for i,line in enumerate(lines) if re.search(needles,line,re.I)]
        chosen=set()
        for i in selected[:24]:chosen.update(range(max(0,i-1),min(len(lines),i+3)))
        row.update(line_count=len(lines),direct_refs=[{'line':i+1,'text':line} for i,line in enumerate(lines) if re.search(r'warden|alexar76',line,re.I)],selected_lines=[{'line':i+1,'text':lines[i]} for i in sorted(chosen)])
    except urllib.error.HTTPError as e:row.update(status=e.code,error=str(e))
    except Exception as e:row.update(status=None,error=str(e))
    return row
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(textget,PATHS))
    (ROOT/'pinned-files.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for r in rows:print(json.dumps({'path':r['path'],'status':r['status'],'refs':r.get('direct_refs'), 'lines':r.get('line_count')},ensure_ascii=False))
    out=[]
    for page in [2,3]:
        row,data=get(f'https://api.github.com/repos/Ducarv/mcpmoat/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}')
        if data is not None:row['selected']=[{k:item.get(k) for k in ['number','title','body','html_url','created_at','updated_at','closed_at','state','comments','pull_request']}|{'author':item.get('user',{}).get('login')} for item in data]
        out.append(row)
    (ROOT/'older-issues.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    for row in out:
        print(json.dumps({'url':row['url'],'status':row['status'],'count':len(row.get('selected',[])),'rate_remaining':row.get('rate_remaining'),'direct_warden_refs':[{'number':x['number'],'title':x['title'],'body':x['body'],'created_at':x['created_at']} for x in row.get('selected',[]) if re.search('warden|alexar76',x.get('body') or '',re.I)]},ensure_ascii=False))
