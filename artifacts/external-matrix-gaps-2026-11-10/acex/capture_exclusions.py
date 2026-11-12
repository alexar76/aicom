"""Read two concrete false-positive candidates; no GitHub API or execution."""
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
helper=ROOT.parents[1]/'external-components-2026-11-10/core/capture_public.py'
spec=importlib.util.spec_from_file_location('local_public_capture',helper)
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
capture.ROOT=ROOT
sources={'pypi-acex-homonym':'https://pypi.org/pypi/acex/json','fastly-own-acex-doc':'https://ithub.global.ssl.fastly.net/alexar76/acex/blob/main/docs/jupiter-routing.md'}
rows=capture.run(sources,'primary-index.json')
for row in rows:
 summary={k:v for k,v in row.items() if k in ('id','status','bytes','complete','error')}
 if row.get('status')==200 and row['id']=='pypi-acex-homonym':
  data=json.loads((ROOT/row['body_path']).read_text());info=data['info'];summary.update({k:info.get(k) for k in ('name','version','summary','author','home_page','project_urls')})
 print(json.dumps(summary,ensure_ascii=False))
