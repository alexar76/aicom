#!/usr/bin/env python3
"""Cross-check current source and the SDK-excluded tooling candidate locally."""
from pathlib import Path
import collections
import importlib.util
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

scan = module('npm_scan', 'scripts/dependency_scan.py')
match = module('npm_match', 'artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py')
inventory = json.loads((OUT / 'inventory.json').read_text())
owners = collections.defaultdict(set)
for rel in inventory['lockfiles']:
    for key in scan.npm_packages(ROOT / rel):
        owners[key].add(rel)
for rel in inventory['manifests']:
    for key in scan.npm_manifest_packages(ROOT / rel):
        owners[key].add(rel)
for key in scan.npm_packages(OUT / 'extension-fixed-package-lock.json'):
    owners[key].add('SDK-excluded isolated dev-tooling candidate')
index = collections.defaultdict(list)
for (eco, name, version), paths in owners.items():
    index[name].append({'ecosystem': eco, 'package': name, 'version': version, 'paths': sorted(paths)})
errors, findings = [], []
count = 0
with zipfile.ZipFile('/private/tmp/aicom-security-audit-20261107/npm.zip') as archive:
    for info in archive.infolist():
        if not info.filename.endswith('.json'):
            continue
        advisory = json.loads(archive.read(info))
        count += 1
        if advisory.get('withdrawn'):
            continue
        for affected in advisory.get('affected', []):
            package = affected.get('package', {})
            if package.get('ecosystem') != 'npm':
                continue
            for target in index.get(package.get('name', ''), []):
                try:
                    hit = match.affected('npm', target['version'], affected)
                except Exception as exc:
                    errors.append({'id': advisory.get('id'), **target, 'error': str(exc)})
                    continue
                if hit:
                    findings.append({'id': advisory['id'], 'aliases': advisory.get('aliases', []),
                                     'summary': advisory.get('summary'), 'severity': scan.severity_of(advisory),
                                     **target})
tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
tracked_findings = [{**f, 'paths': [p for p in f['paths'] if p in tracked]}
                    for f in findings if any(p in tracked for p in f['paths'])]
report = {'source': 'https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip',
          'advisories': count, 'distinct_versions': len(owners), 'all_findings': findings,
          'tracked_findings': tracked_findings, 'errors': errors,
          'tracked_distinct_versions': sum(any(p in tracked for p in paths) for paths in owners.values()),
          'isolated_tooling_candidate_distinct_versions': sum('SDK-excluded isolated dev-tooling candidate' in paths for paths in owners.values())}
(OUT / 'osv-crosscheck-final.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({**report, 'all_findings': len(findings)}, indent=2))
