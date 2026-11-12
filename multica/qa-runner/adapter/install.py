#!/usr/bin/env python3
"""Install the fixed QA capability infrastructure after source publication and coordinator GO. Never restart the daemon."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
SHA256 = '29509c61405856b8ba7b055301009fa7ddb846fb9d75cf5e3c98bf8f823fd898'

def package_files(package, expected_sha256=SHA256):
    if hashlib.sha256(package.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('reviewed WARDEN archive hash mismatch')
    result = {}
    with tarfile.open(package, 'r:gz') as archive:
        for item in archive:
            parts = Path(item.name).parts
            if not parts or parts[0] != 'package' or '..' in parts or item.name.startswith('/') or item.issym() or item.islnk():
                raise ValueError('unsafe package member')
            if item.isdir():
                continue
            if not item.isfile() or item.size > 3_000_000:
                raise ValueError('unsafe package file')
            name = str(Path(*parts[1:]))
            if name in result:
                raise ValueError('duplicate package file')
            result[name] = archive.extractfile(item).read()
    if not {'package.json', 'dist/mcp-server.js', 'dist/task-adapter.js', 'dist/task-cli.js', 'dist/jcs.js', 'dist/sanitize.js'} <= result.keys():
        raise ValueError('full compiled WARDEN package is incomplete')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--ca', type=Path, required=True, help='public CA certificate only, never a private key')
    parser.add_argument('--guard-root', type=Path, default=Path('/opt/multica/opencode-guard'))
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/docker/volumes/multica_daemon_home/_data/.local/state/warden'))
    parser.add_argument('--unit-dir', type=Path, default=Path('/etc/systemd/system'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--go', action='store_true')
    args = parser.parse_args()
    if args.apply and (not args.go or os.geteuid() != 0):
        parser.error('live installation requires root and explicit coordinator --go after source publication')
    files = package_files(args.package)
    ca = args.ca.read_text()
    if 'PRIVATE KEY' in ca:
        raise ValueError('only public CA material may enter the adapter')
    ssl.PEM_cert_to_DER_cert(ca)
    report = {'applied': args.apply, 'archiveSha256': SHA256, 'packageFiles': len(files), 'secretsInstalled': False,
              'globalMcpEnabled': False, 'requiresPrivateQaProfile': True, 'daemonRestarted': False, 'sessionStateReset': False}
    if not args.apply:
        print(json.dumps(report, indent=2)); return
    for parent in (args.guard_root, args.unit_dir):
        info = parent.lstat()
        if parent.is_symlink() or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
            raise ValueError('unprotected installation directory')
    target = args.guard_root / 'qa-adapter'
    if target.exists():
        info = target.lstat()
        if target.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('unprotected adapter directory')
    target.mkdir(mode=0o755, exist_ok=True)
    target.chmod(0o755)
    private = target / 'private'; private.mkdir(mode=0o700, exist_ok=True)
    if private.is_symlink() or private.stat().st_uid != 0 or stat.S_IMODE(private.stat().st_mode) != 0o700:
        raise ValueError('unprotected lease metadata directory')
    stage = Path(tempfile.mkdtemp(prefix='.qa-warden-', dir=target))
    try:
        for name, content in files.items():
            path = stage / name; path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            path.write_bytes(content); path.chmod(0o644)
        for path in stage.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
        stage.chmod(0o755)
        installed = target / 'warden'
        if installed.exists():
            # A package replacement while the adapter runs could mix modules. Identical installs are idempotent only.
            if any(not (installed / name).is_file() or hashlib.sha256((installed / name).read_bytes()).digest() != hashlib.sha256(data).digest() for name, data in files.items()):
                raise ValueError('existing package differs; stop the private QA adapter and review a separate upgrade')
        else:
            os.rename(stage, installed)
        (target / 'ca.crt').write_text(ca); (target / 'ca.crt').chmod(0o644)
        shutil.copyfile(HERE / 'renew-lease.py', target / 'renew-lease.py'); (target / 'renew-lease.py').chmod(0o755)
        fragments = target / 'fragments'; fragments.mkdir(mode=0o755, exist_ok=True)
        fragments.chmod(0o755)
        for source in (HERE / 'fragments').glob('*.json'):
            shutil.copyfile(source, fragments / source.name); (fragments / source.name).chmod(0o644)
        for source in (HERE / 'systemd').iterdir():
            shutil.copyfile(source, args.unit_dir / source.name); (args.unit_dir / source.name).chmod(0o644)
        spec = importlib.util.spec_from_file_location('qa_lease', target / 'renew-lease.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        report['lease'] = module.renew(args.state_dir, args.guard_root / 'flow-policy.json', private, __import__('time').time(), True)
        report['nextSteps'] = ['Merge disabled global MCP fragment without replacing other OpenCode configuration.',
                               'Set WARDEN_FLOW_POLICY=/opt/opencode-guard/flow-policy.json for the OpenCode guard process too.',
                               'Enable the MCP override only for the new private QA agent profile.',
                               'After broker/worker acceptance: systemctl daemon-reload; systemctl enable --now multica-qa-lease.timer']
        print(json.dumps(report, indent=2))
    finally:
        if stage.exists():
            shutil.rmtree(stage)

if __name__ == '__main__':
    main()
