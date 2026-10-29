"""Run only the reason evaluator and its tests in a networkless Linux container."""
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOST = 'factory-vps'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', HOST]
IMAGE = 'sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'


def remote(script):
    return subprocess.check_output(SSH + ['python3 -'], input=script.encode())


def main():
    source = ROOT / 'warden/scripts/selection-probe'
    data = {name: (source / name).read_bytes() for name in ('reason_audit.py', 'test_reason_audit.py')}
    data.update({name: (HERE / name).read_bytes() for name in ('pairs.json', 'annotations.json')})
    manifest = {name: sha256(body).hexdigest() for name, body in data.items()}
    (HERE / 'input-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = HERE / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, body in data.items():
            member = tarfile.TarInfo(name); member.size = len(body); member.mode = 0o644
            tar.addfile(member, io.BytesIO(body))
    root = remote('import tempfile; print(tempfile.mkdtemp(prefix="warden-reason-audit-",dir="/tmp"))').decode().strip()
    assert re.fullmatch(r'/tmp/warden-reason-audit-[A-Za-z0-9_]+', root)
    receipt = {'host': HOST, 'image': IMAGE, 'runtime': 'runc', 'network': 'none', 'sourceFiles': len(data), 'archiveBytes': archive.stat().st_size,
               'inputHashes': manifest, 'archiveSha256': sha256(archive.read_bytes()).hexdigest(), 'remoteTemp': root,
               'startedAt': datetime.now(timezone.utc).isoformat(), 'newModelCalls': 0, 'githubWrites': False, 'npmPublished': False}
    try:
        subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), HOST + ':' + root + '/inputs.tgz'], check=True)
        setup = 'import pathlib,tarfile,hashlib,os; root=pathlib.Path(' + repr(root) + '); manifest=' + repr(manifest) + '\n'
        setup += 'with tarfile.open(root/"inputs.tgz") as tar:\n for member in tar.getmembers():\n  assert member.isfile() and member.name in manifest\n  body=tar.extractfile(member).read(); assert hashlib.sha256(body).hexdigest()==manifest[member.name]\n  (root/member.name).write_bytes(body); (root/member.name).chmod(0o644)\n'
        setup += 'out=root/"result"; out.mkdir(); os.chown(out,65532,65532); root.chmod(0o755)\n'
        remote(setup)
        script = 'cd /study && python3 -B -m unittest -v test_reason_audit && python3 -B reason_audit.py --pairs pairs.json --annotations annotations.json --out /result/results.json'
        command = ['docker', 'run', '--rm', '--runtime', 'runc', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--memory', '256m', '--cpus', '1', '--pids-limit', '64', '--user', '65532:65532', '--tmpfs', '/tmp:rw,nosuid,noexec,size=32m',
                   '-v', root + ':/study:ro', '-v', root + '/result:/result:rw', '--entrypoint', 'sh', IMAGE, '-c', script]
        process = subprocess.run(SSH + [shlex.join(command)], capture_output=True)
        log = process.stdout + process.stderr
        (HERE / 'tests.log').write_bytes(log)
        receipt.update(exitCode=process.returncode, command=command, testsLogSha256=sha256(log).hexdigest())
        if process.returncode:
            print(log.decode(errors='replace')[-6000:])
        else:
            result = remote('from pathlib import Path; import sys; sys.stdout.buffer.write(Path(' + repr(root + '/result/results.json') + ').read_bytes())')
            (HERE / 'results.json').write_bytes(result)
            receipt['resultSha256'] = sha256(result).hexdigest()
            print(json.dumps(json.loads(result)['summary']))
        assert process.returncode == 0, 'Linux tests/audit failed; preserve the log'
    finally:
        receipt['cleanup'] = json.loads(remote('import pathlib,shutil,json; p=pathlib.Path(' + repr(root) + '); shutil.rmtree(p); print(json.dumps({"removed":str(p),"absent":not p.exists()}))'))
        receipt['finishedAt'] = datetime.now(timezone.utc).isoformat()
        (HERE / 'execution.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
