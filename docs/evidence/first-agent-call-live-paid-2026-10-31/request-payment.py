"""Exercise the example's anonymous trial until the hub quotes its first paid call.

At most six attempts: five advertised trial slots and one payment challenge.
No transaction is signed or sent here.
"""
from pathlib import Path
import contextlib,datetime,io,json,os,runpy,sys,time
from aimarket_agent import A2AClient
from aimarket_agent.a2a import payment_required,task_state
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[2]
PRIVATE=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
os.environ.pop('AIMARKET_KEY',None)
rows=[];latest=None
class Recorder(A2AClient):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self.session.event_hooks['response']=[self.record]
 def record(self,r):
  r.read();q=r.request
  rows.append({'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':q.method,'url':str(q.url),'request_body':json.loads(q.content) if q.content else None,'status_code':r.status_code,'response_body':r.json()})
  (ROOT/'anonymous-example-http.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 def invoke(self,*a,**kw):
  global latest
  latest=super().invoke(*a,**kw);return latest
for n in range(1,7):
 module=runpy.run_path(str(WORKSPACE/'aimarket-hub/examples/first-agent-call.py'))
 module['main'].__globals__['A2AClient']=Recorder
 sys.argv=['first-agent-call.py','--invoke'];log=io.StringIO()
 with contextlib.redirect_stdout(log): code=module['main']()
 (ROOT/f'anonymous-example-{n}.stdout.txt').write_text(log.getvalue())
 (ROOT/f'anonymous-example-{n}.task.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
 print('attempt',n,'exit',code,'state',task_state(latest or {}),flush=True)
 if payment_required(latest or {}):
  d=json.loads(PRIVATE.read_text());d['payment_task']=latest
  fd=os.open(PRIVATE,os.O_WRONLY|os.O_TRUNC,0o600)
  with os.fdopen(fd,'w') as f:json.dump(d,f)
  (ROOT/'payment-required-task.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
  print('Quoted:',json.dumps(payment_required(latest)),flush=True)
  break
 if task_state(latest or {})!='TASK_STATE_COMPLETED':raise SystemExit('Unexpected state; stop before payment')
 time.sleep(1)
else:raise SystemExit('No payment quote after advertised trial slots; stop')
