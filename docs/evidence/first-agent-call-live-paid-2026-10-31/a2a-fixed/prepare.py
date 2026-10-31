from pathlib import Path
import json,os
from aimarket_agent import A2AClient
from aimarket_agent.a2a import payment_required,task_state
R=Path(__file__).resolve().parent
P=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
if (R/'payment-journal.json').exists():raise SystemExit('Already paid: never prepare a replacement')
with A2AClient('https://modelmarket.dev') as client:
 offers=client.search('gaia weather open-meteo',budget=0.01,limit=10)['matches']
 offer=next(m for m in offers if m['product_id']=='gaia.gateway' and m['capability_id']=='gaia.weather.read@v1')
 (R/'selected-offer.json').write_text(json.dumps(offer,ensure_ascii=False,indent=2)+'\n')
 task=client.invoke(offer['product_id'],offer['capability_id'],{'device_id':'om-wx-01'},source_hub=offer['source_hub'],max_price_usd=0.01,message_id='first-agent-call-explicitly-approved-a2a-20261031')
 (R/'prepared-task.json').write_text(json.dumps(task,ensure_ascii=False,indent=2)+'\n')
 assert task_state(task)=='TASK_STATE_INPUT_REQUIRED' and payment_required(task),task_state(task)
 secret=json.loads(P.read_text());secret['payment_task']=task
 fd=os.open(P,os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(secret,f)
 print('Prepared same-order payment challenge:',task['id'])
