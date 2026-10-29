#!/usr/bin/env python3
"""Explicit stages for the bounded Linux selection study; never reads a local API key.

--prepare only freezes local allowlisted bytes. --tests transfers them and runs
offline unit checks. --smoke and --main are separate, explicit paid-model stages;
--collect verifies/downloads owned outputs, and --cleanup requires the newest
verified collection. Use a NEW --state-dir after changing any frozen study file.
No Git, production configuration, package publication or fleet mutation occurs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
FILES = (
    'experiment.py', 'analyze.py', 'test_analyze.py', 'guard_probe.mjs',
    'test_guard_probe.mjs', 'fixtures.json', 'control-fixtures.json', 'protocol.md', 'host_relay.py', 'test_host_relay.py', 'test_experiment.py', 'test_stronger.py',
)
ARCHIVE = WORKSPACE / 'docs/evidence/auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz'
WARDEN_SHA = '5cc9aec04fc753adeb2ab97264c571e625b65bb57b43de2541dd4cf6260bc1f1'
REMOTE_PATTERN = r'/tmp/launchgate-stronger-20261025\.[A-Za-z0-9]{6}'
NODE_IMAGE = 'sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402'
PYTHON_IMAGE = 'sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1'
HOST = 'factory-vps'
MODEL = 'mistralai/ministral-8b-2512'
MAX_CALLS = 400
# This path is passed only to the REMOTE host relay, never opened or copied here.
REMOTE_KEY = '/root/claudecode/aicom/data/secrets/llm/openrouter_api_key'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(value))


def read(path):
    return json.loads(path.read_text())


def require(value, message):
    if not value:
        raise RuntimeError(message)


def input_files(state):
    manifest = read(state / 'input-manifest.json')
    archive = state / 'inputs.tar.gz'
    require(digest(archive.read_bytes()) == read(state / 'preparation.json')['archiveSha256'], 'Frozen archive changed')
    return manifest


def prepare(state, prior_attempts=0):
    require(type(prior_attempts) is int and 0 <= prior_attempts < MAX_CALLS,
            '--prior-attempts must be an integer from 0 through 399')
    state.mkdir(parents=True, exist_ok=True)
    require(not (state / 'preparation.json').exists(), 'Frozen evidence exists; use a new --state-dir, never silently refreeze')
    frozen = {}
    for name in FILES:
        source = HERE / name
        require(source.is_file() and not source.is_symlink(), f'Missing/unsafe allowlisted input: {name}')
        frozen[name] = source.read_bytes()
    frozen['warden.tgz'] = ARCHIVE.read_bytes()
    require(digest(frozen['warden.tgz']) == WARDEN_SHA, 'Published WARDEN archive does not match known SHA')
    manifest = {
        'schema': 'launchgate-selection-frozen-inputs/1', 'createdAt': now(),
        'scope': 'Twelve own study files and one public own WARDEN archive; no credentials, env, project configs or foreign MCP implementation.',
        'files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in frozen.items()},
        'publishedWardenArchiveSha256': WARDEN_SHA,
    }
    manifest_bytes = encode(manifest)
    archive = state / 'inputs.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name, data in {**frozen, 'input-manifest.json': manifest_bytes}.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    (state / 'input-manifest.json').write_bytes(manifest_bytes)
    save(state / 'preparation.json', {
        'preparedAt': now(), 'stage': 'local-freeze-only-no-transfer',
        'archiveSha256': digest(archive.read_bytes()), 'archiveBytes': archive.stat().st_size,
        'manifestSha256': digest(manifest_bytes), 'files': len(frozen),
        'orchestratorSha256': digest(Path(__file__).read_bytes()),
        'host': HOST, 'model': MODEL, 'maximumCombinedPaidAttempts': MAX_CALLS,
        'priorPaidAttempts': prior_attempts, 'remainingPaidAttemptCap': MAX_CALLS - prior_attempts,
    })
    print(json.dumps({'stage': 'prepared', 'files': len(frozen), 'archiveBytes': archive.stat().st_size,
                      'archiveSha256': digest(archive.read_bytes()), 'networkUsed': False,
                      'priorPaidAttempts': prior_attempts, 'remainingPaidAttemptCap': MAX_CALLS - prior_attempts}), flush=True)


def ssh(state, script, name):
    runs = state / 'control'
    runs.mkdir(exist_ok=True)
    number = len(list(runs.glob(name + '-*.py'))) + 1
    base = runs / f'{name}-{number:02d}'
    base.with_suffix('.py').write_text(script)
    print(json.dumps({'stage': name, 'host': HOST, 'startedAt': now()}), flush=True)
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', HOST, 'python3 -'],
                            input=script.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base.with_suffix('.stdout.log').write_bytes(result.stdout)
    base.with_suffix('.stderr.log').write_bytes(result.stderr)
    save(base.with_suffix('.json'), {'finishedAt': now(), 'exitCode': result.returncode,
                                   'scriptSha256': digest(script.encode()),
                                   'orchestratorSha256': digest(Path(__file__).read_bytes()),
                                   'stdoutSha256': digest(result.stdout), 'stderrSha256': digest(result.stderr)})
    # Only controlled progress/final JSON is printed by our remote scripts.
    if result.stdout:
        print(result.stdout.decode('utf-8', 'replace').rstrip(), flush=True)
    require(result.returncode == 0, f'Remote {name} failed; preserved stdout/stderr and script in {base.parent}')
    return result.stdout


def remote_record(state):
    record = read(state / 'remote.json')
    require(record['host'] == HOST and re.fullmatch(REMOTE_PATTERN, record['root']), 'Unsafe remote identity')
    return record


COMMON = r'''
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
'''


def script_for(state, body):
    record = remote_record(state)
    return ('ROOT_TEXT = ' + repr(record['root']) + '\nARCHIVE_SHA = ' + repr(read(state / 'preparation.json')['archiveSha256']) +
            '\nINPUT_MANIFEST_SHA = ' + repr(read(state / 'preparation.json')['manifestSha256']) +
            '\n' + COMMON + '\n' + body)


def provision(state):
    input_files(state)
    if (state / 'remote.json').exists():
        remote_record(state)
        return
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', HOST,
                             'mktemp -d /tmp/launchgate-stronger-20261025.XXXXXX'],
                            check=True, capture_output=True, text=True)
    root = result.stdout.strip()
    require(re.fullmatch(REMOTE_PATTERN, root), 'Unexpected remote temporary path')
    save(state / 'remote.json', {'host': HOST, 'root': root, 'createdAt': now(), 'status': 'created-not-yet-extracted'})
    subprocess.run(['scp', '-q', str(state / 'inputs.tar.gz'), HOST + ':' + root + '/inputs.tar.gz'], check=True)
    sha = read(state / 'preparation.json')['archiveSha256']
    body = f'''
assert sha(ROOT/'inputs.tar.gz') == {sha!r}
assert not STUDY.exists() and not OUT.exists() and not WARDEN.exists()
extract_safely(ROOT/'inputs.tar.gz', STUDY)
assert sha(STUDY/'input-manifest.json') == {read(state / 'preparation.json')['manifestSha256']!r}
assert sha(STUDY/'warden.tgz') == {WARDEN_SHA!r}
OUT.mkdir(mode=0o700)
extract_safely(STUDY/'warden.tgz', WARDEN, package=True)
put(ROOT/'warden-manifest.json', manifest(WARDEN))
inputs = verify_sources()
assert sys.platform == 'linux' and sys.version_info >= (3,10)
environment = {{'preparedAt':stamp(),'platform':platform.platform(),'python':sys.version,
    'node':subprocess.check_output(['/usr/bin/node','--version'],text=True).strip(),
    'nodeImage':image({NODE_IMAGE!r}),'pythonImage':image({PYTHON_IMAGE!r}),
    'inputsVerified':inputs,'wardenFiles':len(manifest(WARDEN)),
    'credentialAccess':False,'modelCalls':0}}
put(OUT/'environment.json', environment)
print(json.dumps({{'stage':'provisioned','inputsVerified':inputs,'wardenFiles':environment['wardenFiles']}}))
'''
    ssh(state, script_for(state, body), 'provision')
    record = remote_record(state)
    record['status'] = 'provisioned'
    save(state / 'remote.json', record)


def collect(state):
    record = remote_record(state)
    number = len(list(state.glob('collection-*'))) + 1
    local = state / f'collection-{number:02d}'
    local.mkdir()
    body = '''
stage_lock = exclusive_stage()
inputs = verify_sources()
outputs = manifest(OUT)
put(ROOT/'output-manifest.json', outputs)
with tarfile.open(ROOT/'outputs.tar.gz','w:gz') as tar:
    for name in outputs: tar.add(OUT/name, arcname='out/'+name, recursive=False)
    tar.add(ROOT/'output-manifest.json',arcname='output-manifest.json',recursive=False)
assert manifest(OUT) == outputs, 'Output changed during collection'
verify_sources()
print(json.dumps({'stage':'collection-ready','inputsVerified':inputs,'outputFiles':len(outputs),
    'archiveSha256':sha(ROOT/'outputs.tar.gz'),'archiveBytes':(ROOT/'outputs.tar.gz').stat().st_size}))
'''
    output = ssh(state, script_for(state, body), 'collect')
    metadata = json.loads(output.decode().splitlines()[-1])
    subprocess.run(['scp', '-q', HOST + ':' + record['root'] + '/outputs.tar.gz', str(local / 'outputs.tar.gz')], check=True)
    require(digest((local / 'outputs.tar.gz').read_bytes()) == metadata['archiveSha256'], 'Downloaded archive SHA mismatch')
    with tarfile.open(local / 'outputs.tar.gz', 'r:gz') as tar:
        names = set()
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            require(member.isfile() and not path.is_absolute() and '..' not in path.parts and member.name not in names,
                    'Unsafe output archive member')
            require(member.name == 'output-manifest.json' or path.parts[0] == 'out', 'Unexpected output member')
            names.add(member.name)
            target = local.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    outputs = read(local / 'output-manifest.json')
    require(names == {'output-manifest.json'} | {'out/' + name for name in outputs}, 'Output member set mismatch')
    for name, item in outputs.items():
        data = (local / 'out' / name).read_bytes()
        require(len(data) == item['bytes'] and digest(data) == item['sha256'], 'Downloaded output bytes mismatch')
    save(local / 'verification.json', {**metadata, 'verifiedAt': now(), 'allOutputHashesVerified': True})
    save(state / 'latest-collection.json', {'directory': local.name,
        'manifestSha256': digest((local / 'output-manifest.json').read_bytes()), 'verifiedAt': now()})
    print(json.dumps({'stage': 'collected', 'directory': str(local), 'verifiedFiles': len(outputs)}), flush=True)
    return local


def tests(state):
    provision(state)
    body = f'''
stage_lock = exclusive_stage()
verify_sources()
assert not (OUT/'tests').exists(), 'Tests already attempted; preserve them and use a fresh frozen run for changed inputs'
target = OUT/'tests'; target.mkdir(mode=0o700)
environment = json.loads((OUT/'environment.json').read_text())
commands = {{
 'python': base_container(environment['pythonImage']['id']) + ['-e','PYTHONDONTWRITEBYTECODE=1','--entrypoint','python',
     environment['pythonImage']['id'],'-m','unittest','-v','test_analyze.py','test_host_relay.py','test_experiment.py','test_stronger.py'],
 'node': base_container(environment['nodeImage']['id']) + ['-e','WARDEN_TEST_ROOT=/warden/package','--entrypoint','node',
     environment['nodeImage']['id'],'--test','/study/test_guard_probe.mjs'],
}}
results = {{}}
for name, command in commands.items():
    with (target/(name+'.log')).open('wb') as log:
        result = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    results[name] = {{'exitCode':result.returncode,'command':command,'logSha256':sha(target/(name+'.log'))}}
record = {{'finishedAt':stamp(),'network':'none','runtime':'runc','modelCalls':0,'credentialAccess':False,
    'results':results,'inputsVerifiedAfter':verify_sources(),'passed':all(r['exitCode']==0 for r in results.values())}}
put(target/'execution.json',record)
print(json.dumps({{'stage':'offline-tests','passed':record['passed'],'exitCodes':{{k:v['exitCode'] for k,v in results.items()}}}}))
raise SystemExit(0 if record['passed'] else 1)
'''
    try:
        ssh(state, script_for(state, body), 'tests')
        save(state / 'tests-passed.json', {'passedAt': now(), 'archiveSha256': read(state / 'preparation.json')['archiveSha256']})
    finally:
        collect(state)


def model_phase(state, phase):
    require((state / 'tests-passed.json').exists(), 'Run and pass --tests first')
    preparation = read(state / 'preparation.json')
    prior_attempts = preparation.get('priorPaidAttempts', 0)
    remaining_cap = preparation.get('remainingPaidAttemptCap', MAX_CALLS)
    require(type(prior_attempts) is int and 0 <= prior_attempts < MAX_CALLS and
            type(remaining_cap) is int and remaining_cap == MAX_CALLS - prior_attempts,
            'Invalid cumulative paid-attempt budget in frozen preparation record')
    if phase in ('control', 'main'):
        require((state / 'smoke-passed.json').exists(), 'Inspect and pass --smoke before explicitly starting --main')
        if phase == 'main':
            require((state / 'control-completed.json').exists(), 'Complete the authorized-user control before --main')
    body = f'''
stage_lock = exclusive_stage()
verify_sources()
assert json.loads((OUT/'tests/execution.json').read_text())['passed']
phase = {phase!r}
target = OUT/phase
assert not target.exists(), 'Phase already attempted; preserve it rather than silently rerunning paid slots'
target.mkdir(mode=0o700)
fixture_path = STUDY/('control-fixtures.json' if phase=='control' else 'fixtures.json')
environment = json.loads((OUT/'environment.json').read_text())
relay_root = OUT/'relay'
relay_root.mkdir(mode=0o700,exist_ok=True)
(relay_root/'stop').unlink(missing_ok=True)
guard = base_container(environment['nodeImage']['id'])
# Add stdin before the image; no TTY, no API environment or key mount.
guard = guard[:2]+['--interactive']+guard[2:]+['--entrypoint','node',environment['nodeImage']['id'],
    '/study/guard_probe.mjs','--warden-root','/warden/package']
relay_command = ['/usr/bin/python3',str(STUDY/'host_relay.py'),'--root',str(relay_root),
    '--key-file',{REMOTE_KEY!r},'--model',{MODEL!r},'--max-calls',{str(remaining_cap)!r},'--workers','1','--timeout','60']
command = ['/usr/bin/python3',str(STUDY/'experiment.py'),'--fixtures',str(fixture_path),
    '--out',str(target),'--relay',str(relay_root),'--model',{MODEL!r},'--expected-model',{MODEL!r},
    '--repeats','5','--phase',phase,'--guard-command',json.dumps(guard)]
record = {{'startedAt':stamp(),'phase':phase,'guardCommand':guard,'experimentCommand':command,
    'model':{MODEL!r},'combinedAttemptCap':400,'priorPaidAttempts':{prior_attempts!r},
    'remainingPaidAttemptCap':{remaining_cap!r},'automaticRetries':0,'runnerHost':'factory-vps',
    'guardNetwork':'none','guardRuntime':'runc','credentialScope':'Existing server-local file, host relay only; never copied.'}}
put(target/'execution.json',record)
relay_process = None
experiment_process = None
timer = None
try:
    with (target/'relay-host.log').open('wb') as relay_log, (target/'runner.log').open('wb') as runner_log:
        relay_process = subprocess.Popen(relay_command,stdout=relay_log,stderr=subprocess.STDOUT,start_new_session=True,
            env={{**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}})
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
            env={{**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}})
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
analysis = ['/usr/bin/python3',str(STUDY/'analyze.py'),'--fixtures',str(fixture_path),
    '--results',str(target/'runs.jsonl'),'--schedule',str(target/'schedule.json'),'--out',str(target/'analysis.json')]
with (target/'analysis.log').open('wb') as log:
    record['analysisExitCode'] = subprocess.run(analysis,stdout=log,stderr=subprocess.STDOUT,
        env={{**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}},timeout=180).returncode
rows = [json.loads(line) for line in (target/'runs.jsonl').read_text().splitlines()]
expected = {{'smoke':3,'control':18,'main':270}}[phase]
record['recordedSlots'] = len(rows)
record['expectedSlots'] = expected
record['expectedInitialCalls'] = expected
record['maximumContinuationCalls'] = {{'smoke':0,'control':6,'main':90}}[phase]
record['observedContinuationCalls'] = sum(r.get('continuation_calls',0) for r in rows)
record['maximumPhasePaidCalls'] = {{'smoke':3,'control':24,'main':360}}[phase]
record['allResponsesExpectedModel'] = all(r.get('response_model')=={MODEL!r} for r in rows)
sys.path.insert(0,str(STUDY))
from analyze import parse_selection
fixtures = {{fixture['id']:fixture for fixture in json.loads(fixture_path.read_text())['fixtures']}}
record['selectionFormatDiagnostics'] = [{{'fixture_id':r['fixture_id'],'defense':r['defense'],'arm':r['arm'],
    'diagnostic':parse_selection(r.get('answer'),fixtures[r['fixture_id']])[2]}} for r in rows]
record['mechanicalSmokePassed'] = phase=='smoke' and len(rows)==3 and record['observedContinuationCalls']==0 and all(
    r.get('arm')=='clean' and
    r.get('status')=='ok' and r.get('finish_reason')=='stop' and r.get('answer') and
    r.get('response_model')=={MODEL!r} and
    hashlib.sha256(r['answer'].encode()).hexdigest()==r.get('answer_sha256') for r in rows) and all(
    item['diagnostic'] is None for item in record['selectionFormatDiagnostics'])
record['completedAt'] = stamp()
put(target/'execution.json',record)
print(json.dumps({{'stage':phase,'recordedSlots':len(rows),'expectedSlots':expected,
    'allResponsesExpectedModel':record['allResponsesExpectedModel'],'mechanicalSmokePassed':record['mechanicalSmokePassed'],
    'analysisExitCode':record['analysisExitCode']}}))
assert record['analysisExitCode']==0 and len(rows)==expected, 'Incomplete model phase or failed analysis'
if phase=='smoke': assert record['mechanicalSmokePassed'], 'Smoke instrumentation/model-identity failure; do not advance to main'
'''
    try:
        ssh(state, script_for(state, body), phase)
        if phase == 'control':
            save(state / 'control-completed.json', {'completedAt': now(), 'scope': 'Authorized-user choice control; correct-ID outcomes do not gate main.'})
        if phase == 'smoke':
            save(state / 'smoke-passed.json', {'passedAt': now(), 'archiveSha256': read(state / 'preparation.json')['archiveSha256'],
                'scope': 'Three complete clean expected-model responses, one per defense, with no continuation; selection correctness is an experimental outcome, not the smoke gate.'})
    finally:
        collect(state)


def cleanup(state):
    latest = read(state / 'latest-collection.json')
    local = state / latest['directory']
    require(read(local / 'verification.json')['allOutputHashesVerified'], 'No verified output collection')
    output_manifest = read(local / 'output-manifest.json')
    for name, item in output_manifest.items():
        path = local / 'out' / name
        require(path.is_file() and digest(path.read_bytes()) == item['sha256'], 'Local evidence changed before cleanup')
    body = f'''
stage_lock = exclusive_stage()
inputs = verify_sources()
expected = {output_manifest!r}
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
print(json.dumps({{'removed':not ROOT.exists(),'remoteRoot':root_text,'inputsVerified':inputs,
    'wardenArtifactFilesVerified':warden_files,
    'outputsVerified':files,'cleanedAt':stamp()}}))
'''
    output = ssh(state, script_for(state, body), 'cleanup')
    receipt = json.loads(output.decode().splitlines()[-1])
    save(state / 'cleanup.json', {**receipt, 'localCollection': local.name, 'verifiedDownloadBeforeRemoval': True})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=HERE / 'linux-run')
    parser.add_argument('--prior-attempts', type=int, default=0,
                        help='For --prepare only: already-reserved paid attempts in preserved prior study runs (new-study ceiling remains 400)')
    group = parser.add_mutually_exclusive_group(required=True)
    for stage in ('prepare', 'tests', 'smoke', 'control', 'main', 'collect', 'cleanup'):
        group.add_argument('--' + stage, action='store_true')
    args = parser.parse_args()
    if not args.prepare and args.prior_attempts != 0:
        parser.error('--prior-attempts is accepted only with --prepare; later stages read the frozen preparation record')
    state = args.state_dir.resolve()
    if args.prepare:
        prepare(state, args.prior_attempts)
    else:
        input_files(state)
        if args.tests: tests(state)
        elif args.smoke: model_phase(state, 'smoke')
        elif args.control: model_phase(state, 'control')
        elif args.main: model_phase(state, 'main')
        elif args.collect: collect(state)
        elif args.cleanup: cleanup(state)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'launchgate selection stage failed: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
