import concurrent.futures,datetime,hashlib,json,urllib.request,urllib.error
from pathlib import Path
from read_followup import COMMIT
ROOT=Path(__file__).resolve().parent
TARGETS={'docs/exit-codes.md':[(1,130)],'internal/pins/render.go':[(1,160)],'cmd/mcpmoat/scan_findings.go':[(1,180)],'internal/report/findings.go':[(1,150)]}
def read(item):
    path,ranges=item;url=f'https://raw.githubusercontent.com/Ducarv/mcpmoat/{COMMIT}/{path}'
    row={'path':path,'url':url,'method':'GET','commit_sha':COMMIT,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public research)'}),timeout=25) as response:
            raw=response.read();row.update(status=response.status,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        lines=raw.decode().splitlines();row['line_count']=len(lines)
        row['selected_lines']=[{'line':i+1,'text':s} for i,s in enumerate(lines) if any(start<=i+1<=end for start,end in ranges)]
    except urllib.error.HTTPError as e:row.update(status=e.code,error=str(e))
    except Exception as e:row.update(status=None,error=str(e))
    return row
if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(read,TARGETS.items()))
    (ROOT/'implementation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    for row in rows:print(json.dumps({'path':row['path'],'status':row['status'],'selected':row.get('selected_lines')},ensure_ascii=False)[:18000])
