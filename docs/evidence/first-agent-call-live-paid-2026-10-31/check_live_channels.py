"""Live read/validation checks and fresh quotes. No wallet or signing in this file."""
from pathlib import Path
import datetime,json,os
import httpx
from aimarket_agent import A2AClient
from aimarket_agent.a2a import task_receipt,task_state,payment_required
from aimarket_agent.receipts import verify_receipt
R=Path(__file__).resolve().parent
P=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
private=json.loads(P.read_text());secrets={private['api_key']}

def discover_secrets(d):
 if isinstance(d,dict):
  for k,v in d.items():
   if k in ('payment_secret','x_payment_secret','api_key') and isinstance(v,str):secrets.add(v)
   discover_secrets(v)
 elif isinstance(d,list):
  for v in d:discover_secrets(v)
 elif isinstance(d,str):
  try: nested=json.loads(d)
  except (ValueError,TypeError):return
  if not isinstance(nested,str):discover_secrets(nested)
def save(name,d):
 discover_secrets(d);text=json.dumps(d,ensure_ascii=False,indent=2)
 for s in secrets:
  if s:text=text.replace(s,'[REDACTED]')
 (R/name).write_text(text+'\n')
def private_save():
 fd=os.open(P,os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(private,f)
checks={}
with A2AClient('https://modelmarket.dev') as a:
 original=json.loads((R/'payment-journal.json').read_text())
 old=a.get_task(original['task_id']);save('original-paid-task-reverified.json',old)
 assert old['receipt_verified'];checks['original_paid_receipt_verified_with_fixed_sdk']=True
 # No repeat charge: GetTask is a read, returning the saved old null result.
 matches=a.search('gaia weather open-meteo',budget=0.01,limit=10)['matches']
 offer=next(x for x in matches if x['capability_id']=='gaia.weather.read@v1' and x['product_id']=='gaia.gateway')
 save('postfix-offer.json',offer)
 quote=a.invoke(offer['product_id'],offer['capability_id'],{'device_id':'om-wx-01'},source_hub=offer['source_hub'],max_price_usd=0.01,message_id='first-agent-call-fixed-paid-20261031')
 save('postfix-payment-required-task.json',quote)
 if task_state(quote)=='TASK_STATE_COMPLETED' and not quote.get('artifacts'):
  quote=a.get_task(quote['id'])
  save('postfix-trial-readback.json',quote)
 if task_state(quote)=='TASK_STATE_COMPLETED':
  assert quote['receipt_verified']
  checks['a2a_postfix_trial_delivers_weather']=True
  for attempt in range(1,6):
   quote=a.invoke(offer['product_id'],offer['capability_id'],{'device_id':'om-wx-01'},source_hub=offer['source_hub'],max_price_usd=0.01,message_id=f'first-agent-call-fixed-paid-20261031-{attempt}')
   save(f'postfix-trial-or-quote-{attempt}.json',quote)
   if payment_required(quote):break
 assert payment_required(quote) and task_state(quote)=='TASK_STATE_INPUT_REQUIRED'
 save('postfix-payment-required-task.json',quote)
 private['payment_task']=quote;private_save();checks['a2a_fresh_payment_quote']=True
with httpx.Client(timeout=40) as h:
 def rpc(method,params,headers=None):
  r=h.post('https://modelmarket.dev/mcp',headers={'Accept':'application/json',**(headers or {})},json={'jsonrpc':'2.0','id':1,'method':method,'params':params});r.raise_for_status();return r.json() if 'application/json' in r.headers.get('content-type','') else json.loads(next(line[6:] for line in r.text.splitlines() if line.startswith('data: ')))
 init=rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'operator-channel-audit','version':'1'}});save('mcp-initialize.json',init);assert 'result' in init
 tools=rpc('tools/list',{});save('mcp-tools.json',tools);assert {'market_search','market_invoke'}<={t['name'] for t in tools['result']['tools']};checks['mcp_initialize_tools']=True
 search=rpc('tools/call',{'name':'market_search','arguments':{'intent':'gaia weather open-meteo','budget':0.01,'limit':5}});save('mcp-search.json',search);assert not search['result'].get('isError');checks['mcp_search']=True
 invalid=rpc('tools/call',{'name':'market_invoke','arguments':{'product_id':'gaia.gateway'}});save('mcp-invalid-arguments.json',invalid);assert invalid.get('error') or invalid.get('result',{}).get('isError');checks['mcp_invalid_arguments']=True
 args={'product_id':offer['product_id'],'capability_id':offer['capability_id'],'source_hub':offer['source_hub'],'input':{'device_id':'om-wx-01'},'max_price_usd':0,'include_full_receipt':True}
 cap=rpc('tools/call',{'name':'market_invoke','arguments':args});save('mcp-price-cap.json',cap);assert cap.get('error') or cap.get('result',{}).get('isError');checks['mcp_price_cap_rejected']=True
 args['max_price_usd']=0.01
 quote=rpc('tools/call',{'name':'market_invoke','arguments':args});save('mcp-payment-required.json',quote)
 private['mcp_invoke_args']=args;private['mcp_quote']=quote;private_save()
 r=h.post('https://modelmarket.dev/a2a',headers={'A2A-Version':'9.9'},json={'jsonrpc':'2.0','id':1,'method':'GetTask','params':{'id':old['id']}});save('a2a-invalid-version.json',r.json());assert r.json()['error']['code']==-32009;checks['a2a_invalid_version']=True
 r=h.post('https://modelmarket.dev/a2a',headers={'A2A-Version':'1.0'},json={'jsonrpc':'2.0','id':1,'method':'SendMessage','params':{'message':{'messageId':'invalid-limit-audit','role':'ROLE_USER','parts':[{'data':{'intent':'weather','limit':21}}]}}});save('a2a-invalid-limit.json',r.json());assert r.json()['error']['code']==-32602;checks['a2a_invalid_limit']=True
save('live-initial-checks.json',checks)
print(json.dumps(checks));print('MCP payment response saved; private invoice secret excluded from evidence.')
