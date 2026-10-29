#!/usr/bin/env python3
"""Audit saved measurement data and own harness code on Linux, with no model or network calls."""
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
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']


def remote(args, data=None):
    return subprocess.check_output(SSH + [shlex.join(args)], input=data)


def main():
    state = HERE / 'execution.json'
    assert not state.exists()
    files = {name: HERE / name for name in ('audit_answers.py', 'test_scoring_contract.py', 'test_finish_capture.py', 'probe_stop.mjs')}
    files['model.py'] = WORKSPACE / 'warden/scripts/agentdojo/model.py'
    files['saved-answers.jsonl.gz'] = WORKSPACE / 'warden/scripts/agentdojo/results/model-answer-recheck-2026-10-22.jsonl.gz'
    files['warden.tgz'] = HERE.parent / 'auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz'
    data = {name: path.read_bytes() for name, path in files.items()}
    assert hashlib.sha256(data['warden.tgz']).hexdigest() == '5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
    manifest = {name: {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)} for name, body in data.items()}
    (HERE / 'input-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = HERE / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, body in data.items():
            item = tarfile.TarInfo(name); item.size = len(body); item.mode = 0o644
            tar.addfile(item, io.BytesIO(body))
    root = remote(['mktemp', '-d', '/tmp/launchgate-audit-20261025.XXXXXX']).decode().strip()
    assert root.startswith('/tmp/launchgate-audit-20261025.') and '/' not in root[5:]
    record = {'startedAt': datetime.now(timezone.utc).isoformat(), 'remoteTemp': root, 'image': IMAGE,
              'runtime': 'runc', 'network': 'none', 'modelCalls': 0, 'inputs': manifest}
    state.write_text(json.dumps(record, indent=2) + '\n')
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'admin-vps:' + root + '/inputs.tar.gz'], check=True)
    prepare = '''import pathlib,hashlib,tarfile,os
root=pathlib.Path(ROOT);study=root/'study';study.mkdir();out=root/'out';out.mkdir();warden=root/'warden';warden.mkdir()
manifest=MANIFEST
with tarfile.open(root/'inputs.tar.gz','r:gz') as tar:
 for item in tar.getmembers():
  assert item.isfile() and item.name in manifest
  body=tar.extractfile(item).read();assert hashlib.sha256(body).hexdigest()==manifest[item.name]['sha256']
  target=study/item.name;target.write_bytes(body);target.chmod(0o644)
with tarfile.open(study/'warden.tgz','r:gz') as tar:
 for item in tar.getmembers():
  p=pathlib.PurePosixPath(item.name);assert not p.is_absolute() and '..' not in p.parts and p.parts[0]=='package'
  if item.isdir():continue
  assert item.isfile();target=warden/p;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(tar.extractfile(item).read());target.chmod(0o644)
os.chmod(root,0o755);os.chown(out,65532,65532)
'''.replace('ROOT', repr(root)).replace('MANIFEST', repr(manifest))
    remote(['python3', '-'], prepare.encode())
    base = ['docker', 'run', '--rm', '--runtime', 'runc', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '512m', '--cpus', '1', '--pids-limit', '96',
            '--network', 'none', '--tmpfs', '/tmp:rw,nosuid,noexec,size=128m', '--user', '65532:65532',
            '-v', root + '/study:/study:ro', '-v', root + '/warden:/warden:ro', '-v', root + '/out:/out:rw',
            '--workdir', '/study', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'WARDEN_MODEL_SOURCE=/study/model.py']
    commands = [base + ['--entrypoint', 'python3', IMAGE, '-m', 'unittest', '-v', 'test_scoring_contract.py', 'test_finish_capture.py'],
                base + ['--entrypoint', 'python3', IMAGE, '/study/audit_answers.py', '/study/saved-answers.jsonl.gz', '--out', '/out/saved-answer-audit.json'],
                base + ['--entrypoint', 'node', IMAGE, '/study/probe_stop.mjs', '/warden/package', '/out/published-stop-observations.json']]
    record['commands'] = commands
    codes = []
    for index, command in enumerate(commands):
        result = subprocess.run(SSH + [shlex.join(command)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (HERE / f'linux-{index + 1}.log').write_bytes(result.stdout)
        codes.append(result.returncode)
        print(result.stdout.decode(errors='replace')[-2500:], flush=True)
    record.update({'exitCodes': codes, 'finishedAt': datetime.now(timezone.utc).isoformat()})
    state.write_text(json.dumps(record, indent=2) + '\n')
    pack = '''import pathlib,io,tarfile,sys
out=pathlib.Path(ROOT)/'out';buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
 for p in sorted(out.iterdir()):
  assert p.is_file() and not p.is_symlink() and p.suffix=='.json'
  tar.add(p,arcname=p.name,recursive=False)
sys.stdout.buffer.write(buffer.getvalue())
'''.replace('ROOT', repr(root))
    outputs = remote(['python3', '-'], pack.encode())
    (HERE / 'outputs.tar.gz').write_bytes(outputs)
    with tarfile.open(fileobj=io.BytesIO(outputs), mode='r:gz') as tar:
        for item in tar.getmembers():
            assert item.isfile() and '/' not in item.name and item.name not in ('.', '..')
            (HERE / item.name).write_bytes(tar.extractfile(item).read())
    assert not any(codes), 'Preserve failure evidence before cleanup'


if __name__ == '__main__':
    main()
