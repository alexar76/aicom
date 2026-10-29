ROOT_TEXT = '/tmp/launchgate-selection-20261025.WW9iQW'
ARCHIVE_SHA = 'cdea089d8b688c6c9e06a1d01c882d46c9ef8d2ab5178694b08582e6dbf5d34d'
INPUT_MANIFEST_SHA = '72a70798cafa25f6944a9e39ade4ad66fe3056da81f1153e5f2f05ba9dde41c9'

import fcntl, hashlib, json, os, pathlib, platform, re, shutil, signal, stat, subprocess, sys, tarfile, threading, time
from datetime import datetime, timezone
sys.dont_write_bytecode = True
ROOT = pathlib.Path(ROOT_TEXT)
assert re.fullmatch(r'/tmp/launchgate-selection-20261025\.[A-Za-z0-9]{6}', str(ROOT))
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


assert sha(ROOT/'inputs.tar.gz') == 'cdea089d8b688c6c9e06a1d01c882d46c9ef8d2ab5178694b08582e6dbf5d34d'
assert not STUDY.exists() and not OUT.exists() and not WARDEN.exists()
extract_safely(ROOT/'inputs.tar.gz', STUDY)
assert sha(STUDY/'input-manifest.json') == '72a70798cafa25f6944a9e39ade4ad66fe3056da81f1153e5f2f05ba9dde41c9'
assert sha(STUDY/'warden.tgz') == '5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
OUT.mkdir(mode=0o700)
extract_safely(STUDY/'warden.tgz', WARDEN, package=True)
put(ROOT/'warden-manifest.json', manifest(WARDEN))
inputs = verify_sources()
assert sys.platform == 'linux' and sys.version_info >= (3,10)
environment = {'preparedAt':stamp(),'platform':platform.platform(),'python':sys.version,
    'node':subprocess.check_output(['/usr/bin/node','--version'],text=True).strip(),
    'nodeImage':image('sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402'),'pythonImage':image('sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'),
    'inputsVerified':inputs,'wardenFiles':len(manifest(WARDEN)),
    'credentialAccess':False,'modelCalls':0}
put(OUT/'environment.json', environment)
print(json.dumps({'stage':'provisioned','inputsVerified':inputs,'wardenFiles':environment['wardenFiles']}))
