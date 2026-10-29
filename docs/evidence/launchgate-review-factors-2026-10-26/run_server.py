"""Own Linux supervisor: tested host-local relay; credential never mounted or collected."""
from datetime import datetime,timezone
from hashlib import sha256
import json,os,subprocess,sys,time
from pathlib import Path

from host_relay import Relay,read_regular
from constraint_claims import host_check
from study import schedule,body,decode,digest,canonical,ARMS,review_for

IMAGE='sha256:a85c8ea75b21b6031dd94f06fcb70aa8366956133a0a6ea4f81c64c6b5424fd2'
def now():return datetime.now(timezone.utc).isoformat()
def put(p,v):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def append(p,v):
 with p.open('a') as f:f.write(canonical(v)+'\n');f.flush();os.fsync(f.fileno())
def main():
 assert sys.platform=='linux'
 root=Path(sys.argv[1]);study=root/'study';out=root/'out';assert root.parent==Path('/tmp') and root.name.startswith('warden-review-factors-')
 record={'startedAt':now(),'model':'deepseek-flash','budgetUSD':.12,'attemptCap':384,'host':'factory-vps','runtimeNetwork':'none','modelRelayNetwork':'fixed official endpoint','checks':[],'newModelRun':True,'completed':False}
 out.mkdir();os.chown(out,65532,65532)
 manifest=json.loads((root/'input-manifest.json').read_text())
 for name,m in manifest.items():assert sha256((study/name).read_bytes()).hexdigest()==m['sha256'],name
 def docker(entry='node'):
  return ['docker','run','--rm','--runtime','runc','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--network','none','--user','65532:65532','--memory','1536m','--cpus','2','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,noexec,size=256m','-v',str(study)+':/study:ro','-v',str(out)+':/out:rw','--workdir','/study','-e','PYTHONDONTWRITEBYTECODE=1','--entrypoint',entry,IMAGE]
 def check(name,command):
  with (out/(name+'.log')).open('wb') as log:code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
  record['checks'].append({'name':name,'exitCode':code,'logSha256':sha256((out/(name+'.log')).read_bytes()).hexdigest()});put(out/'execution.json',record)
  print(json.dumps({'stage':name,'exitCode':code}),flush=True);assert code==0,name
 relay=None
 try:
  check('instrument-tests',docker('python3')+['-B','-m','unittest','-v','test_study','test_host_relay','test_budget','test_collection'])
  original=json.loads((study/'cases.json').read_text());cases=original['cases'];work=[]
  for c in cases:
   contract,coverage=host_check(c['initial_answer'],c['fixture'],'prepare',1)
   work.append({**c,'initial_check':contract,'initial_coverage':coverage})
  put(out/'workcases.json',{'cases':work})
  check('prepare-hooks',docker()+['/study/guard.mjs','prepare','/out/workcases.json','/out/prepared.json'])
  prepared={r['pair_id']:r for r in json.loads((out/'prepared.json').read_text())['results']}
  reference={r['pair_id']:r for r in json.loads((study/'baseline-reviews.json').read_text())['results']}
  for c in work:
   assert prepared[c['pair_id']]['new_facts']['reason']==reference[c['pair_id']]['new_facts']['reason']
   # The two revised requests differ only where the deterministic checker supplies evidence.
   assert prepared[c['pair_id']]['new_plain']['decision']=='block' and prepared[c['pair_id']]['new_facts']['decision']=='block'
  reviews={c['pair_id']:{arm:review_for(c,prepared[c['pair_id']]['new_facts']['reason'],arm) for arm in ARMS} for c in work}
  put(out/'treatment-messages.json',reviews)
  slots=schedule(work)
  plan={'schema':'fresh-recheck-plan/1','startedAt':now(),'custodySha256':sha256((study/'custody.md').read_bytes()).hexdigest(),'protocolSha256':sha256((study/'protocol.md').read_bytes()).hexdigest(),'inputManifest':manifest,'slots':slots,'arms':list(ARMS),'repetitions':8,'attempts':384,'model':'deepseek-flash','temperature':.3,'maxTokens':700,'budgetUSD':.12}
  put(out/'frozen-before-api.json',plan)
  plan_sha=digest(plan);cmap={c['pair_id']:c for c in work}
  queue=out/'relay'
  key=read_regular(Path('/root/claudecode/aicom/data/secrets/llm/deepseek_api_key'),8192).decode().strip()
  relay=Relay(queue,key,'deepseek-flash',max_calls=384,workers=1,timeout=60,budget_nanousd=120_000_000)
  key=None
  record['apiStartedAt']=now();record['frozenPlanSha256']=plan_sha;put(out/'execution.json',record)
  errors=0;started=time.monotonic();rows=[]
  for index,slot in enumerate(slots):
   assert time.monotonic()-started<1800,'wall deadline'
   c=cmap[slot['pair_id']];review=review_for(c,prepared[c['pair_id']]['new_facts']['reason'],slot['arm']);request=body(c,review)
   rid=digest({'planSha256':plan_sha,'slot':slot})[:32]
   path=queue/'req'/(rid+'.json');assert not path.exists()
   intent={'slot':slot,'requestId':rid,'requestSha256':digest(request)};append(out/'intents.jsonl',intent)
   with path.open('x') as f:f.write(canonical(request));f.flush();os.fsync(f.fileno())
   response=relay.process(path);decoded=decode(response)
   row={'slot_id':rid,**slot,**decoded,'answer_sha256':digest(decoded['answer']),'requestSha256':digest(request),'request_id':rid,'apiResponse':response,'review_sha256':digest(review),'finishedAt':now()}
   append(out/'runs.jsonl',row);rows.append(row)
   errors=errors+1 if row['status']!='ok' else 0
   if (index+1)%12==0 or row['status']!='ok':print(json.dumps({'stage':'model','completed':index+1,'planned':384,'errors':sum(r['status']!='ok' for r in rows),'heldUpperUSD':relay.held_nanousd/1e9}),flush=True)
   if row['status']=='model_mismatch':raise RuntimeError('unexpected_model')
   if errors>=3:raise RuntimeError('three_consecutive_errors')
  record['apiFinishedAt']=now();record['attempts']=relay.attempts;record['heldUpperUSD']=relay.held_nanousd/1e9
  final_rows=[]
  for row in rows:
   c=cmap[row['pair_id']];check_value=None;coverage='not-examined'
   if row['status']=='ok':
    try:check_value,coverage=host_check(row['answer'],c['fixture'],'prepare',1)
    except (ValueError,KeyError,TypeError):coverage='unsupported-grammar; unknown'
   final_rows.append({**{k:v for k,v in row.items() if k!='apiResponse'},'final_check':check_value,'final_coverage':coverage})
  put(out/'final-check-input.json',{'rows':final_rows})
  check('final-hook-replay',docker()+['/study/guard.mjs','final','/out/workcases.json','/out/final-check-input.json','/out/final-hooks.json'])
  record['completed']=True;record['recordedSlots']=len(rows)
 except BaseException as error:
  record['failureType']=type(error).__name__
  print(json.dumps({'stage':'failure','type':type(error).__name__}),flush=True)
  raise
 finally:
  if relay is not None:record['attempts']=relay.attempts;record['heldUpperUSD']=relay.held_nanousd/1e9;relay.close()
  record['finishedAt']=now();put(out/'execution.json',record)
 print(json.dumps({'stage':'complete','attempts':record['attempts'],'heldUpperUSD':record['heldUpperUSD']}),flush=True)

if __name__=='__main__':
 try:main()
 except BaseException as error:
  print(json.dumps({'fatalType':type(error).__name__}),flush=True);sys.exit(1)
