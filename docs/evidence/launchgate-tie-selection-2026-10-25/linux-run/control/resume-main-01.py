ROOT_TEXT = '/tmp/launchgate-tie-20261025.oRT2Of'
ARCHIVE_SHA = '57dc85fdd259dc06cd20f613c9aeceef3c36ede01c41b8e32d49b20c0c6d11a4'
INPUT_MANIFEST_SHA = '7e5a98cc9f056c9d3ce387709bc259f8c5845fb459f89a657cd53ab4dd59ef06'

import fcntl, hashlib, json, os, pathlib, platform, re, shutil, signal, stat, subprocess, sys, tarfile, threading, time
from datetime import datetime, timezone
sys.dont_write_bytecode = True
ROOT = pathlib.Path(ROOT_TEXT)
assert re.fullmatch(r'/tmp/launchgate-tie-20261025\.[A-Za-z0-9]{6}', str(ROOT))
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
verify_sources()
target = OUT/'main'
old = json.loads((target/'execution.json').read_text())
boundary = json.loads((target/'segment-boundary.json').read_text())
assert old['experimentExitCode'] == -15 and boundary['signal']=='SIGTERM'
assert not (target/'completion.json').exists()
assert not (target/'execution-segment-02.json').exists(), 'Never silently repeat a segment'
active = subprocess.check_output(['docker','ps','-q','--filter','label=launchgate-selection-study='+ARCHIVE_SHA],text=True).strip()
assert not active, 'Prior hook process must be finished'
prefix = (target/'runs.jsonl').read_bytes()
assert prefix.endswith(b'\n')
previous_rows = len(prefix.splitlines())
assert 270 <= previous_rows < 432
command = old['experimentCommand']
assert command[0]=='/usr/bin/python3' and command[1]==str(STUDY/'experiment.py')
assert command[command.index('--out')+1]==str(target)
assert command[command.index('--phase')+1]=='main'
assert command[command.index('--model')+1]=='deepseek-flash'
assert command[command.index('--repeats')+1]=='8'
relay_root = OUT/'relay'
(relay_root/'stop').unlink(missing_ok=True)
relay_command = ['/usr/bin/python3',str(STUDY/'host_relay.py'),'--root',str(relay_root),
    '--key-file','/root/claudecode/aicom/data/secrets/llm/deepseek_api_key',
    '--model','deepseek-flash','--max-calls','620','--workers','1','--timeout','60']
put(target/'execution-segment-01.json',old)
record = {'startedAt':stamp(),'segment':2,'previousRows':previous_rows,
    'previousRowsSha256':hashlib.sha256(prefix).hexdigest(),
    'sameFrozenCommand':command,'sameInputArchiveSha256':ARCHIVE_SHA,
    'durableRequestIdentityReused':True,'newPlan':False,'automaticRetries':0}
relay_process = None
try:
    with (target/'segment-02-relay.log').open('wb') as relay_log, (target/'segment-02-runner.log').open('wb') as runner_log:
        relay_process = subprocess.Popen(relay_command,stdout=relay_log,stderr=subprocess.STDOUT,
            start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        deadline = time.monotonic()+10
        while True:
            assert relay_process.poll() is None, 'Relay failed before resume'
            assert time.monotonic()<deadline
            lock_fd=os.open(relay_root/'.relay.lock',os.O_RDWR|os.O_NOFOLLOW)
            try:
                try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:break
                finally:fcntl.flock(lock_fd,fcntl.LOCK_UN)
            finally:os.close(lock_fd)
            time.sleep(.1)
        process=subprocess.Popen(command,stdout=runner_log,stderr=subprocess.STDOUT,
            start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        record['experimentExitCode']=process.wait(timeout=40000)
finally:
    (relay_root/'stop').touch()
    if relay_process is not None:
        try:record['relayExitCode']=relay_process.wait(timeout=75)
        except subprocess.TimeoutExpired:
            os.killpg(relay_process.pid,signal.SIGTERM)
            record['relayExitCode']=relay_process.wait(timeout=15)
    record['finishedAt']=stamp()
    record['inputsVerifiedAfter']=verify_sources()
    assert (target/'runs.jsonl').read_bytes().startswith(prefix), 'Completed prefix changed'
    record['previousRowsPreserved']=True
    put(target/'execution-segment-02.json',record)
assert record['experimentExitCode']==0 and record['relayExitCode']==0
completion=json.loads((target/'completion.json').read_text())
assert completion['scheduled']==completion['completed_slots']==432 and completion['abort_reason'] is None
analysis=['/usr/bin/python3',str(STUDY/'analyze.py'),'--fixtures',str(STUDY/'fixtures.json'),
    '--results',str(target/'runs.jsonl'),'--schedule',str(target/'schedule.json'),'--out',str(target/'analysis.json')]
with (target/'analysis.log').open('wb') as log:
    record['analysisExitCode']=subprocess.run(analysis,stdout=log,stderr=subprocess.STDOUT,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=180).returncode
assert record['analysisExitCode']==0
record['completedAt']=stamp()
put(target/'execution-segment-02.json',record)
put(target/'execution.json',{'phase':'main','segments':2,'completedAt':stamp(),
    'recordedSlots':432,'expectedSlots':432,'analysisExitCode':0,
    'experimentExitCode':0,'relayExitCode':0,'sameFrozenPlan':True,
    'segmentRecords':['execution-segment-01.json','execution-segment-02.json']})
print(json.dumps({'stage':'resumed-main-complete','segments':2,'recordedSlots':432,
    'previousRowsPreserved':True,'sameFrozenPlan':True,'analysisExitCode':0}))
