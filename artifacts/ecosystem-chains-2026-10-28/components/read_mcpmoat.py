from pathlib import Path
import urllib.request,json,hashlib,base64
from datetime import datetime,timezone
urls=['https://api.github.com/repos/Ducarv/mcpmoat/contents/docs/competitors.md','https://api.github.com/repos/Ducarv/mcpmoat/issues/32','https://api.github.com/repos/Ducarv/mcpmoat/pulls/111','https://api.github.com/repos/Ducarv/mcpmoat/issues/111/comments?per_page=100','https://api.github.com/repos/Ducarv/mcpmoat/pulls/111/files?per_page=100']
records=[]
for url in urls:
 rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
   body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
   if '/contents/' in url:
    txt=base64.b64decode(d['content']).decode();rec['blob_sha']=d['sha'];rec['html_url']=d['html_url'];rec['text']=txt
   elif isinstance(d,list):rec['items']=[{'html_url':x.get('html_url'),'user':x.get('user',{}).get('login'),'created_at':x.get('created_at'),'updated_at':x.get('updated_at'),'body':x.get('body'),'filename':x.get('filename'),'status':x.get('status'),'patch':x.get('patch')} for x in d]
   else:rec['selected']={k:d.get(k) for k in ['html_url','title','state','merged','merged_at','created_at','updated_at','closed_at','body','comments']};rec['selected']['user']=d.get('user',{}).get('login')
 except Exception as e:rec.update(status=getattr(e,'code',None),error=str(e))
 records.append(rec)
 print(url,rec.get('status'),len(rec.get('text','')),flush=True)
Path('artifacts/ecosystem-chains-2026-10-28/components/mcpmoat-evidence.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
