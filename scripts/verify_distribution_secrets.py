#!/usr/bin/env python3
"""Inspect wheel/sdist contents without extracting or executing package files."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
import tarfile
import zipfile
from dataclasses import asdict

# Also works under Python -I: this directory is trusted release tooling, not
# the current package directory or a member of the candidate archive.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_structured_secrets import _scan_stream  # noqa: E402

MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 50_000


def _check_member(name: str, size: int, total: int) -> int:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or PureWindowsPath(name).drive or '..' in path.parts or '\\' in name:
        raise ValueError('unsafe archive member')
    if size < 0 or size > MAX_MEMBER_BYTES or total + size > MAX_TOTAL_BYTES:
        raise ValueError('archive exceeds inspection limits')
    return total + size


def _inspect_member(name: str, source) -> list[dict]:
    if PurePosixPath(name).name != '_signing_key_storage.py':
        return [asdict(row) for row in _scan_stream(name, source, export_policy=True)]
    # The filename exception in the release name gate is reserved for the exact
    # current storage implementation. Other source, or a key renamed as source,
    # cannot inherit that exception. Do not execute candidate Python code.
    body = source.read(1_048_577)
    if len(body) > 1_048_576:
        raise ValueError('storage helper exceeds inspection limit')
    rows = [asdict(row) for row in _scan_stream(name, io.BytesIO(body), export_policy=True)]
    trusted = Path(__file__).resolve().parents[1] / 'security' / 'signing_key_storage.py'
    if hashlib.sha256(body).digest() != hashlib.sha256(trusted.read_bytes()).digest():
        rows.append({'path': name, 'kind': 'unexpected-signing-storage-module',
                     'sha256': hashlib.sha256(body).hexdigest()})
    return rows


def scan_archive(path: Path) -> list[dict]:
    findings = []
    total = 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS:
                raise ValueError('too many archive members')
            for member in members:
                total = _check_member(member.filename, member.file_size, total)
                mode = member.external_attr >> 16
                is_directory = member.is_dir()
                allowed_modes = (0, stat.S_IFDIR) if is_directory else (0, stat.S_IFREG)
                if stat.S_IFMT(mode) not in allowed_modes or member.flag_bits & 1:
                    raise ValueError('linked or encrypted archive member')
                if is_directory:
                    if member.file_size:
                        raise ValueError('archive directory contains payload')
                    continue
                with archive.open(member) as source:
                    findings.extend(_inspect_member(member.filename, source))
    else:
        with tarfile.open(path, 'r:*') as archive:
            for count, member in enumerate(archive, 1):
                if count > MAX_MEMBERS:
                    raise ValueError('too many archive members')
                total = _check_member(member.name, member.size, total)
                if member.isdir():
                    if member.size:
                        raise ValueError('archive directory contains payload')
                    continue
                if not member.isfile():
                    raise ValueError('linked or special archive member')
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('unreadable archive member')
                with source:
                    findings.extend(_inspect_member(member.name, source))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args(argv)
    try:
        findings = scan_archive(args.archive)
    except Exception as exc:
        # Archive/parser diagnostics can reproduce package bytes and credentials.
        print(f'error: distribution secret inspection failed ({type(exc).__name__})', file=sys.stderr)
        return 2
    if findings:
        print(json.dumps({'distribution_secret_findings': findings}, sort_keys=True))
        return 1
    print('OK distribution contents inspected')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
