#!/usr/bin/env python3
"""Prepare aimarket-hub's exact audited wheel and publisher tools; never upload.

Build only committed hub sources. Existing eight-package handoff is read-only.
"""
from __future__ import annotations

import argparse
import datetime
import email
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/vulnetix-review-2026-10-28'
TEMPLATE = BASE/'pypi-handoff'
HANDOFF = BASE/'hub-pypi-handoff'
FIX_MEMBERS = ['aimarket_hub/oracle_paid_tier.py', 'aimarket_hub/outbound_http.py',
    'aimarket_hub/hub_routes/invoke_parts/local_delivery.py',
    'aimarket_hub/hub_routes/invoke_parts/federated_delivery.py']


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('release template changed; review the adaptation')
    return text.replace(before, after, 1)


def verifier():
    spec = importlib.util.spec_from_file_location('hub_release_verifier', HANDOFF/'verify_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare():
    if git('status', '--porcelain', '--', 'aimarket-hub').strip():
        raise ValueError('commit hub sources before preparing the release')
    commit = git('rev-parse', 'HEAD').decode().strip()
    epoch = git('show', '-s', '--format=%ct', commit).decode().strip()
    HANDOFF.mkdir(parents=True, exist_ok=True)
    wheel_dir = HANDOFF/'wheels'
    wheel_dir.mkdir(exist_ok=True)
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is required')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('UV_', 'PIP_', 'TWINE_', 'PYPI_'))}
    env['SOURCE_DATE_EPOCH'] = epoch
    with tempfile.TemporaryDirectory(prefix='hub-release-build-') as temp:
        result = subprocess.run([uv, 'build', '--offline', '--wheel', '--no-create-gitignore',
            '--out-dir', temp, str(ROOT/'aimarket-hub')], env=env, cwd=ROOT, capture_output=True, text=True)
        (HANDOFF/'build.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError('build failed; see build.log')
        wheels = list(Path(temp).glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('expected one hub wheel')
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            metadata = email.message_from_bytes(archive.read(next(
                n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
            if metadata['Name'] != 'aimarket-hub':
                raise ValueError('unexpected package')
            sources = {}
            for name in archive.namelist():
                if not name.endswith('.py') or '.dist-info/' in name:
                    continue
                path = 'aimarket-hub/'+name
                raw = archive.read(name)
                if raw != git('show', commit+':'+path) or raw != (ROOT/path).read_bytes():
                    raise ValueError('wheel source mismatch: '+name)
                sources[name] = hashlib.sha256(raw).hexdigest()
        if not set(FIX_MEMBERS).issubset(sources):
            raise ValueError('missing fix module')
        raw = wheel.read_bytes()
        entry = {'package': 'aimarket-hub', 'version': metadata['Version'], 'wheel': wheel.name,
            'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'requires_python': metadata['Requires-Python'],
            'required_fix_members': FIX_MEMBERS, 'python_sha256': sources,
            'fixes': ['Vulnetix/advisory-database#5 goal 6']}
        # Never mix previously prepared versions into an upload directory.
        if any(p.name != wheel.name for p in wheel_dir.glob('*.whl')):
            raise ValueError('handoff contains a different version; archive it before rebuilding')
        shutil.copyfile(wheel, wheel_dir/wheel.name)
    if git('rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('HEAD changed during build')
    plan = {'source_commit': commit, 'prepared_at_utc': datetime.datetime.now(datetime.UTC).isoformat(),
        'status': 'prepared_only_not_published', 'packages': [entry],
        'source_binding': 'Every packaged Python file equals committed and working source.', 'uploads_performed': 0}
    (HANDOFF/'publication-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    (HANDOFF/'sha256.json').write_text(json.dumps({wheel.name:entry['sha256']}, indent=2)+'\n')
    tool = (TEMPLATE/'verify_release.py').read_text()
    tool = replace_once(tool, "if len(plan['packages']) != 8:",
        "if len(plan['packages']) != 1 or plan['packages'][0]['package'] != 'aimarket-hub':")
    tool = tool.replace('expected_eight_packages', 'expected_one_hub_package').replace('all eight exact-version wheels', 'the exact-version hub wheel')
    (HANDOFF/'verify_release.py').write_text(tool)
    shutil.copyfile(TEMPLATE/'publish_prepared.py', HANDOFF/'publish_prepared.py')
    tests = (ROOT/'tests/test_pypi_release_handoff.py').read_text()
    tests = replace_once(tests, "ROOT = Path(__file__).resolve().parents[1]\nHANDOFF = ROOT/'artifacts/vulnetix-review-2026-10-28/pypi-handoff'",
                         'HANDOFF = Path(__file__).resolve().parent')
    tests = tests.replace("e['package'] == 'aimarket-mcp'", "e['package'] == 'aimarket-hub'")
    tests = tests.replace('test_all_eight_prepared_wheels_match_audited_sources_and_record', 'test_prepared_hub_wheel_matches_audited_sources_and_record')
    tests = tests.replace('assert len(results) == 8', 'assert len(results) == 1')
    tests = tests.replace("assert sum(r['python_files_verified'] for r in results) == 387",
                          f"assert sum(r['python_files_verified'] for r in results) == {len(sources)}")
    local = verifier().local_preflight(plan, HANDOFF)
    tests = tests.replace("assert sum(r['record_entries_verified'] for r in results) == 450",
                          f"assert sum(r['record_entries_verified'] for r in results) == {local[0]['record_entries_verified']}")
    tests = tests.replace("plan['packages'][0]['package'] == 'aimarket-oracle-core'", "plan['packages'][0]['package'] == 'aimarket-hub'")
    (HANDOFF/'test_handoff.py').write_text(tests)
    (HANDOFF/'local-verification.json').write_text(json.dumps(local, indent=2)+'\n')
    print(json.dumps({'source_commit':commit, 'version':entry['version'], 'python_files':len(sources),
                     'sha256':entry['sha256'], 'uploads_performed':0}, indent=2))


def bundle():
    plan = json.loads((HANDOFF/'publication-plan.json').read_text())
    verifier().local_preflight(plan, HANDOFF)
    required = ['PUBLISHING.txt', 'publication-plan.json', 'sha256.json', 'verify_release.py',
        'publish_prepared.py', 'test_handoff.py', 'local-verification.json', 'build.log']
    optional = ['validation.json', 'availability.json', 'tests.log', 'handoff-tests.log', 'secret-scan.json']
    names = required + [n for n in optional if (HANDOFF/n).is_file()]
    names += ['wheels/'+entry['wheel'] for entry in plan['packages']]
    archive = BASE/'hub-pypi-publication-handoff.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(HANDOFF/name, 'hub-pypi-handoff/'+name)
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print('Verified publisher bundle: '+str(archive))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-only', action='store_true')
    args = parser.parse_args()
    if args.bundle_only:
        bundle()
    else:
        prepare()
