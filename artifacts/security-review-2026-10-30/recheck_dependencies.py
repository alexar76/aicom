"""Reuse the previously validated inventory and matcher against today's downloaded databases."""
import importlib.util,json,subprocess,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
phase=sys.argv[1] if len(sys.argv)>1 else 'after'
def module(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
out=OUT/('dependencies-'+phase);out.mkdir(exist_ok=True)
i=module('inventory','artifacts/security-audit-2026-10-25/dependencies/audit_dependencies.py');i.OUT=out;i.run()
m=module('offline','artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py');m.OUT=out;m.CACHE=Path('/private/tmp/aicom-security-review-20261030');m.run()
tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
fs=json.loads((out/'findings.json').read_text());tf=[{**f,'paths':[x for x in f['paths'] if x in tracked]} for f in fs if any(x in tracked for x in f['paths'])]
(out/'tracked-findings.json').write_text(json.dumps(tf,indent=2)+'\n')
print('TRACKED',len(tf),'advisories',len({f['id'] for f in tf}),dict(collections.Counter(f['severity'] for f in tf)))
