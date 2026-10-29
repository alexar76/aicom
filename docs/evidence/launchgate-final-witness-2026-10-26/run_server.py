"""Linux supervisor; only the tested host-local relay receives a key/network."""
from datetime import datetime,timezone
from hashlib import sha256
import json,os,subprocess,sys,time
from pathlib import Path
from host_relay import Relay,read_regular,validate_request

IMAGE='sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
def now():return datetime.now(timezone.utc).isoformat()
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def put(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def append(path,value):
 with path.open('a') as f:f.write(canonical(value)+'\n');f.flush();os.fsync(f.fileno())
def main():
 assert sys.platform=='linux';root=Path(sys.argv[1]);study=root/'study';out=root/'out'
 assert root.parent==Path('/tmp') and root.name.startswith('warden-final-witness-')
 out.mkdir();os.chown(out,65532,65532)
 manifest=json.loads((root/'input-manifest.json').read_text())
 for name,meta in manifest.items():assert sha256((study/name).read_bytes()).hexdigest()==meta['sha256'],name
 slots=json.loads((study/'slots.json').read_text())
 plan={'schema':'final-witness-plan/1','startedAt':now(),'slots':slots,'protocolSha256':sha256((study/'protocol.md').read_bytes()).hexdigest(),
  'freezeSha256':sha256((study/'freeze.json').read_bytes()).hexdigest(),'inputManifest':manifest,'model':'deepseek-flash','budgetUSD':.08,'maxFreshCalls':120,'temperature':.3,'maxTokens':700,'maxCorrections':0}
 plan['planId']=sha256(canonical(plan).encode()).hexdigest();put(out/'frozen-before-api.json',plan)
 record={'startedAt':now(),'host':'factory-vps','image':IMAGE,'runtime':'runc','runtimeNetwork':'none','modelRelayNetwork':'fixed official endpoint',
  'model':'deepseek-flash','budgetUSD':.08,'maxFreshCalls':120,'plannedFailure':80,'plannedValidControls':40,'completed':False,'checks':[],'githubWrites':False,'npmPublished':False}
 name=root.name+'-runner'
 def docker(entry='node',interactive=False):
  cmd=['docker','run','--rm']
  if interactive:cmd+=['-i','--name',name]
  return cmd+['--runtime','runc','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--network','none','--user','65532:65532',
   '--memory','768m','--cpus','2','--pids-limit','96','--tmpfs','/tmp:rw,nosuid,noexec,size=64m','-v',str(study)+':/study:ro','-v',str(out)+':/out:rw',
   '--workdir','/study','-e','PYTHONDONTWRITEBYTECODE=1','--entrypoint',entry,IMAGE]
 def check(label,command):
  with (out/(label+'.log')).open('wb') as log:code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
  record['checks'].append({'name':label,'exitCode':code,'logSha256':sha256((out/(label+'.log')).read_bytes()).hexdigest()});put(out/'execution.json',record)
  print(json.dumps({'stage':label,'exitCode':code}),flush=True);assert code==0,label
 relay=None;process=None
 try:
  check('study-tests',docker()+['--test','test_study.mjs'])
  check('relay-collection-tests',docker('python3')+['-B','-m','unittest','-v','test_host_relay','test_budget','test_collection'])
  # Bound every known base/repair request before reading a key or dispatching calls.
  check('request-preflight',docker()+['preflight.mjs'])
  for line in (out/'preflight-requests.jsonl').read_text().splitlines():validate_request(json.loads(line),'deepseek-flash')
  key=read_regular(Path('/root/claudecode/aicom/data/secrets/llm/deepseek_api_key'),8192).decode().strip()
  relay=Relay(out/'relay',key,'deepseek-flash',max_calls=120,workers=1,timeout=60,budget_nanousd=80_000_000);key=None
  record['apiStartedAt']=now();put(out/'execution.json',record)
  stderr=(out/'worker.log').open('w')
  process=subprocess.Popen(docker(interactive=True)+['worker.mjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1)
  errors=0;calls=0;started=time.monotonic()
  for line in process.stdout:
   event=json.loads(line);assert time.monotonic()-started<2400,'wall deadline'
   if event['event']=='call':
    rid=event['requestId'];assert len(rid)==32 and all(c in '0123456789abcdef' for c in rid)
    raw=canonical(event['body']);validate_request(event['body'],'deepseek-flash')
    append(out/'intents.jsonl',{'requestId':rid,'slotId':event['slotId'],'attempt':event['attempt'],'requestSha256':sha256(raw.encode()).hexdigest(),'at':now()})
    path=relay.req/(rid+'.json')
    with path.open('x') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    response=relay.process(path);assert response is not None
    decoded={'requestId':rid,'status':'error','answer':''}
    if response['status']=='ok':
     p=response['provider_response'];assert p['model'] in ['deepseek-flash','deepseek-v4.1-flash-1017'],'unexpected model'
     choices=p['choices']
     if len(choices)==1 and choices[0].get('finish_reason')=='stop' and not choices[0].get('message',{}).get('tool_calls') and isinstance(choices[0]['message'].get('content'),str):
      decoded.update(status='ok',answer=choices[0]['message']['content'])
    errors=errors+1 if decoded['status']!='ok' else 0;calls+=1
    process.stdin.write(canonical(decoded)+'\n');process.stdin.flush()
    if response.get('error',{}).get('code') in ['dollar_budget_exhausted','budget_exhausted'] or errors>=3:raise RuntimeError('stop_after_budget_or_errors')
   elif event['event']=='trajectory':
    if event['completed']%8==0:print(json.dumps({'stage':'model',**{k:v for k,v in event.items() if k!='event'},'apiAttempts':relay.attempts,'heldUpperUSD':relay.held_nanousd/1e9}),flush=True)
   else:raise RuntimeError('unexpected worker event')
  code=process.wait(timeout=30);stderr.close();assert code==0,'worker failed'
  complete=json.loads((out/'worker-complete.json').read_text());assert complete['completed']==120
  record.update(completed=True,trajectories=120)
 except BaseException as error:
  record['failureType']=type(error).__name__;print(json.dumps({'stage':'failure','type':type(error).__name__}),flush=True);raise
 finally:
  if process is not None and process.poll() is None:
   subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30);process.wait(timeout=30)
  if relay is not None:record.update(apiAttempts=relay.attempts,heldUpperUSD=relay.held_nanousd/1e9);relay.close()
  record['finishedAt']=now();put(out/'execution.json',record)
 print(json.dumps({'stage':'complete','apiAttempts':record['apiAttempts'],'heldUpperUSD':record['heldUpperUSD']}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as error:print(json.dumps({'fatalType':type(error).__name__}),flush=True);sys.exit(1)
