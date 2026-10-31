"""Match pinned Vulnetix OSV records locally against source/dependency versions."""
import collections,importlib.util,json,tomllib,sys
from pathlib import Path
from packaging.utils import canonicalize_name
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('offline',ROOT/'artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
phase='dependencies-after' if '--after' in sys.argv else 'dependencies'
packages=json.loads((OUT/phase/'packages.json').read_text());inventory=json.loads((OUT/phase/'inventory.json').read_text())
owned=[]
for row in inventory:
 p=ROOT/row['path']
 try:
  if p.name=='pyproject.toml':
   d=tomllib.loads(p.read_text()).get('project',{});eco='PyPI'
  elif p.name=='package.json':d=json.loads(p.read_text());eco='npm'
  else:continue
  if d.get('name') and d.get('version'):owned.append({'ecosystem':eco,'package':d['name'],'version':d['version'],'paths':[row['path']],'owned':True})
 except Exception:continue
packages+=owned
index=collections.defaultdict(list)
for p in packages:index[(p['ecosystem'],m.normalize(p['ecosystem'],p['package']))].append(p)
hits=[];errors=[];records=0;withdrawn=0
for path in Path('/private/tmp/aicom-security-review-20261030/vulnetix-osv').glob('*.json'):
 d=json.loads(path.read_text());records+=1
 if d.get('withdrawn'):withdrawn+=1;continue
 for a in d.get('affected',[]):
  pkg=a.get('package',{});eco=pkg.get('ecosystem');name=pkg.get('name','')
  for p in index.get((eco,m.normalize(eco,name)),[]):
   try:
    if not m.affected(eco,p['version'],a):continue
   except Exception as e:errors.append({'id':d['id'],'package':p,'error':str(e)});continue
   hits.append({**p,'id':d['id'],'summary':d.get('summary'),'classification':d.get('database_specific',{}).get('vulnetix',{}).get('classification'),'modified':d.get('modified'),'fixed':m.scan.fixed_versions(d,eco,name),'references':d.get('references',[])})
(OUT/'vulnetix-owned-packages.json').write_text(json.dumps(owned,indent=2)+'\n')
(OUT/('vulnetix-matches-after.json' if '--after' in sys.argv else 'vulnetix-matches.json')).write_text(json.dumps({'records_checked':records,'withdrawn_skipped':withdrawn,'package_versions_including_owned':len(packages),'owned_package_versions':len(owned),'matches':hits,'errors':errors},indent=2)+'\n')
print('records',records,'owned',len(owned),'matches',len(hits),'errors',len(errors))
for h in hits:print(h['id'],h['package'],h['version'],'owned',h.get('owned',False),h['summary'])
