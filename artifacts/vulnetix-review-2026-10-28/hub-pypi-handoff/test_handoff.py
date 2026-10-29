"""Release handoff checks use prepared files and simulated PyPI; never real uploads."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest

HANDOFF = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verifier():
    return load('handoff_verifier', HANDOFF/'verify_release.py')


@pytest.fixture
def wheel():
    plan = json.loads((HANDOFF/'publication-plan.json').read_text())
    entry = next(e for e in plan['packages'] if e['package'] == 'aimarket-hub')
    return entry, (HANDOFF/'wheels'/entry['wheel']).read_bytes()


def metadata_for(entry):
    return {'info': {'name': entry['package'], 'version': entry['version']}, 'urls': [{
        'filename': entry['wheel'], 'size': entry['size'], 'yanked': False,
        'digests': {'sha256': entry['sha256']},
        'url': 'https://files.pythonhosted.org/packages/'+entry['wheel'],
        'upload_time_iso_8601': '2026-10-28T00:00:00Z',
    }]}


def test_prepared_hub_wheel_matches_audited_sources_and_record(verifier):
    plan = json.loads((HANDOFF/'publication-plan.json').read_text())
    results = verifier.local_preflight(plan)
    assert len(results) == 1
    assert sum(r['python_files_verified'] for r in results) == 176
    assert sum(r['record_entries_verified'] for r in results) == 207
    assert all(r['all_required_fix_modules_present'] for r in results)
    assert plan['packages'][0]['package'] == 'aimarket-hub'


def test_modified_wheel_is_refused(verifier, wheel):
    entry, raw = wheel
    with pytest.raises(verifier.VerificationError, match='wheel_bytes_differ'):
        verifier.inspect_wheel(raw+b'changed', entry)


@pytest.mark.parametrize('url', [
    'http://pypi.org/project/example',
    'https://files.pythonhosted.org.attacker.example/wheel',
    'https://127.0.0.1/wheel',
    'file:///tmp/wheel',
    'https://user:password@pypi.org/pypi/example/json',
])
def test_downloads_restrict_https_origins(verifier, url):
    with pytest.raises(verifier.VerificationError, match='unexpected_download_origin'):
        verifier.checked_url(url)


def test_unpublished_version_is_available_but_never_verified_as_published(verifier, wheel, monkeypatch):
    entry, _ = wheel

    def missing(url):
        raise urllib.error.HTTPError(url, 404, 'Not Found', None, None)

    monkeypatch.setattr(verifier, 'fetch', missing)
    assert verifier.inspect_remote(entry, download=False)['status'] == 'available_for_new_release'
    assert verifier.inspect_remote(entry, download=True)['status'] == 'not_published'


def test_published_wheel_requires_actual_download_and_exact_content(verifier, wheel, monkeypatch):
    entry, raw = wheel
    calls = []

    def serve(url):
        calls.append(url)
        return json.dumps(metadata_for(entry)).encode() if url.endswith('/json') else raw

    monkeypatch.setattr(verifier, 'fetch', serve)
    result = verifier.inspect_remote(entry, download=True)
    assert result['status'] == 'published_verified'
    assert result['identical_to_audited_build']
    assert len(calls) == 2 and calls[1].startswith('https://files.pythonhosted.org/')


def test_correct_registry_digest_cannot_hide_tampered_download(verifier, wheel, monkeypatch):
    entry, raw = wheel
    monkeypatch.setattr(verifier, 'fetch', lambda url: json.dumps(metadata_for(entry)).encode()
                        if url.endswith('/json') else raw+b'tampered')
    with pytest.raises(verifier.VerificationError, match='wheel_bytes_differ'):
        verifier.inspect_remote(entry, download=True)


@pytest.mark.parametrize('change,reason', [
    ('digest', 'published_wheel_conflicts'),
    ('yanked', 'published_wheel_is_yanked'),
    ('extra-wheel', 'unreviewed_wheels'),
])
def test_conflicting_or_unreviewed_release_stops_publication_preflight(
    verifier, wheel, monkeypatch, change, reason
):
    entry, _ = wheel
    metadata = metadata_for(entry)
    if change == 'digest':
        metadata['urls'][0]['digests']['sha256'] = '0'*64
    elif change == 'yanked':
        metadata['urls'][0]['yanked'] = True
    else:
        metadata['urls'].append({'filename': 'unreviewed-platform.whl'})
    monkeypatch.setattr(verifier, 'fetch', lambda url: json.dumps(metadata).encode())
    with pytest.raises(verifier.VerificationError, match=reason):
        verifier.inspect_remote(entry, download=False)


@pytest.fixture
def publisher(verifier, monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'verify_release', verifier)
    return load('handoff_publisher', HANDOFF/'publish_prepared.py')


def test_default_publisher_mode_never_reads_credentials_or_uploads(publisher, monkeypatch):
    calls = []
    monkeypatch.setattr(publisher.verify_release, 'main', lambda argv: calls.append(argv) or 0)

    class NoCredentialAccess:
        def get(self, name):
            pytest.fail('default mode read credentials')

    monkeypatch.setattr(publisher, 'os', SimpleNamespace(environ=NoCredentialAccess()))
    monkeypatch.setattr(publisher, 'subprocess', SimpleNamespace(
        run=lambda *a, **k: pytest.fail('default mode attempted an upload')))
    assert publisher.main([]) == 0
    assert calls == [['--local-only']]


def test_operator_only_upload_path_uses_exact_ordered_files_and_runs_verification(publisher, monkeypatch):
    calls, commands = [], []
    monkeypatch.setattr(publisher.verify_release, 'main', lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(publisher, 'os', SimpleNamespace(environ={'UV_PUBLISH_TOKEN': 'unit-test-only'}))
    monkeypatch.setattr(publisher.shutil, 'which', lambda name: '/unit-test/uv')

    def fake_upload(command, **kwargs):
        commands.append(command)
        assert command[1] == 'publish'
        assert command[command.index('--publish-url')+1] == 'https://upload.pypi.org/legacy/'
        assert 'unit-test-only' not in command
        assert kwargs['env']['UV_PUBLISH_TOKEN'] == 'unit-test-only'
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(publisher, 'subprocess', SimpleNamespace(run=fake_upload))
    assert publisher.main(['--upload-to-pypi']) == 0
    plan = json.loads((HANDOFF/'publication-plan.json').read_text())
    assert [Path(c[-1]).name for c in commands] == [e['wheel'] for e in plan['packages']]
    assert calls[0] == ['--local-only']
    assert calls[1][0] == '--availability'
    assert calls[2][0] == '--published'
