#!/usr/bin/env python3
"""Replay archived tool data through the Linux-built local candidate only."""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
OUT = HERE / 'candidate'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)])


def main():
    final = json.loads((HERE / 'candidate-final-execution.json').read_text())
    assert final['testExitCode'] == 0
    root = final['remoteTemp']
    assert root == '/tmp/jakub-candidate-20261025.xB0Wdi'
    state_file = OUT / 'execution.json'
    assert not state_file.exists()
    case = HERE / 'real-cases' / '17172'
    inputs = {'replay.mjs': OUT / 'replay.mjs', 'from-toolsets.json': case / 'from-toolsets.json',
              'to-toolsets.json': case / 'to-toolsets.json', 'change.json': case / 'change.json'}
    assert all(p.is_file() for p in inputs.values()), inputs
    manifest = {name: {'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size} for name, path in inputs.items()}
    archive = OUT / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, path in inputs.items():
            tar.add(path, arcname=name, recursive=False)
    record = {'kind': 'local-unreleased-candidate-real-diff-replay', 'startedAt': datetime.now(timezone.utc).isoformat(),
              'remoteTemp': root, 'inputs': manifest, 'inputArchiveSha256': sha(archive.read_bytes()),
              'sourceManifestSha256': final['sourceManifestSha256'], 'targetExecuted': False}
    state_file.write_text(json.dumps(record, indent=2) + '\n')
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'admin-vps:' + root + '/replay.tar.gz'], check=True)
    prepare = '''import pathlib,hashlib,tarfile,os
root=pathlib.Path(ROOT)
assert hashlib.sha256((root/'replay.tar.gz').read_bytes()).hexdigest()==SHA
study=root/'study';study.mkdir();out=root/'results';out.mkdir();os.chown(out,65532,65532)
with tarfile.open(root/'replay.tar.gz','r:gz') as tar:
 for item in tar.getmembers():
  assert item.isfile() and item.name in INPUTS
  target=study/item.name;target.write_bytes(tar.extractfile(item).read());target.chmod(0o644)
assert all(hashlib.sha256((study/name).read_bytes()).hexdigest()==meta['sha256'] for name,meta in INPUTS.items())
'''.replace('ROOT', repr(root)).replace('SHA', repr(record['inputArchiveSha256'])).replace('INPUTS', repr(manifest))
    remote(['python3', '-c', prepare])
    original = json.loads((HERE / 'candidate-execution.json').read_text())
    command = ['docker', 'run', '--rm', '--runtime', 'runc', '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--memory', '768m', '--cpus', '1', '--pids-limit', '128',
               '--tmpfs', '/tmp:rw,nosuid,noexec,size=128m', '--user', '65532:65532', '--network', 'none',
               '-v', root + '/project:/work:ro', '-v', root + '/study:/study:ro',
               '-v', root + '/results:/out:rw', '--workdir', '/work', '--entrypoint', 'node',
               original['image'], '/study/replay.mjs']
    record['command'] = command
    state_file.write_text(json.dumps(record, indent=2) + '\n')
    child = subprocess.run(SSH + [shlex.join(command)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / 'linux.log').write_bytes(child.stdout)
    record['exitCode'] = child.returncode
    record['finishedAt'] = datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(record, indent=2) + '\n')
    assert child.returncode == 0, child.stdout.decode(errors='replace')[-4000:]
    pack = '''import pathlib,tarfile,io,sys
root=pathlib.Path(ROOT)/'results'
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as tar:
 for path in sorted(root.iterdir()):
  assert path.is_file() and not path.is_symlink()
  assert path.suffix in ('.json','.txt')
  tar.add(path,arcname=path.name,recursive=False)
sys.stdout.buffer.write(data.getvalue())
'''.replace('ROOT', repr(root))
    result_archive = remote(['python3', '-c', pack])
    (OUT / 'outputs.tar.gz').write_bytes(result_archive)
    with tarfile.open(fileobj=io.BytesIO(result_archive), mode='r:gz') as tar:
        for item in tar.getmembers():
            assert item.isfile() and '/' not in item.name and item.name not in ('.', '..')
            (OUT / item.name).write_bytes(tar.extractfile(item).read())
    checksums = {p.name: {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
                 for p in sorted(OUT.iterdir()) if p.suffix in ('.json', '.txt') and p.name != 'checksums.json'}
    (OUT / 'checksums.json').write_text(json.dumps(checksums, indent=2) + '\n')
    result = json.loads((OUT / 'result.json').read_text())
    print(json.dumps({'assertions': result['assertions'], 'targetExecuted': result['targetExecuted'],
                      'result': str(OUT / 'result.json')}, indent=2))
    assert result['assertions']['failed'] == 0


if __name__ == '__main__':
    main()
