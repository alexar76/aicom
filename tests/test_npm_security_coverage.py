"""Regression coverage for nested npm manifests and exported repositories."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_npm_security', ROOT / 'scripts/security/configure_npm_security.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def test_nested_studio_gets_coverage_and_existing_ecosystems_survive(tmp_path):
    studio = tmp_path / 'hephaestus/studio'
    studio.mkdir(parents=True)
    (studio / 'package.json').write_text('{}')
    gh = tmp_path / '.github'
    gh.mkdir()
    pip = {'package-ecosystem': 'pip', 'directory': '/backend', 'schedule': {'interval': 'monthly'}}
    (gh / 'dependabot.yml').write_text(yaml.safe_dump({'version': 2, 'updates': [pip]}))
    assert config.configure(tmp_path)
    first = (gh / 'dependabot.yml').read_bytes()
    assert config.configure(tmp_path)
    assert (gh / 'dependabot.yml').read_bytes() == first
    data = yaml.safe_load(first)
    assert pip in data['updates']
    npm = next(e for e in data['updates'] if e['package-ecosystem'] == 'npm')
    assert npm['directories'] == ['/', '/**/*']
    assert npm['groups']['npm-security']['applies-to'] == 'security-updates'
    wf = yaml.safe_load((gh / 'workflows/npm-dependency-audit.yml').read_text())
    assert wf['permissions'] == {'contents': 'read'}
    audit = wf['jobs']['audit']
    assert audit['strategy']['fail-fast'] is False
    command = next(s['run'] for s in audit['steps'] if 'run' in s)
    assert '--include=dev' in command and '--audit-level=high' in command
    assert '|| true' not in command and '--omit=dev' not in command
    for job in wf['jobs'].values():
        for step in job['steps']:
            if 'uses' in step:
                assert re.fullmatch(r'[^@]+@[0-9a-f]{40}', step['uses'])


def test_no_config_for_repository_without_npm(tmp_path):
    (tmp_path / 'requirements.txt').write_text('pytest==8.0.0')
    assert not config.configure(tmp_path)
    assert not (tmp_path / '.github').exists()


def test_custom_registry_policy_is_not_overwritten(tmp_path):
    (tmp_path / 'package.json').write_text('{}')
    (tmp_path / '.github').mkdir()
    p = tmp_path / '.github/dependabot.yml'
    text = yaml.safe_dump({'version': 2, 'updates': [{'package-ecosystem': 'npm', 'directory': '/', 'registries': ['private']}]})
    p.write_text(text)
    with pytest.raises(ValueError, match='custom npm restrictions'):
        config.configure(tmp_path)
    assert p.read_text() == text


def test_all_committed_lockfiles_exclude_the_reported_vulnerable_versions():
    locks = subprocess.check_output(['git', 'ls-files', '*package-lock.json'], cwd=ROOT, text=True).splitlines()
    bad = []
    for path in locks:
        data = json.loads((ROOT / path).read_text())
        for location, meta in data.get('packages', {}).items():
            if meta.get('link'):
                continue
            name = location.split('node_modules/')[-1]
            if name not in {'vite', 'esbuild', 'source-map-js', 'launch-editor'}:
                continue
            version = tuple(int(x) for x in meta['version'].split('.')[:3])
            if name == 'vite':
                unsafe = (version < (6, 4, 3)
                          or (7, 0, 0) <= version < (7, 3, 5)
                          or (8, 0, 0) <= version < (8, 0, 16))
            else:
                minimum = {'esbuild': (0, 25, 0), 'source-map-js': (1, 2, 2), 'launch-editor': (2, 14, 1)}[name]
                unsafe = version < minimum
            if unsafe:
                bad.append(f'{path}: {location}@{meta["version"]}')
    assert not bad, '\n'.join(bad)
