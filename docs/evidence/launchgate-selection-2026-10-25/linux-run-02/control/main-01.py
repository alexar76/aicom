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


stage_lock = exclusive_stage()
verify_sources()
assert json.loads((OUT/'tests/execution.json').read_text())['passed']
phase = 'main'
target = OUT/phase
assert not target.exists(), 'Phase already attempted; preserve it rather than silently rerunning paid slots'
target.mkdir(mode=0o700)
environment = json.loads((OUT/'environment.json').read_text())
relay_root = OUT/'relay'
relay_root.mkdir(mode=0o700,exist_ok=True)
(relay_root/'stop').unlink(missing_ok=True)
guard = base_container(environment['nodeImage']['id'])
# Add stdin before the image; no TTY, no API environment or key mount.
guard = guard[:2]+['--interactive']+guard[2:]+['--entrypoint','node',environment['nodeImage']['id'],
    '/study/guard_probe.mjs','--warden-root','/warden/package']
relay_command = ['/usr/bin/python3',str(STUDY/'host_relay.py'),'--root',str(relay_root),
    '--key-file','/root/claudecode/aicom/data/secrets/llm/deepseek_api_key','--model','deepseek-flash','--max-calls','363','--workers','1','--timeout','60']
command = ['/usr/bin/python3',str(STUDY/'experiment.py'),'--fixtures',str(STUDY/'fixtures.json'),
    '--out',str(target),'--relay',str(relay_root),'--model','deepseek-flash','--expected-model','deepseek-flash',
    '--repeats','5','--phase',phase,'--guard-command',json.dumps(guard)]
record = {'startedAt':stamp(),'phase':phase,'guardCommand':guard,'experimentCommand':command,
    'model':'deepseek-flash','combinedAttemptCap':372,'priorPaidAttempts':9,
    'remainingPaidAttemptCap':363,'automaticRetries':0,'runnerHost':'factory-vps',
    'guardNetwork':'none','guardRuntime':'runc','credentialScope':'Existing server-local file, host relay only; never copied.'}
put(target/'execution.json',record)
relay_process = None
experiment_process = None
timer = None
try:
    with (target/'relay-host.log').open('wb') as relay_log, (target/'runner.log').open('wb') as runner_log:
        relay_process = subprocess.Popen(relay_command,stdout=relay_log,stderr=subprocess.STDOUT,start_new_session=True,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        deadline = time.monotonic()+10
        while True:
            assert relay_process.poll() is None, 'Host relay failed before readiness'
            assert time.monotonic()<deadline, 'Host relay did not initialize'
            if (relay_root/'req').is_dir() and (relay_root/'.relay.lock').is_file():
                check_fd = os.open(relay_root/'.relay.lock',os.O_RDWR|os.O_NOFOLLOW)
                try:
                    try: fcntl.flock(check_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError: break
                    finally: fcntl.flock(check_fd,fcntl.LOCK_UN)
                finally: os.close(check_fd)
            time.sleep(.1)
        assert relay_process.poll() is None, 'Host relay exited before runner launch'
        experiment_process = subprocess.Popen(command,stdout=runner_log,stderr=subprocess.STDOUT,start_new_session=True,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        timeout = 1800 if phase=='smoke' else 40_000
        try: record['experimentExitCode'] = experiment_process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(experiment_process.pid,signal.SIGTERM)
            record['experimentExitCode'] = experiment_process.wait(timeout=20)
            record['timedOut'] = True
finally:
    (relay_root/'stop').touch()
    if relay_process is not None:
        try: record['relayExitCode'] = relay_process.wait(timeout=75)
        except subprocess.TimeoutExpired:
            os.killpg(relay_process.pid,signal.SIGTERM)
            record['relayExitCode'] = relay_process.wait(timeout=15)
    record['finishedAt'] = stamp()
    record['inputsVerifiedAfter'] = verify_sources()
    put(target/'execution.json',record)
assert record.get('experimentExitCode') == 0 and record.get('relayExitCode') == 0, 'Model phase process failed'
analysis = ['/usr/bin/python3',str(STUDY/'analyze.py'),'--fixtures',str(STUDY/'fixtures.json'),
    '--results',str(target/'runs.jsonl'),'--schedule',str(target/'schedule.json'),'--out',str(target/'analysis.json')]
with (target/'analysis.log').open('wb') as log:
    record['analysisExitCode'] = subprocess.run(analysis,stdout=log,stderr=subprocess.STDOUT,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=180).returncode
rows = [json.loads(line) for line in (target/'runs.jsonl').read_text().splitlines()]
expected = 3 if phase=='smoke' else 270
record['recordedSlots'] = len(rows)
record['expectedSlots'] = expected
record['expectedInitialCalls'] = expected
record['maximumContinuationCalls'] = 0 if phase=='smoke' else 90
record['observedContinuationCalls'] = sum(r.get('continuation_calls',0) for r in rows)
record['maximumPhasePaidCalls'] = 3 if phase=='smoke' else 360
record['allResponsesExpectedModel'] = all(r.get('response_model')=='deepseek-flash' for r in rows)
sys.path.insert(0,str(STUDY))
from analyze import parse_selection
fixtures = {fixture['id']:fixture for fixture in json.loads((STUDY/'fixtures.json').read_text())['fixtures']}
record['selectionFormatDiagnostics'] = [{'fixture_id':r['fixture_id'],'defense':r['defense'],'arm':r['arm'],
    'diagnostic':parse_selection(r.get('answer'),fixtures[r['fixture_id']])[2]} for r in rows]
record['mechanicalSmokePassed'] = phase=='smoke' and len(rows)==3 and record['observedContinuationCalls']==0 and all(
    r.get('arm')=='clean' and
    r.get('status')=='ok' and r.get('finish_reason')=='stop' and r.get('answer') and
    r.get('response_model')=='deepseek-flash' and
    hashlib.sha256(r['answer'].encode()).hexdigest()==r.get('answer_sha256') for r in rows) and all(
    item['diagnostic'] is None for item in record['selectionFormatDiagnostics'])
record['completedAt'] = stamp()
put(target/'execution.json',record)
print(json.dumps({'stage':phase,'recordedSlots':len(rows),'expectedSlots':expected,
    'allResponsesExpectedModel':record['allResponsesExpectedModel'],'mechanicalSmokePassed':record['mechanicalSmokePassed'],
    'analysisExitCode':record['analysisExitCode']}))
assert record['analysisExitCode']==0 and len(rows)==expected, 'Incomplete model phase or failed analysis'
if phase=='smoke': assert record['mechanicalSmokePassed'], 'Smoke instrumentation/model-identity failure; do not advance to main'
