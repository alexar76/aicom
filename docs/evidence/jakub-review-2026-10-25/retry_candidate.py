#!/usr/bin/env python3
"""Complete the existing disposable Linux candidate study, preserving first-run evidence."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
WARDEN = HERE.parents[2] / 'warden'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)], text=True)


def main():
    final = sys.argv[1:] == ['--final']
    assert not sys.argv[1:] or final
    phase = 'final' if final else 'retry'
    original = json.loads((HERE / 'candidate-execution.json').read_text())
    root = original['remoteTemp']
    assert root == '/tmp/jakub-candidate-20261025.xB0Wdi'
    output = HERE / f'candidate-{phase}-execution.json'
    assert not output.exists(), 'Preserve existing retry evidence'
    manifest = json.loads((HERE / ('candidate-retry-source-manifest.json' if final else 'candidate-source-manifest.json')).read_text())
    changed = [name for name, item in manifest.items() if sha(WARDEN / name) != item['sha256']]
    expected_changes = ['src/wrap-state.ts', 'test/review-diff.test.ts', 'test/wrap.test.ts'] if final else ['test/wrap.test.ts']
    assert sorted(changed) == sorted(expected_changes), changed
    inputs = expected_changes if final else ['test/wrap.test.ts', 'vitest.config.ts', 'test/setup.ts',
                                            'test/global-setup.ts', 'examples/atomic-screen-server.mjs']
    assert all((WARDEN / name).is_file() and not (WARDEN / name).is_symlink() for name in inputs)
    current = {**manifest, **{name: {'sha256': sha(WARDEN / name), 'bytes': (WARDEN / name).stat().st_size} for name in inputs}}
    manifest_path = HERE / f'candidate-{phase}-source-manifest.json'
    manifest_path.write_text(json.dumps(current, indent=2) + '\n')
    archive = HERE / f'candidate-{phase}-inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in inputs:
            tar.add(WARDEN / name, arcname=name, recursive=False)
    record = {'kind': original['kind'], 'startedAt': datetime.now(timezone.utc).isoformat(),
              'remoteTemp': root, 'inputFiles': inputs, 'inputBytes': archive.stat().st_size,
              'inputSha256': sha(archive), 'sourceManifestSha256': sha(manifest_path),
              'reason': ('Final bounded metadata Unicode validation and stronger CAS race assertion.' if final else
                         'Restore normal repository test config/setup and own example omitted in initial minimal archive; fix Python test helper process-variable shadowing.')}
    output.write_text(json.dumps(record, indent=2) + '\n')
    remote_archive = phase + '.tar.gz'
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'admin-vps:' + root + '/' + remote_archive], check=True)
    extract = '''import pathlib,hashlib,tarfile,os,json
root=pathlib.Path(ROOT)
assert hashlib.sha256((root/ARCHIVE).read_bytes()).hexdigest()==SHA
with tarfile.open(root/ARCHIVE,'r:gz') as tar:
 for item in tar.getmembers():
  p=pathlib.PurePosixPath(item.name)
  assert item.isfile() and not p.is_absolute() and '..' not in p.parts
  target=root/'project'/p;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(tar.extractfile(item).read());target.chmod(0o644);os.chown(target,65532,65532)
  os.chown(target.parent,65532,65532)
project=root/'project'
expected=MANIFEST
assert all(hashlib.sha256((project/name).read_bytes()).hexdigest()==meta['sha256'] for name,meta in expected.items())
print(json.dumps({'verifiedFiles':len(expected)}))
'''.replace('ROOT', repr(root)).replace('SHA', repr(sha(archive))).replace('MANIFEST', repr(current)).replace('ARCHIVE', repr(remote_archive))
    record['remoteInputVerification'] = json.loads(remote(['python3', '-c', extract]))
    base = original['testCommand']
    record['testCommand'] = base
    output.write_text(json.dumps(record, indent=2) + '\n')
    with (HERE / f'candidate-{phase}-tests.log').open('w') as log:
        child = subprocess.Popen(SSH + [shlex.join(base)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in child.stdout:
            log.write(line); log.flush()
            print(line[:1500].rstrip(), flush=True)
        record['testExitCode'] = child.wait()
    record['finishedAt'] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(record, indent=2) + '\n')
    assert record['testExitCode'] == 0, 'Keep all failed evidence and investigate'
    if final:
        hash_code = '''import pathlib,hashlib,json
p=pathlib.Path(PROJECT)
print(json.dumps({str(f.relative_to(p)):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
for f in sorted((p/'dist').glob('*.js'))},indent=2))
'''.replace('PROJECT', repr(root + '/project'))
        (HERE / 'candidate-final-built-manifest.json').write_text(remote(['python3', '-c', hash_code]) + '\n')


if __name__ == '__main__':
    main()
