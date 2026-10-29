#!/usr/bin/env python3
"""Read-only local/PyPI verification. This tool never uploads or reads credentials."""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import email
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
MAX_BYTES = 25_000_000
ALLOWED_HOSTS = {'pypi.org', 'files.pythonhosted.org'}


class VerificationError(Exception):
    pass


def normalized(value):
    return re.sub(r'[-_.]+', '-', value).lower()


def checked_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise VerificationError('unexpected_download_origin')
    return url


class SafeRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    request = urllib.request.Request(checked_url(url), headers={
        'User-Agent': 'alexar76-security-release-verifier/1',
    })
    with urllib.request.build_opener(SafeRedirects()).open(request, timeout=30) as response:
        checked_url(response.geturl())
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise VerificationError('response_exceeds_limit')
    return raw


def inspect_wheel(raw, entry):
    if len(raw) != entry['size'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise VerificationError('wheel_bytes_differ_from_audited_build')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise VerificationError('duplicate_archive_member')
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1):
                raise VerificationError('unsafe_archive_member')
        metadata_names = [n for n in names if n.endswith('.dist-info/METADATA')]
        if len(metadata_names) != 1:
            raise VerificationError('invalid_wheel_metadata_count')
        metadata = email.message_from_bytes(archive.read(metadata_names[0]))
        if (normalized(metadata['Name']) != normalized(entry['package'])
                or metadata['Version'] != entry['version']
                or metadata['Requires-Python'] != entry['requires_python']):
            raise VerificationError('wheel_identity_mismatch')
        if 'Private :: Do Not Upload' in metadata.get_all('Classifier', []):
            raise VerificationError('distribution_marked_private')
        actual_python = {n for n in names if n.endswith('.py') and '.dist-info/' not in n}
        if actual_python != set(entry['python_sha256']):
            raise VerificationError('python_member_set_mismatch')
        for name, expected in entry['python_sha256'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise VerificationError('packaged_source_mismatch')
        if not set(entry['required_fix_members']).issubset(actual_python):
            raise VerificationError('required_fix_module_missing')
        records = [n for n in names if n.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise VerificationError('invalid_record_count')
        checked = set()
        for name, digest, size in csv.reader(io.StringIO(archive.read(records[0]).decode())):
            if name not in names or name in checked:
                raise VerificationError('invalid_record_member')
            checked.add(name)
            if not digest:
                if name != records[0]:
                    raise VerificationError('unhashed_record_member')
                continue
            algorithm, encoded = digest.split('=', 1)
            if algorithm != 'sha256':
                raise VerificationError('unexpected_record_algorithm')
            content = archive.read(name)
            actual = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b'=').decode()
            if actual != encoded or len(content) != int(size):
                raise VerificationError('record_integrity_mismatch')
        if checked != {n for n in names if not n.endswith('/')}:
            raise VerificationError('record_does_not_cover_wheel')
    return {'python_files_verified': len(actual_python), 'record_entries_verified': len(checked) - 1,
            'all_required_fix_modules_present': True, 'identical_to_audited_build': True}


def local_preflight(plan, directory=HERE):
    expected = {entry['wheel'] for entry in plan['packages']}
    if {p.name for p in (directory/'wheels').glob('*.whl')} != expected:
        raise VerificationError('local_wheel_set_mismatch')
    return [dict(package=entry['package'], version=entry['version'], status='local_verified',
                 **inspect_wheel((directory/'wheels'/entry['wheel']).read_bytes(), entry))
            for entry in plan['packages']]


def inspect_remote(entry, *, download):
    url = 'https://pypi.org/pypi/' + entry['package'] + '/' + entry['version'] + '/json'
    try:
        metadata = json.loads(fetch(url))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {'package': entry['package'], 'version': entry['version'],
                    'status': 'not_published' if download else 'available_for_new_release'}
        raise
    if (normalized(metadata['info']['name']) != normalized(entry['package'])
            or metadata['info']['version'] != entry['version']):
        raise VerificationError('registry_identity_mismatch')
    wheels = [f for f in metadata['urls'] if f['filename'].endswith('.whl')]
    if {f['filename'] for f in wheels} != {entry['wheel']}:
        raise VerificationError('release_contains_missing_or_unreviewed_wheels')
    matches = [f for f in wheels if f['filename'] == entry['wheel']]
    if len(matches) != 1:
        raise VerificationError('expected_wheel_missing_or_conflicting_release')
    wheel = matches[0]
    if wheel.get('yanked'):
        raise VerificationError('published_wheel_is_yanked')
    if wheel['digests']['sha256'] != entry['sha256'] or wheel['size'] != entry['size']:
        raise VerificationError('published_wheel_conflicts_with_prepared_build')
    result = {'package': entry['package'], 'version': entry['version'],
              'status': 'published_verified' if download else 'already_present_metadata_matches',
              'wheel_url': checked_url(wheel['url']), 'sha256': entry['sha256'],
              'uploaded_at': wheel.get('upload_time_iso_8601')}
    if download:
        result.update(inspect_wheel(fetch(wheel['url']), entry))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--local-only', action='store_true', help='default: inspect only the prepared local files')
    mode.add_argument('--availability', action='store_true', help='GET PyPI metadata to detect occupied versions; no uploads')
    mode.add_argument('--published', action='store_true', help='after publication: GET and inspect all eight exact-version wheels')
    parser.add_argument('--report', type=Path, help='write the verification result as JSON')
    args = parser.parse_args(argv)
    plan = json.loads((HERE/'publication-plan.json').read_text())
    if len(plan['packages']) != 8:
        raise VerificationError('expected_eight_packages')
    local = local_preflight(plan)
    rows = local
    if args.availability or args.published:
        rows = []
        for entry in plan['packages']:
            try:
                rows.append(inspect_remote(entry, download=args.published))
            except Exception as exc:
                rows.append({'package': entry['package'], 'version': entry['version'],
                             'status': 'error', 'reason': str(exc) if isinstance(exc, VerificationError) else type(exc).__name__})
    good = {'published_verified'} if args.published else {'local_verified', 'available_for_new_release', 'already_present_metadata_matches'}
    passed = all(row['status'] in good for row in rows)
    result = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'mode': 'published' if args.published else 'availability' if args.availability else 'local',
              'source_commit': plan['source_commit'], 'passed': passed,
              'uploads_performed': 0, 'credentials_read': False, 'packages': rows}
    if args.report:
        args.report.write_text(json.dumps(result, indent=2)+'\n')
    for row in rows:
        print(row['package']+'=='+row['version']+': '+row['status'])
    print('PASS' if passed else 'INCOMPLETE_OR_FAILED')
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print('Verification failed: '+str(exc), file=sys.stderr)
        raise SystemExit(2)
