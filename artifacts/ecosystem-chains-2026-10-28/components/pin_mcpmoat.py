from pathlib import Path
import urllib.request,json,hashlib
from datetime import datetime,timezone
b=Path('artifacts/ecosystem-chains-2026-10-28/components')
records=[]
url='https://api.github.com/repos/Ducarv/mcpmoat/commits?sha=dev&path=docs%2Fcompetitors.md&per_page=1'
rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
 body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),items=[{'sha':x['sha'],'html_url':x['html_url'],'author':x['commit']['author'],'committer':x['commit']['committer'],'message':x['commit']['message']} for x in d])
records.append(rec)
commit=d[0]['sha'];url='https://raw.githubusercontent.com/Ducarv/mcpmoat/'+commit+'/docs/competitors.md';rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
 body=r.read();txt=body.decode();rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),git_blob_sha1=hashlib.sha1(b'blob '+str(len(body)).encode()+bytes([0])+body).hexdigest())
records.append(rec)
fact={'commit_sha':commit,'pinned_url':'https://github.com/Ducarv/mcpmoat/blob/'+commit+'/docs/competitors.md','blob_sha1':rec['git_blob_sha1'],'body_sha256':rec['sha256'],'retrieved_at_utc':rec['retrieved_at_utc'],'declared_check_date':'2026-10-23','scope':'Documentation comparison; explicitly not installed/run; project benchmarks not independently reproduced.','credited_ideas':['ruleset version and digest per report','field-by-field pin diff','severity separate from blocking','plain coverage limits','publish method and held-out test set'],'not_claimed':['package integration','deployed use','independent benchmark replication'],'authorship_note':'Issue/PR authored by Ducarv; 11 PR comments all Ducarv and describe AI review panels. Account identity does not establish human-only writing.'}
(b/'mcpmoat-pinned.json').write_text(json.dumps({'fact':fact,'records':records},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'fact':fact,'commit':d[0]['commit']},ensure_ascii=False))
