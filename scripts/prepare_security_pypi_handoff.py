#!/usr/bin/env python3
"""Rebuild the eight security wheels and refresh their publisher handoff; never upload."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import email
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HANDOFF = ROOT/'artifacts/vulnetix-review-2026-10-28/pypi-handoff'
PROJECTS = {
    'aimarket-oracle-core': 'oracles/core',
    'aimarket-atlas': 'atlas',
    'aimarket-logos': 'logos',
    'aimarket-mcp': 'aimarket-mcp',
    'aimarket-metis': 'metis',
    'aimarket-platon': 'platon/backend',
    'aimarket-treasury': 'treasury',
    'skopos-fleet': 'skopos',
}


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True).stdout


def refresh(handoff):
    handoff = handoff.resolve()
    if not handoff.is_relative_to(ROOT):
        raise ValueError('handoff must be inside this workspace')
    plan_path = handoff/'publication-plan.json'
    plan = json.loads(plan_path.read_text())
    if {row['package'] for row in plan['packages']} != set(PROJECTS):
        raise ValueError('expected exactly the eight security projects')
    source_commit = git('rev-parse', 'HEAD').decode().strip()
    previous_commit = plan['source_commit']
    if git('diff', 'HEAD', '--name-only', '--', *PROJECTS.values()).strip():
        raise ValueError('package source has uncommitted changes')
    uv = shutil.which('uv')
    if uv is None:
        raise RuntimeError('uv is required for offline builds')
    logs = handoff/'build-logs'
    logs.mkdir(exist_ok=True)
    epoch = git('show', '-s', '--format=%ct', source_commit).decode().strip()
    env = {key: value for key, value in os.environ.items() if not key.startswith(('UV_', 'PIP_'))}
    env['SOURCE_DATE_EPOCH'] = epoch
    with tempfile.TemporaryDirectory(prefix='aicom-release-refresh-') as temporary:
        output = Path(temporary)

        def build(package):
            command = [uv, 'build', '--offline', '--wheel', '--no-create-gitignore',
                       '--out-dir', str(output), str(ROOT/PROJECTS[package])]
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            (logs/(package+'.log')).write_text(completed.stdout+completed.stderr)
            return package, completed.returncode

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(pool.map(build, PROJECTS))
        if any(results.values()):
            raise RuntimeError('build failed; inspect build-logs')
        wheels = list(output.glob('*.whl'))
        if len(wheels) != 8:
            raise ValueError('expected eight freshly built wheels')
        by_package = {}
        for wheel in wheels:
            raw = wheel.read_bytes()
            with zipfile.ZipFile(wheel) as archive:
                metadata = email.message_from_bytes(archive.read(next(
                    n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
                package = metadata['Name']
                if package not in PROJECTS or package in by_package:
                    raise ValueError('unexpected or duplicate package identity')
                python_hashes = {}
                for name in archive.namelist():
                    if not name.endswith('.py') or '.dist-info/' in name:
                        continue
                    source = (Path(PROJECTS[package])/name).as_posix()
                    content = archive.read(name)
                    if content != git('show', source_commit+':'+source):
                        raise ValueError('packaged Python differs from source commit: '+source)
                    if content != (ROOT/source).read_bytes():
                        raise ValueError('working source changed while building: '+source)
                    python_hashes[name] = hashlib.sha256(content).hexdigest()
                by_package[package] = dict(wheel=wheel.name, version=metadata['Version'],
                    sha256=hashlib.sha256(raw).hexdigest(), size=len(raw),
                    requires_python=metadata['Requires-Python'], python_sha256=python_hashes)
        refreshed = []
        for row in plan['packages']:
            fresh = dict(row)
            fresh.update(by_package[row['package']])
            if not set(row['required_fix_members']).issubset(fresh['python_sha256']):
                raise ValueError('required fix module absent')
            refreshed.append(fresh)
        if git('rev-parse', 'HEAD').decode().strip() != source_commit:
            raise ValueError('HEAD changed during preparation; rerun')
        wheel_dir = handoff/'wheels'
        wheel_dir.mkdir(exist_ok=True)
        expected = {row['wheel'] for row in refreshed}
        for old in wheel_dir.glob('*.whl'):
            if old.name not in expected:
                old.unlink()
        for wheel in wheels:
            shutil.copyfile(wheel, wheel_dir/wheel.name)
    changes = git('diff', '--name-only', previous_commit, source_commit, '--',
                  *PROJECTS.values()).decode().splitlines()
    plan.update(source_commit=source_commit,
        prepared_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='prepared_only_not_published', packages=refreshed,
        refresh={'previous_source_commit': previous_commit,
                 'changed_package_paths_since_previous_preparation': changes,
                 'source_binding': 'Every packaged Python file equals git show source_commit:path and current workspace.',
                 'build_policy': 'offline uv build; SOURCE_DATE_EPOCH fixed to source commit time',
                 'uploads_performed': 0})
    plan['validation']['all_packaged_python_sources_verified'] = sum(
        len(row['python_sha256']) for row in refreshed)
    plan['validation']['baseline_tests_source_commit'] = 'e35551666fb0e8a4388cef4ebce6858f00216dc7'
    plan_path.write_text(json.dumps(plan, indent=2)+'\n')
    (handoff/'sha256.json').write_text(json.dumps({r['wheel']: r['sha256'] for r in refreshed}, indent=2)+'\n')
    (handoff/'requirements-security.txt').write_text(''.join(
        r['package']+'=='+r['version']+'\n' for r in refreshed))
    instructions = handoff/'PUBLISHING.txt'
    text = instructions.read_text()
    text = re.sub(r'Исходники: коммит [0-9a-f]{40}', 'Исходники: коммит '+source_commit, text)
    instructions.write_text(text)
    spec = importlib.util.spec_from_file_location('refreshed_release_verifier', handoff/'verify_release.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    local = verifier.local_preflight(plan, handoff)
    (handoff/'local-preflight.json').write_text(json.dumps({
        'observed_at_utc': plan['prepared_at_utc'], 'mode': 'local', 'source_commit': source_commit,
        'passed': True, 'uploads_performed': 0, 'credentials_read': False, 'packages': local,
    }, indent=2)+'\n')
    print(json.dumps({'source_commit': source_commit, 'wheels_rebuilt': len(refreshed),
        'python_sources_verified': plan['validation']['all_packaged_python_sources_verified'],
        'changed_paths': changes, 'uploads_performed': 0}, indent=2))


def bundle(handoff):
    """Package only the handoff allowlist; credentials and caches cannot enter it."""
    handoff = handoff.resolve()
    plan = json.loads((handoff/'publication-plan.json').read_text())
    spec = importlib.util.spec_from_file_location('bundle_release_verifier', handoff/'verify_release.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.local_preflight(plan, handoff)
    tests = (ROOT/'tests/test_pypi_release_handoff.py').read_text()
    tests = tests.replace(
        "ROOT = Path(__file__).resolve().parents[1]\nHANDOFF = ROOT/'artifacts/vulnetix-review-2026-10-28/pypi-handoff'",
        "HANDOFF = Path(__file__).resolve().parent")
    (handoff/'test_handoff.py').write_text(tests)
    required = ['PUBLISHING.txt', 'publication-plan.json', 'sha256.json',
                'requirements-security.txt', 'verify_release.py', 'publish_prepared.py',
                'test_handoff.py', 'local-preflight.json']
    optional = ['availability-at-preparation.json', 'refresh-validation.json',
                'refresh-tests.log', 'treasury-refresh-tests.log']
    files = [handoff/name for name in required]
    files += [handoff/name for name in optional if (handoff/name).is_file()]
    files += [handoff/'build-logs'/(name+'.log') for name in PROJECTS]
    files += [handoff/'wheels'/entry['wheel'] for entry in plan['packages']]
    archive = handoff.parent/'pypi-publication-handoff.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, 'pypi-handoff/'+path.relative_to(handoff).as_posix())
    with zipfile.ZipFile(archive) as output:
        for row in plan['packages']:
            raw = output.read('pypi-handoff/wheels/'+row['wheel'])
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('bundled wheel differs from manifest')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n')
    print(json.dumps({'bundle': str(archive.relative_to(ROOT)),
        'source_commit': plan['source_commit'], 'wheels': 8, 'sha256': digest,
        'uploads_performed': 0}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff-dir', type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument('--bundle-only', action='store_true', help='verify and package an already refreshed handoff')
    args = parser.parse_args()
    if not args.bundle_only:
        refresh(args.handoff_dir)
    bundle(args.handoff_dir)


if __name__ == '__main__':
    main()
