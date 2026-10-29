ROOT_TEXT = '/tmp/launchgate-selection-20261025.QLzT6N'
ARCHIVE_SHA = '6a767736340c74915eccd275f2558810948dbef6a877d75c28360164a0980cad'
INPUT_MANIFEST_SHA = 'fec5f805b3fadaca891206dfe9ef84de5c54502ea5e79a8b87be62673ecd17ca'

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


stage_lock = exclusive_stage()
inputs = verify_sources()
expected = {'environment.json': {'bytes': 836, 'sha256': '661135109423b0b01c21955a56a45d1808f8cf2a311f4dbde32d494765c66006'}, 'relay/.relay.lock': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'relay/req/013e88f4794d44498eb44f5278b758e9.json': {'bytes': 2379, 'sha256': 'be9cc236c67c9475ef2359836344c95684b675532178249dd44ed2ef7bbab339'}, 'relay/req/33662a357efe407895120d8c758d33c3.json': {'bytes': 2399, 'sha256': '05a809dc654332034a887d49077dbcb2ccc9ae0f08f3d271bbb654d18deae4f7'}, 'relay/req/4dda1970d4374af98ad41e4fbc6afbe1.json': {'bytes': 2379, 'sha256': 'be9cc236c67c9475ef2359836344c95684b675532178249dd44ed2ef7bbab339'}, 'relay/req/5ca6757af4d646b6ab1e1b89adc36f28.json': {'bytes': 2410, 'sha256': '321717ead4a518dcda45f5e2b2fd7b182bf9dd2c3dcf685958d856f7a6cc49f8'}, 'relay/req/968ea9e9e0ba40088698615ce1e7bc97.json': {'bytes': 2252, 'sha256': '8c2ab685bfcad2aa421e75deb34e2c49284e410ec4dea58231dd512f41122bbf'}, 'relay/req/9bae694837be4675917797465dc74cd1.json': {'bytes': 2221, 'sha256': 'a93f7840aff0f63874803f5eb9a796f0c19771337dca0fbc0d6c204b51c9f9e5'}, 'relay/req/c766b1203a074018b45f133f90bb03f1.json': {'bytes': 2399, 'sha256': '05a809dc654332034a887d49077dbcb2ccc9ae0f08f3d271bbb654d18deae4f7'}, 'relay/req/ed580d41eff2497bad6ec87056efe245.json': {'bytes': 2410, 'sha256': '321717ead4a518dcda45f5e2b2fd7b182bf9dd2c3dcf685958d856f7a6cc49f8'}, 'relay/req/f1bdabea095c46dc81c51b865add20b6.json': {'bytes': 2241, 'sha256': '7929f2f0b9591d7724a3dfc3b79ccf94f9275a5a80c0eeb13102419d155fcadc'}, 'relay/resp/013e88f4794d44498eb44f5278b758e9.json': {'bytes': 1129, 'sha256': '636fee5d777fcad9fc2f78c66a2dd9a7784ad5954cb16c0d5f070e54fd621c1d'}, 'relay/resp/33662a357efe407895120d8c758d33c3.json': {'bytes': 1073, 'sha256': 'fce4f7f17258e541de95d2497e0c892772edb9bb98e60475c12dba62c0504628'}, 'relay/resp/4dda1970d4374af98ad41e4fbc6afbe1.json': {'bytes': 1102, 'sha256': 'bf4cd12fd019c56f26fec782a2f241663785d3081fe1cd873370251eb5c4073f'}, 'relay/resp/5ca6757af4d646b6ab1e1b89adc36f28.json': {'bytes': 1057, 'sha256': '55b1207ee6a268b82de605d9b85545b62b05f12b80d45a1d5dd09d507bd1719b'}, 'relay/resp/968ea9e9e0ba40088698615ce1e7bc97.json': {'bytes': 1053, 'sha256': '294a2e5ef164eaef02df1939f7abd35142dced9a360716640c3ce74850e34022'}, 'relay/resp/9bae694837be4675917797465dc74cd1.json': {'bytes': 1142, 'sha256': '5b86d3513c1468a664a23f7e9208f89c34ba5889476a40d98ef2efeb9c29ce98'}, 'relay/resp/c766b1203a074018b45f133f90bb03f1.json': {'bytes': 977, 'sha256': '0563059d7d85138e88e64fc0eb4b0c527cf3aa7d010148537b5eb2bd19711942'}, 'relay/resp/ed580d41eff2497bad6ec87056efe245.json': {'bytes': 1021, 'sha256': '3c8103b018c5df39ca50786d329e04193dbfc2a453772b3065b4dfee6363c3c3'}, 'relay/resp/f1bdabea095c46dc81c51b865add20b6.json': {'bytes': 977, 'sha256': '00c7c00291759b6f391e65c30750edd93669a0c29e197e9292c22c8b5041f977'}, 'relay/stop': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'relay/usage.jsonl': {'bytes': 8357, 'sha256': 'b36f76a71365caa652736ae9c7ccaf8a5909c2e073bcbad87988731ebc8b2608'}, 'smoke/analysis.json': {'bytes': 105535, 'sha256': 'e2cdec9b7c506caa350258b92ffe23c5709a7cdf3b91e1b94b8491837a47a9e6'}, 'smoke/analysis.log': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'smoke/completion.json': {'bytes': 346, 'sha256': '53e4c423a1f71750927d3e14ce5643236cad6fccf52c379a7d2d677ec7f8f38e'}, 'smoke/execution.json': {'bytes': 3976, 'sha256': 'ac748b7f259139d6b2c2fb887d76ae2df92d2b3468eedd717da780c19e5f1636'}, 'smoke/guard-stderr.log': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'smoke/relay-host.log': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'smoke/runner.log': {'bytes': 76, 'sha256': '7d70c18c97fd47bfd6c201c58a7f01a746598e3cdc9fe8079c4370d103fee938'}, 'smoke/runs.jsonl': {'bytes': 82521, 'sha256': '4cb441e557e3c1491d2f26aa88068b7ce634f7d08890c867ab0afc97e8afd7f0'}, 'smoke/schedule.json': {'bytes': 2896, 'sha256': 'df60b48b5cc6018d344b23d23b392b17a9204085cb5b5bac5c7a06837246275d'}, 'tests/execution.json': {'bytes': 2622, 'sha256': '103cedc06df0250fed6964c3b402d838f49cc061b597cb5a45c50ee4728c7455'}, 'tests/node.log': {'bytes': 2365, 'sha256': '63d6ad2e0e47768d1050cc25d0248e9ee0752096b85ce8d34e1edfa419e9aaef'}, 'tests/python.log': {'bytes': 11734, 'sha256': 'd8ad3c6fd7ce03c1080fca29eeb625a6f3ef44f2bd34df397a92f8cf0af389a5'}}
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
