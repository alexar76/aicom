#!/usr/bin/env python3
"""Read-only fresh registry audits, with complete per-lockfile evidence."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CACHE = Path('/private/tmp/aicom-security-audit-20261107/npm-registry-cache')
phase = sys.argv[1] if len(sys.argv) > 1 else 'before'
inventory = json.loads((OUT / 'inventory.json').read_text())
tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
(OUT / phase).mkdir(exist_ok=True)

def audit(lock):
    workdir = ROOT / Path(lock).parent
    result = subprocess.run([
        'npm', 'audit', '--package-lock-only', '--ignore-scripts', '--include=dev',
        '--json', '--cache', str(CACHE), '--fetch-retries=1',
        '--fetch-timeout=45000',
    ], cwd=workdir, text=True, capture_output=True, timeout=150)
    slug = str(Path(lock).parent).replace('/', '__')
    (OUT / phase / (slug + '.json')).write_text(result.stdout)
    (OUT / phase / (slug + '.stderr')).write_text(result.stderr)
    data = json.loads(result.stdout)
    return {'lockfile':lock, 'tracked': lock in tracked, 'returncode':result.returncode,
            'counts':data.get('metadata',{}).get('vulnerabilities'),
            'vulnerabilities':data.get('vulnerabilities'), 'error':data.get('error')}

results=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    futures={pool.submit(audit, lock):lock for lock in inventory['lockfiles']}
    for future in as_completed(futures):
        lock=futures[future]
        try: result=future.result()
        except Exception as exc: result={'lockfile':lock,'error':str(exc)}
        results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k!='vulnerabilities'}), flush=True)
summary={'source':'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk',
         'observed_at':datetime.now(timezone.utc).isoformat(),
         'results':sorted(results,key=lambda v:v['lockfile'])}
(OUT / (phase + '-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
