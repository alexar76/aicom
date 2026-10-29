from pathlib import Path
import urllib.request,json,hashlib
from datetime import datetime,timezone
b=Path('artifacts/ecosystem-chains-2026-10-28/components');url='https://api.github.com/repos/Ducarv/mcpmoat'
rec={'url':url,'method':'GET','retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AICOM-public-research'}),timeout=25) as r:
 body=r.read();d=json.loads(body);rec.update(status=r.status,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body),selected={k:d.get(k) for k in ['html_url','full_name','fork','default_branch','created_at','pushed_at','archived','license']})
(b/'mcpmoat-repository.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(rec['selected'],ensure_ascii=False))
