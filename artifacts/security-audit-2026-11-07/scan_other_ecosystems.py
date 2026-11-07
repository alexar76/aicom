"""Recheck tracked Rust, Go and Dart dependencies against complete OSV archives."""
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'rust-go-dart'
OUT.mkdir(exist_ok=True)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


scan = module('source_scan', 'scripts/dependency_scan.py')
matcher = module('offline_matcher', 'artifacts/security-audit-2026-10-25/dependencies/match_osv_offline.py')
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
parsers = {'Cargo.lock': scan.cargo_packages, 'go.mod': scan.go_packages, 'pubspec.lock': scan.pub_packages}
inventory, errors, owners = [], [], {}
for relative in sorted(tracked):
    path = ROOT / relative
    if path.name not in parsers or set(Path(relative).parts) & {'artifacts', 'evidence', '.upstreams'}:
        continue
    try:
        packages = parsers[path.name](path)
        inventory.append({'path': relative, 'kind': path.name, 'pinned_registry_versions': len(packages)})
        for key in packages:
            owners.setdefault(key, []).append(relative)
    except Exception as exc:
        errors.append({'path': relative, 'error': str(exc)})
data = [{'ecosystem': eco, 'package': name, 'version': version, 'paths': paths}
        for (eco, name, version), paths in sorted(owners.items())]
for filename, content in [('packages.json', data), ('inventory.json', inventory),
                          ('parse-errors.json', errors), ('unresolved-requirements.json', [])]:
    (OUT / filename).write_text(json.dumps(content, indent=2) + '\n')
matcher.OUT = OUT
matcher.CACHE = Path('/private/tmp/aicom-security-audit-20261107')
matcher.run()
