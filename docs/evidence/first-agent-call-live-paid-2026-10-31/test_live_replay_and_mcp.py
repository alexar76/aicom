"""Existing-task replay, credit accounting and MCP live delivery; no blockchain writes."""
from pathlib import Path
import json
import httpx
from aimarket_agent import A2AClient
from aimarket_agent.a2a import task_receipt,task_result
from aimarket_agent.receipts import verify_receipt
R=Path(__file__).resolve().parent
private=json.loads(Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json').read_text())
key=private['api_key'];checks={}
if (R/'mcp-credit-delivery.json').exists():raise SystemExit('MCP credit execution already recorded; do not invoke twice')
def save(name,d):(R/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
with httpx.Client(timeout=45) as h:
 def account():
  r=h.get('https://modelmarket.dev/ai-market/v2/account',headers={'X-API-Key':key});r.raise_for_status();return r.json()
 before=account();save('credit-account-before-channel-checks.json',before)
 # Replay exactly the successful authenticated example's original SendMessage.
 rows=json.loads((R/'postfix-credit-example-http.json').read_text())
 request=next(x['request_body'] for x in rows if (x.get('request_body') or {}).get('method')=='SendMessage' and 'invoke' in str(x['request_body']))
 r=h.post('https://modelmarket.dev/a2a',headers={'X-API-Key':key,'A2A-Version':'1.0'},json=request);r.raise_for_status();again=r.json()['result']['task'];save('a2a-credit-idempotent-replay.json',again)
 original=json.loads((R/'postfix-credit-example-task.json').read_text())
 after=account();save('credit-account-after-a2a-replay.json',after)
 checks['a2a_same_message_same_task']=again['id']==original['id']
 checks['a2a_same_message_no_second_charge']=after['balance_usd']==before['balance_usd'] and after['spent_usd']==before['spent_usd']
 def mcp(args,api=key):
  r=h.post('https://modelmarket.dev/mcp',headers={'X-API-Key':api},json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'market_invoke','arguments':args}});r.raise_for_status()
  return r.json() if 'application/json' in r.headers.get('content-type','') else json.loads(next(x[6:] for x in r.text.splitlines() if x.startswith('data: ')))
 args=private['mcp_invoke_args'];data=mcp(args);save('mcp-credit-invoke.json',data)
 payload=json.loads(data['result']['content'][0]['text']);save('mcp-credit-delivery.json',payload)
 checks['mcp_credit_delivery_success']=not data['result'].get('isError') and bool(payload['output']['reading']['values'])
 provider=json.loads((R/'provider-well-known.json').read_text())['body']['signer_public_key']
 checks['mcp_credit_receipt_verified']=bool(verify_receipt(payload['receipt'],provider))
 after_mcp=account();save('credit-account-after-mcp.json',after_mcp)
 checks['mcp_exact_credit_charge']=round(before['balance_usd']-after_mcp['balance_usd'],6)==0.001
 bad=mcp(args,api='invalid-key-channel-audit');save('mcp-invalid-key.json',bad);checks['mcp_invalid_key_rejected']=bad.get('result',{}).get('isError') is True
 # Replay the already settled x402 follow-up, with its identical message ID.
 j=json.loads((R/'payment-journal.json').read_text());prior=json.loads((R/'fresh-payment-required-task.json').read_text())
 with A2AClient('https://modelmarket.dev') as a:
  paid=a.pay_x402(prior,j['transaction_hash'],message_id='first-agent-call-paid-20261031-once')
  save('a2a-original-paid-idempotent-replay.json',paid)
  checks['a2a_x402_replay_same_task']=paid['id']==j['task_id']
  checks['a2a_x402_replay_receipt_verified']=paid['receipt_verified']
 assert all(checks.values()),checks
 save('live-replay-and-credit-checks.json',checks)
 print(json.dumps(checks))
