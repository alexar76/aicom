from pathlib import Path
import urllib.request,json,hashlib,base64
from datetime import datetime,timezone
b=Path('artifacts/ecosystem-chains-2026-10-28/components');records=[]
def get(url):
 rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
  body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
 records.append(rec);return d,rec
d,r=get('https://api.github.com/repos/Ducarv/mcpmoat/branches/dev');commit=d['commit']['sha'];r['branch_head_sha']=commit
x,r=get('https://api.github.com/repos/Ducarv/mcpmoat/contents/docs/competitors.md?ref='+commit)
body=base64.b64decode(x['content']);r.update(blob_sha1=x['sha'],body_sha256=hashlib.sha256(body).hexdigest(),body_bytes=len(body));text=body.decode()
old=json.loads((b/'mcpmoat-evidence.json').read_text())[0]
fact={'commit_sha':commit,'pinned_url':'https://github.com/Ducarv/mcpmoat/blob/'+commit+'/docs/competitors.md','branch':'dev','blob_sha1':x['sha'],'body_sha256':r['body_sha256'],'retrieved_at_utc':r['retrieved_at_utc'],'matches_first_read_blob':x['sha']==old['blob_sha'],'declared_check_date':'2026-10-23','line_count':len(text.splitlines()),'scope':'Documentation comparison; explicitly not installed/run; project benchmarks not independently reproduced.','credited_ideas':['ruleset version and digest per report','field-by-field pin diff','severity separate from blocking','plain coverage limits','publish method and held-out test set'],'not_claimed':['package integration','deployed use','independent benchmark replication'],'authorship_note':'Issue/PR authored by Ducarv; 11 PR comments all Ducarv and describe AI review panels. Commit history credits Claude co-author. Account identity does not establish human-only writing.'}
(b/'mcpmoat-current-pinned.json').write_text(json.dumps({'fact':fact,'records':records},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(fact,ensure_ascii=False))
