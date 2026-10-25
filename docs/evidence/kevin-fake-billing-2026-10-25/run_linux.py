#!/usr/bin/env python3
"""Transfer only own test inputs and public own WARDEN artifact, then run without external network."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
IMAGE = 'sha256:e1b65057659c168cb8510100daeca2f95d6e3f7ec081ed1b98f217591359b7a3'
WARDEN_SHA = '5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)])


def main():
    execution = HERE / 'execution.json'
    assert not execution.exists(), 'Never replace completed experiment evidence'
    inputs = {'experiment.py': HERE / 'experiment.py', 'billing_backend.py': HERE / 'billing_backend.py',
              'fake-billing-server.mjs': WORKSPACE / 'warden/test/fixtures/fake-billing-server.mjs',
              'histor_observe.py': WORKSPACE / 'histor/sandbox/histor_observe.py',
              'warden-0.21.0.tgz': HERE.parent / 'auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz'}
    assert all(path.is_file() and not path.is_symlink() for path in inputs.values())
    assert sha(inputs['warden-0.21.0.tgz']) == WARDEN_SHA
    manifest = {name: {'sha256': sha(path), 'bytes': path.stat().st_size} for name, path in inputs.items()}
    (HERE / 'input-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = HERE / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, path in inputs.items():
            tar.add(path, arcname=name, recursive=False)
    root = remote(['mktemp', '-d', '/tmp/kevin-fake-billing-20261025.XXXXXX']).decode().strip()
    assert root.startswith('/tmp/kevin-fake-billing-20261025.') and '/' not in root[5:]
    record = {'startedAt': datetime.now(timezone.utc).isoformat(), 'host': 'admin-vps', 'image': IMAGE,
              'runtime': 'runc', 'network': 'none', 'remoteTemp': root,
              'inputArchiveBytes': archive.stat().st_size, 'inputArchiveSha256': sha(archive),
              'inputManifestSha256': sha(HERE / 'input-manifest.json'),
              'workspaceHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKSPACE, text=True).strip(),
              'publicOwnWardenArtifactSha256': WARDEN_SHA, 'realMoneyUsed': False,
              'thirdPartyMcpCodeExecuted': False, 'state': 'prepared'}
    execution.write_text(json.dumps(record, indent=2) + '\n')
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'admin-vps:' + root + '/inputs.tar.gz'], check=True)
    prepare = '''import pathlib,hashlib,tarfile,os,json
root=pathlib.Path(ROOT)
assert hashlib.sha256((root/'inputs.tar.gz').read_bytes()).hexdigest()==SHA
study=root/'study';study.mkdir();out=root/'out';out.mkdir();warden=root/'warden';warden.mkdir()
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 for item in tar.getmembers():
  assert item.isfile() and item.name in MANIFEST
  target=study/item.name;target.write_bytes(tar.extractfile(item).read());target.chmod(0o644)
assert all(hashlib.sha256((study/name).read_bytes()).hexdigest()==meta['sha256'] for name,meta in MANIFEST.items())
with tarfile.open(study/'warden-0.21.0.tgz','r:gz') as tar:
 for item in tar.getmembers():
  path=pathlib.PurePosixPath(item.name)
  assert not path.is_absolute() and '..' not in path.parts and path.parts[0]=='package'
  if item.isdir():continue
  assert item.isfile()
  target=warden/path;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(tar.extractfile(item).read());target.chmod(0o644)
os.chmod(root,0o755);os.chown(out,65532,65532)
print(json.dumps({'verifiedInputFiles':len(MANIFEST),'wardenVersion':json.loads((warden/'package/package.json').read_text())['version']}))
'''.replace('ROOT', repr(root)).replace('SHA', repr(sha(archive))).replace('MANIFEST', repr(manifest))
    record['remoteInputVerification'] = json.loads(remote(['python3', '-c', prepare]))
    base = ['docker', 'run', '--rm', '--runtime', 'runc', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '512m', '--memory-swap', '512m',
            '--cpus', '1', '--pids-limit', '96', '--network', 'none',
            '--tmpfs', '/tmp:rw,nosuid,noexec,size=128m', '--user', '65532:65532',
            '-v', root + '/study:/study:ro', '-v', root + '/warden:/warden:ro',
            '-v', root + '/out:/out:rw', '--workdir', '/study', '--entrypoint', 'python3', IMAGE]

    def run(args, log_name):
        with (HERE / log_name).open('wb') as log:
            child = subprocess.Popen(SSH + [shlex.join(args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for line in child.stdout:
                log.write(line); log.flush()
                print(line.decode(errors='replace')[:1200].rstrip(), flush=True)
            return child.wait()

    self_test = base + ['/study/billing_backend.py', '--self-test']
    record['backendSelfTestCommand'] = self_test
    record['backendSelfTestExitCode'] = run(self_test, 'backend-self-test.log')
    execution.write_text(json.dumps(record, indent=2) + '\n')
    assert record['backendSelfTestExitCode'] == 0
    command = base + ['/study/experiment.py']
    record['experimentCommand'] = command
    execution.write_text(json.dumps(record, indent=2) + '\n')
    record['experimentExitCode'] = run(command, 'linux.log')
    record['finishedAt'] = datetime.now(timezone.utc).isoformat()
    record['state'] = 'executed_not_cleaned'
    execution.write_text(json.dumps(record, indent=2) + '\n')
    pack = '''import pathlib,tarfile,io,sys
out=pathlib.Path(ROOT)/'out';data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as tar:
 for path in sorted(out.rglob('*')):
  if path.is_file():
   assert not path.is_symlink() and path.suffix in ('.json','.jsonl','.txt')
   tar.add(path,arcname=str(path.relative_to(out)),recursive=False)
sys.stdout.buffer.write(data.getvalue())
'''.replace('ROOT', repr(root))
    output_bytes = remote(['python3', '-c', pack])
    (HERE / 'outputs.tar.gz').write_bytes(output_bytes)
    outputs = HERE / 'results'
    outputs.mkdir()
    with tarfile.open(fileobj=io.BytesIO(output_bytes), mode='r:gz') as tar:
        for item in tar.getmembers():
            path = Path(item.name)
            assert item.isfile() and not path.is_absolute() and '..' not in path.parts
            target = outputs / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(item).read())
    checksums = {str(path.relative_to(outputs)): {'sha256': sha(path), 'bytes': path.stat().st_size}
                 for path in sorted(outputs.rglob('*')) if path.is_file()}
    (HERE / 'output-manifest.json').write_text(json.dumps(checksums, indent=2) + '\n')
    print(json.dumps({'outputs': len(checksums), 'experimentExitCode': record['experimentExitCode']}))
    assert record['experimentExitCode'] == 0, 'Preserve failed run evidence; do not clean before investigation'


if __name__ == '__main__':
    main()
