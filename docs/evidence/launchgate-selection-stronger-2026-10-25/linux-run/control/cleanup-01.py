ROOT_TEXT = '/tmp/launchgate-stronger-20261025.jc9gXU'
ARCHIVE_SHA = '89067f5b80fd535304a64280c9e206c8a52a86029aaeb555da1a23cf96ce7803'
INPUT_MANIFEST_SHA = '284653bc1f356ac3d714b42e00389db80e85bcd258c31b2261f6a5be56a7c2b2'

import fcntl, hashlib, json, os, pathlib, platform, re, shutil, signal, stat, subprocess, sys, tarfile, threading, time
from datetime import datetime, timezone
sys.dont_write_bytecode = True
ROOT = pathlib.Path(ROOT_TEXT)
assert re.fullmatch(r'/tmp/launchgate-stronger-20261025\.[A-Za-z0-9]{6}', str(ROOT))
assert ROOT.is_dir() and not ROOT.is_symlink()
STUDY, OUT, WARDEN = ROOT/'study', ROOT/'out', ROOT/'warden'
def stamp(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')
    path.chmod(0o600)
def manifest(directory):
    rows = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink(): raise RuntimeError('Symlink in owned evidence')
        if path.is_file(): rows[str(path.relative_to(directory))] = {'sha256':sha(path),'bytes':path.stat().st_size}
        elif not path.is_dir(): raise RuntimeError('Special file in owned evidence')
    return rows
def verify_sources():
    assert sha(ROOT/'inputs.tar.gz') == ARCHIVE_SHA, 'Frozen transfer archive changed'
    assert sha(STUDY/'input-manifest.json') == INPUT_MANIFEST_SHA, 'Input manifest changed'
    frozen = json.loads((STUDY/'input-manifest.json').read_text())
    assert set(manifest(STUDY)) == set(frozen['files']) | {'input-manifest.json'}
    for name, item in frozen['files'].items():
        path = STUDY/name
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], name
    if (ROOT/'warden-manifest.json').exists():
        assert manifest(WARDEN) == json.loads((ROOT/'warden-manifest.json').read_text())
    return len(frozen['files'])
def extract_safely(archive, destination, *, package=False):
    destination.mkdir(mode=0o755)
    with tarfile.open(archive, 'r:gz') as tar:
        seen = set()
        for member in tar.getmembers():
            path = pathlib.PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts and path.parts
            assert member.isfile() or member.isdir(), 'Only regular files/directories are allowed'
            assert member.name not in seen, 'Duplicate member'
            seen.add(member.name)
            if package: assert path.parts[0] == 'package'
            target = destination.joinpath(*path.parts)
            if member.isdir(): target.mkdir(parents=True, exist_ok=True, mode=0o755)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open('xb') as stream: shutil.copyfileobj(tar.extractfile(member), stream)
                target.chmod(0o644)
def image(prefix):
    data = json.loads(subprocess.check_output(['docker','image','inspect',prefix.removeprefix('sha256:')]))[0]
    assert data['Id'].startswith(prefix), 'Unexpected image identity'
    return {'id':data['Id'],'repoDigests':data.get('RepoDigests',[]),'os':data['Os'],'architecture':data['Architecture']}
def base_container(image_id):
    return ['docker','run','--rm','--runtime','runc','--network','none','--read-only',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--user','65532:65532',
        '--memory','512m','--cpus','1','--pids-limit','96',
        '--tmpfs','/tmp:rw,nosuid,noexec,size=128m',
        '--label','launchgate-selection-study='+ARCHIVE_SHA,
        '-v',str(STUDY)+':/study:ro','-v',str(WARDEN)+':/warden:ro','--workdir','/study']
def exclusive_stage():
    fd = os.open(ROOT/'.stage.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return fd


stage_lock = exclusive_stage()
inputs = verify_sources()
expected = {'environment.json': {'bytes': 836, 'sha256': '590b034a53de154622e3a4d2235bf480bfe2b51729c52e0fceabf62926cd4236'}, 'tests/execution.json': {'bytes': 2646, 'sha256': 'a30a6d62b2db0b26c96d547de6f1b365d5ce76b3ef2d33f1e563dd1aa6db38a8'}, 'tests/node.log': {'bytes': 2370, 'sha256': 'a6c1949271dfef1a1235c17a65dd66d27ca559a4a98c4e1a6483c9a4da23a14c'}, 'tests/python.log': {'bytes': 17956, 'sha256': '5171a6da95843b3521968e125f32bd0bb284eea956b636b534d3f53801fc4258'}}
assert manifest(OUT) == expected, 'Remote output changed since verified download'
active = subprocess.check_output(['docker','ps','-q','--filter','label=launchgate-selection-study='+ARCHIVE_SHA],text=True).strip()
assert not active, 'An owned guard/test container is still running'
lock_path = OUT/'relay/.relay.lock'
lock_fd = None
if lock_path.exists():
    lock_fd = os.open(lock_path,os.O_RDWR|os.O_NOFOLLOW)
    fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
files = len(expected)
warden_files = len(manifest(WARDEN))
root_text = str(ROOT)
shutil.rmtree(ROOT)
if lock_fd is not None: os.close(lock_fd)
print(json.dumps({'removed':not ROOT.exists(),'remoteRoot':root_text,'inputsVerified':inputs,
    'wardenArtifactFilesVerified':warden_files,
    'outputsVerified':files,'cleanedAt':stamp()}))
