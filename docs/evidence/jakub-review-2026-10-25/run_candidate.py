#!/usr/bin/env python3
"""Build/test only the local WARDEN candidate on Linux; no external MCP package runs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
WARDEN = WORKSPACE / 'warden'
IMAGE = 'sha256:e1b65057659c168cb8510100daeca2f95d6e3f7ec081ed1b98f217591359b7a3'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']
TESTS = ['test/review-diff.test.ts', 'test/pin-review-origin.test.ts',
         'test/wrap.test.ts', 'test/persistent-pins.test.ts']


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)], text=True)


def stream(args, name):
    with (HERE / name).open('w') as handle:
        child = subprocess.Popen(SSH + [shlex.join(args)], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
        for line in child.stdout:
            handle.write(line); handle.flush()
            print(line[:1500].rstrip(), flush=True)
        code = child.wait()
    return code


def main():
    state_file = HERE / 'candidate-execution.json'
    assert not state_file.exists(), 'Preserve prior run evidence'
    files = sorted(WARDEN.joinpath('src').rglob('*.ts'))
    files += [WARDEN / name for name in ('package.json', 'package-lock.json', 'tsconfig.json', *TESTS)]
    files += sorted(WARDEN.joinpath('test/fixtures').rglob('*.mjs'))
    assert all(p.is_file() and not p.is_symlink() for p in files)
    source = {str(p.relative_to(WARDEN)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files}
    (HERE / 'candidate-source-manifest.json').write_text(json.dumps(source, indent=2) + '\n')
    archive = HERE / 'candidate-test-inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(WARDEN)), recursive=False)
    root = remote(['mktemp', '-d', '/tmp/jakub-candidate-20261025.XXXXXX']).strip()
    assert root.startswith('/tmp/jakub-candidate-20261025.') and '/' not in root[5:]
    record = {'kind': 'local-unreleased-candidate-not-published-0.21.0', 'startedAt': now(),
              'host': 'admin-vps', 'image': IMAGE, 'remoteTemp': root,
              'transferredFiles': len(files), 'inputArchiveBytes': archive.stat().st_size,
              'inputArchiveSha256': sha(archive), 'sourceManifestSha256': sha(HERE / 'candidate-source-manifest.json'),
              'externalMcpPackagesExecuted': False, 'state': 'prepared'}

    def save():
        state_file.write_text(json.dumps(record, indent=2) + '\n')

    save()
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'admin-vps:' + root + '/inputs.tar.gz'], check=True)
    prepare = '''import hashlib,pathlib,tarfile,os
root=pathlib.Path(ROOT)
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==SHA
project=root/'project'; project.mkdir()
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 for item in tar.getmembers():
  path=pathlib.PurePosixPath(item.name)
  assert item.isfile() and not path.is_absolute() and '..' not in path.parts
  target=project/path; target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(tar.extractfile(item).read()); target.chmod(0o644)
for folder,dirs,files in os.walk(root):
 os.chown(folder,65532,65532);os.chmod(folder,0o755)
 for name in files:os.chown(pathlib.Path(folder)/name,65532,65532)
'''.replace('ROOT', repr(root)).replace('SHA', repr(sha(archive)))
    remote(['python3', '-c', prepare])
    base = ['docker', 'run', '--rm', '--runtime', 'runc', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '768m', '--cpus', '1', '--pids-limit', '128',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=256m', '--user', '65532:65532',
            '-v', root + '/project:/work:rw', '--workdir', '/work']
    # Preparation may download only lockfile-pinned development dependencies; lifecycle scripts disabled.
    setup = base + ['--network', 'bridge', '--entrypoint', 'npm', IMAGE,
                    'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', '/tmp/npm-cache']
    record['setupCommand'] = setup; save()
    assert stream(setup, 'candidate-setup.log') == 0, 'Dependency setup failed'
    build = base + ['--network', 'none', '--entrypoint', 'node', IMAGE,
                    'node_modules/typescript/bin/tsc', '-p', 'tsconfig.json']
    record['buildCommand'] = build; save()
    assert stream(build, 'candidate-build.log') == 0, 'TypeScript build failed'
    test = base + ['--network', 'none', '--entrypoint', 'node', IMAGE,
                   'node_modules/vitest/vitest.mjs', 'run', *TESTS, '--maxWorkers=1', '--no-file-parallelism']
    record['testCommand'] = test; save()
    code = stream(test, 'candidate-tests.log')
    record.update({'testExitCode': code, 'finishedAt': now(), 'state': 'tested_not_cleaned'})
    save()
    # Hash compiled artifacts on Linux; only metadata returns to the workspace.
    hash_code = '''import pathlib,hashlib,json
p=pathlib.Path(PROJECT)
print(json.dumps({str(f.relative_to(p)):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
for f in sorted((p/'dist').glob('*.js'))},indent=2))
'''.replace('PROJECT', repr(root + '/project'))
    (HERE / 'candidate-built-manifest.json').write_text(remote(['python3', '-c', hash_code]) + '\n')
    if code:
        raise RuntimeError('Candidate tests failed; preserve remote study for investigation')
    print('Candidate tests passed; preserve temporary project until final checks/cleanup.', flush=True)


if __name__ == '__main__':
    main()
