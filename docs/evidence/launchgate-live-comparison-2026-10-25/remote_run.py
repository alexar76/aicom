#!/usr/bin/env python3
"""Own temporary Linux study supervisor. No credential values enter evidence."""
import argparse,fcntl,hashlib,json,os
from pathlib import Path
import re,signal,subprocess,sys,time
from datetime import datetime,timezone

IMAGE='sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
KEY='/root/claudecode/aicom/data/secrets/llm/deepseek_api_key'
MODEL='deepseek-flash'
TESTS=['test/'+x for x in ['action.test.ts','annotation-review.test.ts','claude-plugin.test.ts',
 'flow-guard-answer-review.test.ts','flow-guard-credential-boundary.test.ts','flow-guard-gaps.test.ts',
 'flow-guard-gautam.test.ts','flow-guard-gui-policy.test.ts','flow-guard-home-paths.test.ts',
 'flow-guard-instructions.test.ts','flow-guard-screen.test.ts','flow-guard-secret-regression.test.ts',
 'flow-guard.test.ts','mcp-client.test.ts','pin-review-origin.test.ts','result-screen.test.ts',
 'review-diff.test.ts','toxic-flow.test.ts','wrap-screen.test.ts','wrap.test.ts']]
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
def run():
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args()
 root=Path(args.root);assert re.fullmatch(r'/tmp/launchgate-live-20261025\.[A-Za-z0-9]{6}',str(root)) and root.is_dir() and not root.is_symlink()
 lock=(root/'.supervisor.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 study=root/'study';project=study/'project';research=study/'research';out=root/'out';out.mkdir(mode=0o700)
 manifest=json.loads((root/'input-manifest.json').read_text())
 def verify():
  for n,m in manifest.items():
   if n.startswith('project/claude-plugin/scripts/flow-guard'):continue
   assert sha(study/n)==m['sha256'],n
  return len(manifest)
 def container(entry='node',network='none',interactive=False,readonly_out=False):
  return ['docker','run','--rm',*(['-i'] if interactive else []),'--runtime','runc','--read-only','--cap-drop','ALL',
   '--security-opt','no-new-privileges','--network',network,'--memory','1536m','--memory-swap','1536m',
   '--cpus','2','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,noexec,size=256m','--user','65532:65532',
   '-v',str(project)+':/work:rw','-v',str(research)+':/study:ro','-v',str(root/'baseline/package')+':/published:ro',
   '-v',str(project)+':/candidate:ro','-v',str(out)+':/out:'+('ro' if readonly_out else 'rw'),
   '--workdir','/work','-e','HOME=/tmp/warden-home','-e','WARDEN_STATE_DIR=/tmp/warden-state',
   '-e','PYTHONDONTWRITEBYTECODE=1','-e','WARDEN_TEST_ROOT=/published','-e','npm_config_cache=/tmp/npm-cache','--entrypoint',entry,IMAGE]
 # project rw and candidate ro are two paths to the same own sources; no secret mount.
 for directory,_,files in os.walk(project):
  os.chown(directory,65532,65532)
  for name in files:os.chown(Path(directory)/name,65532,65532)
 os.chmod(root,0o755);os.chown(out,65532,65532)
 record={'startedAt':now(),'host':'factory-vps','platform':sys.platform,'python':sys.version,
  'nodeImage':json.loads(subprocess.check_output(['docker','image','inspect',IMAGE]))[0]['Id'],
  'sourceInputs':verify(),'model':MODEL,'budgetUSD':1,'attemptCap':1100,'phases':[],'checks':[]}
 assert record['nodeImage']==IMAGE
 put(out/'execution.json',record)
 def check(name,command,timeout=300):
  item={'name':name,'startedAt':now(),'command':command};record['checks'].append(item);put(out/'execution.json',record)
  print(json.dumps({'stage':name,'startedAt':now()}),flush=True)
  with (out/(name+'.log')).open('wb') as log:
   item['exitCode']=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
  item['finishedAt']=now();put(out/'execution.json',record)
  print(json.dumps({'stage':name,'exitCode':item['exitCode']}),flush=True)
  assert item['exitCode']==0,'Check failed: '+name
 check('dependencies',container('npm','bridge')+['ci','--ignore-scripts','--no-audit','--no-fund'])
 check('build',container('npm')+['run','build'])
 check('typecheck',container('npm')+['run','typecheck'])
 check('warden-tests',container()+['node_modules/vitest/vitest.mjs','run',*TESTS,'--maxWorkers=1','--no-file-parallelism',
  '--reporter=default','--reporter=json','--outputFile.json=/out/vitest.json'],600)
 check('redteam',container()+['scripts/redteam/flow-redteam.mjs','/out/redteam.json','--check'])
 py=['/usr/bin/python3','-B','-m','unittest','-v','test_host_relay','test_budget','test_experiment','test_comparison','test_analyze','test_ties']
 with (out/'study-tests.log').open('wb') as log:
  result=subprocess.run(py,cwd=research,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=300)
 record['checks'].append({'name':'study-tests','command':py,'exitCode':result.returncode});put(out/'execution.json',record)
 print(json.dumps({'stage':'study-tests','exitCode':result.returncode}),flush=True);assert result.returncode==0
 check('adapter-tests',container()+['--test','/study/test_guard_probe.mjs'])
 candidate={'packageName':'@aimarket/warden','version':'0.22.0','kind':'local-0.22.0-unpublished-full-hook-parts',
  'files':{'package.json':sha(project/'package.json'),**{str(p.relative_to(project)):sha(p) for p in sorted((project/'dist').glob('flow-guard*.js'))}}}
 put(out/'candidate-runtime.json',candidate);(out/'candidate-runtime.json').chmod(0o644)
 guard=container(interactive=True,readonly_out=True)+['/study/guard_probe.mjs','--warden-root','/published']
 candidate_guard=container(interactive=True,readonly_out=True)+['/study/guard_probe.mjs','--warden-root','/candidate','--runtime-manifest','/out/candidate-runtime.json']
 relay_root=out/'relay';relay_root.mkdir(mode=0o700)
 relay_command=['/usr/bin/python3','-B',str(research/'host_relay.py'),'--root',str(relay_root),'--key-file',KEY,
  '--model',MODEL,'--max-calls','1100','--workers','1','--timeout','60']
 relay=None
 try:
  with (out/'relay-host.log').open('wb') as log:
   relay=subprocess.Popen(relay_command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
   deadline=time.monotonic()+10
   while not (relay_root/'budget-config.json').exists():
    assert relay.poll() is None and time.monotonic()<deadline;time.sleep(.1)
   for phase,expected in [('smoke',5),('control',30),('main',720)]:
    verify();target=out/phase;assert not target.exists()
    fixture=research/('control-fixtures.json' if phase=='control' else 'fixtures.json')
    command=['/usr/bin/python3','-B',str(research/'experiment.py'),'--fixtures',str(fixture),'--out',str(target),
     '--relay',str(relay_root),'--model',MODEL,'--expected-model',MODEL,'--repeats','8','--phase',phase,
     '--guard-command',json.dumps(guard),'--candidate-guard-command',json.dumps(candidate_guard)]
    item={'phase':phase,'startedAt':now(),'command':command,'expectedSlots':expected};record['phases'].append(item);put(out/'execution.json',record)
    target.mkdir()
    with (target/'runner.log').open('wb') as log:
     child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
     end=time.monotonic()+(300 if phase=='smoke' else 3600)
     try:
      while child.poll() is None:
       assert relay.poll() is None,'Relay died'
       if time.monotonic()>end:raise TimeoutError('Phase deadline')
       path=target/'runs.jsonl';count=len(path.read_text().splitlines()) if path.exists() else 0
       ledger=relay_root/'usage.jsonl';events=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
       held=events[-1].get('held_upper_nanousd_after',0) if events else 0
       print(json.dumps({'stage':phase,'completed':count,'scheduled':expected,'attempts':sum(x['event']=='reserved' for x in events),'upperUSD':held/1e9}),flush=True)
       time.sleep(20)
     except BaseException:
      os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=20);raise
    item['exitCode']=child.returncode;item['finishedAt']=now();put(out/'execution.json',record)
    assert child.returncode==0,'Runner failed'
    rows=[json.loads(x) for x in (target/'runs.jsonl').read_text().splitlines()]
    assert len(rows)==expected,'Incomplete planned phase'
    # Mechanical smoke only. No target-selection or control-success gate/tuning.
    if phase=='smoke':
     sys.path.insert(0,str(research));from analyze import parse_selection
     f={x['id']:x for x in json.loads(fixture.read_text())['fixtures']}
     assert all(r['status']=='ok' and r['response_model']==MODEL and r['finish_reason']=='stop' and not r['continuation_calls'] and parse_selection(r['answer'],f[r['fixture_id']])[2] is None for r in rows)
    analysis=['/usr/bin/python3','-B',str(research/'analyze.py'),'--fixtures',str(fixture),
     '--results',str(target/'runs.jsonl'),'--schedule',str(target/'schedule.json'),'--out',str(target/'analysis.json')]
    with (target/'analysis.log').open('wb') as log:
     assert subprocess.run(analysis,stdout=log,stderr=subprocess.STDOUT,timeout=300,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}).returncode==0
    item['recordedSlots']=len(rows);item['continuationCalls']=sum(r['continuation_calls'] for r in rows);put(out/'execution.json',record)
    print(json.dumps({'stage':phase,'complete':True,'recordedSlots':len(rows),'continuations':item['continuationCalls']}),flush=True)
 finally:
  (relay_root/'stop').touch()
  if relay is not None:
   try:record['relayExitCode']=relay.wait(timeout=75)
   except subprocess.TimeoutExpired:os.killpg(relay.pid,signal.SIGTERM);record['relayExitCode']=relay.wait(timeout=15)
  record['finishedAt']=now();record['sourceInputsVerifiedAfter']=verify();put(out/'execution.json',record)
 assert record['relayExitCode']==0
 record['completed']=True;put(out/'execution.json',record)
 print(json.dumps({'stage':'complete','finishedAt':now()}),flush=True)

if __name__=='__main__':run()
