"""Release archives must not hide a signing key behind a Python filename."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'verify_distribution_secrets.py'
spec = importlib.util.spec_from_file_location('distribution_guard', SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def _archive(tmp_path, kind, name, data):
    target = tmp_path / ('package.whl' if kind == 'wheel' else 'package.tar.gz')
    if kind == 'wheel':
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name, data)
    else:
        with tarfile.open(target, 'w:gz') as archive:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return target


def _run(path):
    return subprocess.run([sys.executable, '-I', str(SCRIPT), str(path)], text=True, capture_output=True)


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_private_key_disguised_as_storage_module_is_refused_without_value(tmp_path, kind):
    seed = bytes(range(32))
    raw = seed + Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    target = _archive(tmp_path, kind, 'package/_signing_key_storage.py', raw)
    result = _run(target)
    assert result.returncode == 1
    rows = json.loads(result.stdout)['distribution_secret_findings']
    assert rows[0]['sha256'] == hashlib.sha256(raw).hexdigest()
    assert 'raw-ed25519-keypair' in result.stdout
    assert seed.hex() not in result.stdout + result.stderr
    assert raw.hex() not in result.stdout + result.stderr


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_archive_source_is_inspected_as_data_and_never_executed(tmp_path, kind):
    canary = tmp_path / 'must-not-exist'
    source = f'from pathlib import Path\nPath({str(canary)!r}).touch()\n'.encode()
    result = _run(_archive(tmp_path, kind, 'package/source.py', source))
    assert result.returncode == 0
    assert not canary.exists()


def test_innocently_named_archive_member_with_api_credential_is_refused(tmp_path):
    canary = 'sk-' + 'Q8nS9d' * 8
    result = _run(_archive(tmp_path, 'wheel', 'package/notes.txt', canary.encode()))
    assert result.returncode == 1
    assert 'api-token-literal' in result.stdout
    assert canary not in result.stdout + result.stderr


@pytest.mark.parametrize('member', ['../../outside.py', '/absolute.py', 'C:/absolute.py', 'C:relative.py', 'package/../escape.py', 'package\\escape.py'])
def test_unsafe_member_names_fail_closed_without_extraction(tmp_path, member):
    result = _run(_archive(tmp_path, 'sdist', member, b'safe text'))
    assert result.returncode == 2
    assert result.stdout == ''


def test_symlink_archive_member_is_never_followed(tmp_path):
    target = tmp_path / 'package.whl'
    with zipfile.ZipFile(target, 'w') as archive:
        member = zipfile.ZipInfo('package/_signing_key_storage.py')
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, '/private/outside-key')
    assert _run(target).returncode == 2


def test_decompression_limits_fail_closed(tmp_path, monkeypatch):
    target = _archive(tmp_path, 'wheel', 'package/data.txt', b'A' * 1000)
    monkeypatch.setattr(guard, 'MAX_MEMBER_BYTES', 100)
    with pytest.raises(ValueError, match='limits'):
        guard.scan_archive(target)


def test_release_script_checks_contents_before_upload_or_dry_run_success():
    source = SCRIPT.with_name('publish_pypi.sh').read_text()
    scan = source.index('"$ROOT/scripts/verify_distribution_secrets.py"')
    dry_run = source.index('if [[ "$DRY_RUN" -eq 1 ]]', scan)
    upload = source.index('twine upload', dry_run)
    assert scan < dry_run < upload


def test_only_exact_current_storage_helper_can_receive_filename_exception(tmp_path):
    trusted = (SCRIPT.parents[1] / 'security' / 'signing_key_storage.py').read_bytes()
    assert _run(_archive(tmp_path, 'wheel', 'package/_signing_key_storage.py', trusted)).returncode == 0
    result = _run(_archive(tmp_path, 'wheel', 'package/_signing_key_storage.py', trusted + b'\n# altered\n'))
    assert result.returncode == 1
    assert 'unexpected-signing-storage-module' in result.stdout


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_directory_payload_cannot_hide_secret_bytes(tmp_path, kind):
    if kind == 'wheel':
        target = _archive(tmp_path, kind, 'package/directory/', b'concealed bytes')
    else:
        target = tmp_path / 'package.tar.gz'
        with tarfile.open(target, 'w:gz') as archive:
            member = tarfile.TarInfo('package/directory/')
            member.type = tarfile.DIRTYPE
            member.size = len(b'concealed bytes')
            archive.addfile(member, io.BytesIO(b'concealed bytes'))
    assert _run(target).returncode == 2


def test_trailing_slash_cannot_hide_zip_symlink_type(tmp_path):
    target = tmp_path / 'package.whl'
    with zipfile.ZipFile(target, 'w') as archive:
        member = zipfile.ZipInfo('package/innocent/')
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, b'')
    assert _run(target).returncode == 2
