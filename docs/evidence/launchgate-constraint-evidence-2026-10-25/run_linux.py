"""Freeze minimal WARDEN build/tests, validate on Linux, replay, collect and clean."""
from datetime import datetime, timezone
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'factory-vps']
IMAGE = 'sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
TESTS = ['action', 'annotation-review', 'claude-plugin', 'flow-guard-answer-review', 'flow-guard-constraints', 'flow-guard-credential-boundary', 'flow-guard-gaps', 'flow-guard-gautam', 'flow-guard-gui-policy', 'flow-guard-home-paths', 'flow-guard-instructions', 'flow-guard-screen', 'flow-guard-secret-regression', 'flow-guard', 'mcp-client', 'pin-review-origin', 'result-screen', 'review-diff', 'toxic-flow', 'wrap-screen', 'wrap']


def remote(script):
    return subprocess.check_output(SSH + ['python3 -'], input=script.encode())


def freeze(state):
    previous = json.loads((HERE.parent / 'launchgate-live-comparison-2026-10-25/run-02/input-manifest.json').read_text())
    data = {}
    for name in previous:
        if name.startswith('project/'):
            source = ROOT / 'warden' / name.removeprefix('project/')
            assert source.is_file() and not source.is_symlink()
            data[name] = source.read_bytes()
    for name in ['src/flow-guard-constraints.ts', 'test/flow-guard-constraints.test.ts']:
        data['project/' + name] = (ROOT / 'warden' / name).read_bytes()
    for name in ['constraint_claims.py', 'test_constraint_claims.py', 'reason_audit.py', 'test_reason_audit.py']:
        data['research/' + name] = (ROOT / 'warden/scripts/selection-probe' / name).read_bytes()
    for name in ['build_cases.py', 'replay.mjs']:
        data['research/' + name] = (HERE / name).read_bytes()
    for name, origin in [('pairs.json', 'pairs.json'), ('gold.json', 'results.json')]:
        data['research/' + name] = (HERE.parent / 'launchgate-reason-audit-2026-10-25' / origin).read_bytes()
    manifest = {name: {'sha256': sha256(body).hexdigest(), 'bytes': len(body)} for name, body in data.items()}
    (state / 'input-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = state / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, body in data.items():
            member = tarfile.TarInfo(name); member.size = len(body); member.mode = 0o644
            tar.addfile(member, io.BytesIO(body))
    return archive, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='run-01')
    args = parser.parse_args()
    assert re.fullmatch(r'run-[0-9]{2}', args.run)
    state = HERE / args.run; state.mkdir(exist_ok=True)
    assert not (state / 'execution.json').exists(), 'Keep prior attempts; choose a new run directory after repair.'
    archive, manifest = freeze(state)
    receipt = {'host': 'factory-vps', 'image': IMAGE, 'runtime': 'runc', 'runtimeNetwork': 'none', 'inputFiles': len(manifest), 'archiveBytes': archive.stat().st_size,
               'archiveSha256': sha256(archive.read_bytes()).hexdigest(), 'newModelCalls': 0, 'githubWrites': False, 'npmPublished': False, 'checks': []}
    root = remote('import tempfile; print(tempfile.mkdtemp(prefix="warden-constraint-evidence-",dir="/tmp"))').decode().strip()
    assert re.fullmatch(r'/tmp/warden-constraint-evidence-[A-Za-z0-9_]+', root)
    receipt['remoteTemp'] = root
    try:
        subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', str(archive), 'factory-vps:' + root + '/inputs.tgz'], check=True)
        setup = '''import pathlib,tarfile,hashlib,os
root=pathlib.Path(ROOT); manifest=MANIFEST
with tarfile.open(root/'inputs.tgz') as tar:
 assert {m.name for m in tar.getmembers()}==set(manifest)
 for member in tar.getmembers():
  assert member.isfile() and member.name in manifest
  body=tar.extractfile(member).read(); assert hashlib.sha256(body).hexdigest()==manifest[member.name]['sha256']
  path=root/member.name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(body)
for directory,_,files in os.walk(root/'project'):
 os.chown(directory,65532,65532)
 for name in files: os.chown(pathlib.Path(directory)/name,65532,65532)
out=root/'out'; out.mkdir(); os.chown(out,65532,65532); root.chmod(0o755)
'''.replace('ROOT', repr(root)).replace('MANIFEST', repr(manifest))
        remote(setup)
        def container(entry='node', network='none'):
            return ['docker', 'run', '--rm', '--runtime', 'runc', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--network', network,
                    '--memory', '1536m', '--cpus', '2', '--pids-limit', '128', '--user', '65532:65532', '--tmpfs', '/tmp:rw,nosuid,noexec,size=256m',
                    '-v', root + '/project:/work:rw', '-v', root + '/research:/study:ro', '-v', root + '/out:/out:rw', '--workdir', '/work',
                    '-e', 'HOME=/tmp/warden-home', '-e', 'WARDEN_STATE_DIR=/tmp/warden-state', '-e', 'npm_config_cache=/tmp/npm-cache', '--entrypoint', entry, IMAGE]
        def check(name, command):
            started = datetime.now(timezone.utc).isoformat()
            result = subprocess.run(SSH + [shlex.join(command)], capture_output=True)
            log = result.stdout + result.stderr
            (state / (name + '.log')).write_bytes(log)
            receipt['checks'].append({'name': name, 'exitCode': result.returncode, 'startedAt': started, 'finishedAt': datetime.now(timezone.utc).isoformat(), 'logSha256': sha256(log).hexdigest()})
            print(json.dumps(receipt['checks'][-1]), flush=True)
            if result.returncode: print(log.decode(errors='replace')[-6500:], flush=True)
            assert result.returncode == 0, name
        check('dependencies', container('npm', 'bridge') + ['ci', '--ignore-scripts', '--no-audit', '--no-fund'])
        check('build', container('npm') + ['run', 'build'])
        check('typecheck', container('npm') + ['run', 'typecheck'])
        check('warden-tests', container() + ['node_modules/vitest/vitest.mjs', 'run', *['test/' + name + '.test.ts' for name in TESTS], '--maxWorkers=1', '--no-file-parallelism', '--reporter=default', '--reporter=json', '--outputFile.json=/out/vitest.json'])
        check('redteam', container() + ['scripts/redteam/flow-redteam.mjs', '/out/redteam.json', '--check'])
        check('probe-tests', container('sh') + ['-c', 'cd /study && python3 -B -m unittest -v test_constraint_claims test_reason_audit'])
        check('extract-claims', container('sh') + ['-c', 'cd /study && python3 -B build_cases.py pairs.json /out/cases.json'])
        check('replay', container() + ['/study/replay.mjs', '/out/cases.json', '/study/gold.json', '/out/replay.json'])
    finally:
        collect = '''import pathlib,tarfile,io,hashlib,json,sys
root=pathlib.Path(ROOT); files={}
for base,prefix in [(root/'out','out'),(root/'project/dist','generated/dist'),(root/'project/claude-plugin/scripts','generated/claude-plugin/scripts')]:
 if base.exists():
  for p in base.glob('*'):
   if p.is_file() and not p.is_symlink(): files[prefix+'/'+p.name]=p.read_bytes()
manifest={name:hashlib.sha256(body).hexdigest() for name,body in files.items()}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
 for name,body in files.items():
  m=tarfile.TarInfo(name); m.size=len(body); tar.addfile(m,io.BytesIO(body))
 body=json.dumps(manifest).encode(); m=tarfile.TarInfo('manifest.json'); m.size=len(body); tar.addfile(m,io.BytesIO(body))
sys.stdout.buffer.write(buffer.getvalue())
'''.replace('ROOT', repr(root))
        try:
            output = remote(collect); (state / 'outputs.tar.gz').write_bytes(output)
            with tarfile.open(fileobj=io.BytesIO(output)) as tar:
                hashes = json.load(tar.extractfile('manifest.json'))
                for member in tar.getmembers():
                    p = PurePosixPath(member.name); assert member.isfile() and not p.is_absolute() and '..' not in p.parts
                    body = tar.extractfile(member).read()
                    if member.name != 'manifest.json': assert sha256(body).hexdigest() == hashes[member.name]
                    path = state / member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
            receipt.update(outputSha256=sha256(output).hexdigest(), verifiedOutputs=len(hashes))
        finally:
            receipt['cleanup'] = json.loads(remote('import pathlib,shutil,json; p=pathlib.Path(' + repr(root) + '); shutil.rmtree(p); print(json.dumps({"removed":str(p),"absent":not p.exists()}))'))
            (state / 'execution.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('All offline checks and replay completed; outputs collected and temporary root removed.', flush=True)


if __name__ == '__main__':
    main()
