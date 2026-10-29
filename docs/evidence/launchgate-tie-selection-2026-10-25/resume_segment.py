#!/usr/bin/env python3
"""Continue the same frozen plan after its controlled helper-lifetime boundary.

Orchestration only on the local computer; model/guard/scoring execution on Linux.
Does not reset requests, rewrite rows, change fixtures or retry paid attempts.
"""
from pathlib import Path
import hashlib
import json
import run_linux as orchestration

STATE = Path(__file__).resolve().parent / "linux-run"
BODY = r'''
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
'''


def main():
    receipt = {"orchestratorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "purpose": "same-plan resume at helper lifetime boundary"}
    orchestration.save(STATE / "resume-orchestrator.json", receipt)
    try:
        orchestration.ssh(STATE, orchestration.script_for(STATE, BODY), "resume-main")
    finally:
        orchestration.collect(STATE)


if __name__ == "__main__":
    main()
