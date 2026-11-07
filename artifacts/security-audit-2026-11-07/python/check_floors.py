import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];BASE=Path(__file__).resolve().parent;PHASE=sys.argv[1] if len(sys.argv)>1 else 'before'; OUT=BASE/('floors' if PHASE=='before' else 'floors-'+PHASE);OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('matcher',ROOT/'artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
(OUT/'packages.json').write_text((BASE/PHASE/'floor-candidates.json').read_text())
for f in ('inventory.json','parse-errors.json','unresolved-requirements.json'):(OUT/f).write_text((BASE/PHASE/f).read_text())
m.OUT=OUT;m.CACHE=Path('/private/tmp/aicom-security-audit-20261107');m.run()
