"""Audit first-party Python manifest pins against a downloaded public OSV snapshot."""
from __future__ import annotations
import collections, importlib.util, json, subprocess, sys, tomllib
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
PHASE=sys.argv[1] if len(sys.argv)>1 else 'before'
DEST=OUT/PHASE
DEST.mkdir(exist_ok=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
scan=module('scan','scripts/dependency_scan.py')
matcher=module('matcher','artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py')
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
paths=[p for p in paths if p and not p.startswith(('artifacts/','docs/evidence/','dist/','build/','dist-pypi-')) and '/.upstreams/' not in p and '/vendor/' not in p]
owners=collections.defaultdict(set);inventory=[];unresolved=[];errors=[];floors=collections.defaultdict(set)
def add(eco,n,v,p): owners[(eco,canonicalize_name(n),v)].add(p)
def requirement(text,path):
    try: req=Requirement(text)
    except Exception as exc: errors.append({'path':path,'requirement':text,'error':str(exc)});return
    pins=[x.version for x in req.specifier if x.operator=='==' and '*' not in x.version]
    if len(pins)==1: add('PyPI',req.name,pins[0],path)
    else:
        unresolved.append({'path':path,'requirement':text})
        for item in req.specifier:
            if item.operator=='>=': floors[(canonicalize_name(req.name),item.version)].add(path)
for path in paths:
    p=ROOT/path;name=p.name
    if name not in ('pyproject.toml','uv.lock','requirements.lock') and not(name.startswith('requirements') and name.endswith(('.txt','.in'))): continue
    inventory.append({'path':path,'kind':name})
    try:
        if name=='uv.lock':
            for eco,n,v in scan.uv_packages(p): add(eco,n,v,path)
        elif name=='pyproject.toml':
            d=tomllib.loads(p.read_text());proj=d.get('project',{});reqs=list(proj.get('dependencies',[]))
            for group in proj.get('optional-dependencies',{}).values(): reqs.extend(group)
            for group in d.get('dependency-groups',{}).values(): reqs.extend(x for x in group if isinstance(x,str))
            for req in reqs: requirement(req,path)
        else:
            for line in p.read_text().splitlines():
                line=line.strip()
                if not line or line.startswith(('#','--','-r ','-c ')): continue
                if line.startswith(('./','../')):
                    unresolved.append({'path':path,'requirement':line,'reason':'local source path, outside public registry matching'});continue
                line=line.removesuffix('\\').strip().split(' #',1)[0].strip()
                requirement(line,path)
    except Exception as exc: errors.append({'path':path,'error':str(exc)})
packages=[{'ecosystem':e,'package':n,'version':v,'paths':sorted(o)} for (e,n,v),o in sorted(owners.items())]
for name,d in [('packages.json',packages),('inventory.json',inventory),('unresolved-requirements.json',unresolved),('parse-errors.json',errors),('floor-candidates.json',[{'ecosystem':'PyPI','package':n,'version':v,'paths':sorted(o)} for (n,v),o in floors.items()])]:
    (DEST/name).write_text(json.dumps(d,indent=2)+'\n')
matcher.OUT=DEST;matcher.CACHE=Path('/private/tmp/aicom-security-audit-20261107');matcher.run()
