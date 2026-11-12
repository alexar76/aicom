"""Paced exact-component README search; stop on public API throttle."""
import importlib.util,json,time,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture',ROOT/'capture_public.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
QUERIES=[
('bridges','"aimarket-bridges" in:readme -user:alexar76'),
('widget','"@aimarket/widget" in:readme -user:alexar76'),
('service-mesh','"github.com/alexar76/ai-service-mesh" in:readme -user:alexar76'),
('protocol','"github.com/alexar76/aimarket-protocol" in:readme -user:alexar76'),
('treasury','"aimarket-treasury" in:readme -user:alexar76'),
('acex','"github.com/alexar76/acex" in:readme -user:alexar76'),
('pulse','"github.com/alexar76/pulse-terminal" in:readme -user:alexar76'),
('escrow-signer','"github.com/alexar76/escrow-signer" in:readme -user:alexar76')]
if __name__=='__main__':
 rows=[]
 for i,(component,query) in enumerate(QUERIES,1):
  url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':query,'per_page':30})
  row=m.capture(('github-search-'+str(i),url));row.update(component=component,query=query)
  if row.get('status')==200:
   data=json.loads((ROOT/row['body_path']).read_text());row.update(total_count=data.get('total_count'),incomplete_results=data.get('incomplete_results'),items=[{k:x.get(k) for k in ('full_name','fork','default_branch','html_url','description','pushed_at')} for x in data.get('items',[])])
  rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
  if row.get('status') in (403,429):break
  if i<len(QUERIES):time.sleep(8)
 (ROOT/'github-search-index.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
