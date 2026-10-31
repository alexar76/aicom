"""Record the real example's public request/response bodies; never log API keys."""
from pathlib import Path
import contextlib,datetime,io,json,os,runpy,sys
import httpx
from aimarket_agent import A2AClient
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[2]
PRIVATE=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
LABEL=os.getenv('AICOM_EXAMPLE_LABEL','original')
if LABEL not in ('original','postfix-credit'):raise SystemExit('Unknown recording label')
PREFIX='' if LABEL=='original' else LABEL+'-'
if (ROOT/(PREFIX+'example-execution.json')).exists():raise SystemExit('Recorded execution exists; refuse another invoke')

def save(name,value):
 (ROOT/(PREFIX+name)).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def private_save(d):
 fd=os.open(PRIVATE,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f: json.dump(d,f)

if not PRIVATE.exists():
 with httpx.Client(timeout=35) as c:
  r=c.post('https://modelmarket.dev/ai-market/v2/accounts',json={'label':'operator-integration-test-first-agent-call-2026-10-31'})
  r.raise_for_status();account=r.json()
  if not account.get('api_key'): raise RuntimeError('signup did not return key')
  private_save(account)
  save('account-created-redacted.json',{k:v for k,v in account.items() if k!='api_key'})
secret=json.loads(PRIVATE.read_text())
os.environ['AIMARKET_KEY']=secret['api_key']
class RecordedClient(A2AClient):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.session.event_hooks['response']=[self.record]
 def record(self,response):
  response.read();request=response.request
  try: body=json.loads(request.content) if request.content else None
  except Exception: body=None
  try: answer=response.json()
  except Exception: answer={'text':response.text}
  rows.append({'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':request.method,'url':str(request.url),'request_body':body,'status_code':response.status_code,'response_body':answer})
  save('example-http.json',rows)
 def invoke(self,*args,**kwargs):
  task=super().invoke(*args,**kwargs);save('example-task.json',task)
  d=json.loads(PRIVATE.read_text());d['task']=task;private_save(d)
  return task
rows=[]
module=runpy.run_path(str(WORKSPACE/'aimarket-hub/examples/first-agent-call.py'))
module['main'].__globals__['A2AClient']=RecordedClient
sys.argv=['first-agent-call.py','--invoke']
log=io.StringIO()
with contextlib.redirect_stdout(log):
 exit_code=module['main']()
(ROOT/(PREFIX+'example.stdout.txt')).write_text(log.getvalue())
save('example-execution.json',{'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':exit_code,'script':'aimarket-hub/examples/first-agent-call.py','args':['--invoke'],'local_sdk':'aimarket-agent','live_network':True})
print(log.getvalue());print('Example exit:',exit_code)
