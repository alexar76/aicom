"""Run the actual example against one settled invoice; record result and safe replay."""
from pathlib import Path
import contextlib,io,json,os,runpy,sys
from aimarket_agent import A2AClient
from aimarket_agent.a2a import task_result,task_receipt
R=Path(__file__).resolve().parent
ROOT=R.parents[3]
j=json.loads((R/'payment-journal.json').read_text())
os.environ.pop('AIMARKET_KEY',None)
rows=[];completed=None
class Recorder(A2AClient):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self.session.event_hooks['response']=[self.record]
 def record(self,r):
  r.read();q=r.request
  rows.append({'method':q.method,'url':str(q.url),'request_body':json.loads(q.content) if q.content else None,'status_code':r.status_code,'response_body':r.json()})
 def pay_x402(self,*a,**kw):
  global completed
  completed=super().pay_x402(*a,**kw);return completed
 def get_task(self,*a,**kw):
  global completed
  task=super().get_task(*a,**kw)
  if task.get('status',{}).get('state')=='TASK_STATE_COMPLETED':completed=task
  return task
module=runpy.run_path(str(ROOT/'aimarket-hub/examples/first-agent-call.py'))
module['main'].__globals__['A2AClient']=Recorder
sys.argv=['first-agent-call.py','--task-id',j['task_id'],'--payment-tx',j['transaction_hash']]
log=io.StringIO()
with contextlib.redirect_stdout(log):exit_code=module['main']()
(R/'example.stdout.txt').write_text(log.getvalue())
(R/'example-http.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
(R/'paid-task.json').write_text(json.dumps(completed,ensure_ascii=False,indent=2)+'\n')
(R/'paid-receipt.json').write_text(json.dumps(task_receipt(completed),ensure_ascii=False,indent=2)+'\n')
assert exit_code==0 and completed['receipt_verified'] and task_result(completed)['reading']['device_id']=='om-wx-01'
rows.clear();log2=io.StringIO()
with contextlib.redirect_stdout(log2):replay_code=module['main']()
(R/'example-replay-http.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
assert replay_code==0 and not any((r.get('request_body') or {}).get('method')=='SendMessage' for r in rows)
(R/'checks.json').write_text(json.dumps({'actual_example_exit':exit_code,'receipt_verified':completed['receipt_verified'],'weather_delivered':True,'same_cli_replay_exit':replay_code,'same_cli_replay_does_not_send_message_or_pay':True},indent=2)+'\n')
print(log.getvalue());print('Same CLI replay: no SendMessage, no new payment.')
