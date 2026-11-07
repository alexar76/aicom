from __future__ import annotations
import collections, importlib.util,json,subprocess,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];BASE=Path(__file__).resolve().parent
paths=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines();changes=[]
def reqs(d):
 out={}
 for i,v in enumerate(d.get('project',{}).get('dependencies',[])):out[f'project.dependencies[{i}]']=v
 for group,vs in d.get('project',{}).get('optional-dependencies',{}).items():
  for i,v in enumerate(vs):out[f'project.optional-dependencies.{group}[{i}]']=v
 for group,vs in d.get('dependency-groups',{}).items():
  for i,v in enumerate(vs):
   if isinstance(v,str):out[f'dependency-groups.{group}[{i}]']=v
 return out
for path in paths:
 p=ROOT/path
 if p.name!='pyproject.toml' and not(p.name.startswith('requirements') and p.suffix=='.txt'):continue
 old=subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT,text=True);new=p.read_text()
 if p.name=='pyproject.toml':
  a=reqs(tomllib.loads(old));b=reqs(tomllib.loads(new))
  for key in a:
   if a[key]!=b.get(key):changes.append({'path':path,'location':key,'before':a[key],'after':b.get(key)})
 else:
  for i,(a,b) in enumerate(zip(old.splitlines(),new.splitlines()),1):
   if a!=b and not a.lstrip().startswith('#'):changes.append({'path':path,'line':i,'before':a,'after':b})
(BASE/'declaration-changes.json').write_text(json.dumps(changes,indent=2)+'\n')
for label,env in [('runtime-graph','/private/tmp/aicom-python-security-20261107'),('mcp-minimum-graph','/private/tmp/aicom-mcp-minimum-20261107')]:
 out=BASE/label;out.mkdir(exist_ok=True)
 script="""import importlib.metadata as m,json
rows=[]
for d in m.distributions():
 direct=d.read_text('direct_url.json')
 if direct and json.loads(direct).get('dir_info',{}).get('editable'):continue
 rows.append({'ecosystem':'PyPI','package':d.metadata['Name'],'version':d.version,'paths':['isolated-test-environment'],'requires_python':d.metadata.get('Requires-Python')})
print(json.dumps(rows))"""
 raw=subprocess.check_output([env+'/bin/python','-c',script],text=True);(out/'packages.json').write_text(raw+'\n')
 for f in ('inventory.json','parse-errors.json','unresolved-requirements.json'):(out/f).write_text('[]\n')
 spec=importlib.util.spec_from_file_location('match_'+label,ROOT/'artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=out;m.CACHE=Path('/private/tmp/aicom-security-audit-20261107');m.run()
print('DECLARATIONS',len(changes),'FILES',len({r['path'] for r in changes}))
