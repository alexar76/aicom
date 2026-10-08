#!/usr/bin/env python3
"""Configure npm maintenance in a source tree or an exported satellite.

Usage: python3 scripts/security/configure_npm_security.py PATH [PATH ...]
Existing non-npm Dependabot settings are preserved. The workflow discovers all
committed lockfiles at run time; Dependabot also covers new nested manifests.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

SKIP = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '.next',
        '.upstreams', '.cache', 'vendor', '.pnpm-store'}


def has_npm(root: Path) -> bool:
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not Path(base, d).is_symlink()]
        if 'package.json' in files:
            return True
    return False


def configure(root: Path) -> bool:
    if not has_npm(root):
        return False
    config = root / '.github/dependabot.yml'
    data = yaml.safe_load(config.read_text()) if config.exists() else {'version': 2, 'updates': []}
    updates = data.setdefault('updates', [])
    npm_entries = [entry for entry in updates if entry.get('package-ecosystem') == 'npm']
    # Do not silently discard bespoke registries/branches/ignore rules.
    special = {'registries', 'target-branch', 'ignore', 'allow', 'exclude-paths'}
    if any(special.intersection(entry) for entry in npm_entries):
        raise ValueError(f'{config}: review custom npm restrictions before expanding coverage')
    entry = dict(npm_entries[0]) if npm_entries else {'package-ecosystem': 'npm'}
    entry.pop('directory', None)
    entry.update({
        'directories': ['/', '/**/*'],
        'schedule': {'interval': 'weekly', 'day': 'monday'},
        'open-pull-requests-limit': 10,
        'groups': {
            'npm-security': {'applies-to': 'security-updates', 'patterns': ['*']},
            'npm-minor-patch': {'patterns': ['*'], 'update-types': ['minor', 'patch']},
        },
    })
    data['updates'] = [e for e in updates if e.get('package-ecosystem') != 'npm'] + [entry]
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('# npm coverage is maintained by scripts/security/configure_npm_security.py.\n'
                      + yaml.safe_dump(data, sort_keys=False))
    workflow = config.parent / 'workflows/npm-dependency-audit.yml'
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_bytes(Path(__file__).with_name('npm-dependency-audit.yml').read_bytes())
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', type=Path, nargs='+')
    for root in parser.parse_args().roots:
        if configure(root):
            print(root)
