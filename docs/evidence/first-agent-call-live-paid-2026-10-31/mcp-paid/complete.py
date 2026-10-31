"""Redeem one already-mined MCP invoice and test replay rejection. No signing/broadcast."""
from pathlib import Path
import json
import httpx
from aimarket_agent.receipts import verify_receipt
R=Path(__file__).resolve().parent
P=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
if (R/'paid-response.json').exists():raise SystemExit('MCP paid attempt recorded; inspect it instead of invoking again')
private=json.loads(P.read_text());quote=private['mcp_paid_quote'];j=json.loads((R/'payment-journal.json').read_text())
args={**private['mcp_invoke_args'],'x_payment':j['transaction_hash'],'x_payment_nonce':quote['nonce'],'x_payment_secret':quote['payment_secret']}
request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'market_invoke','arguments':args}}
def save(name,d):
 text=json.dumps(d,ensure_ascii=False,indent=2).replace(quote['payment_secret'],'[REDACTED]')
 (R/name).write_text(text+'\n')
with httpx.Client(timeout=45) as c:
 def call():
  r=c.post('https://modelmarket.dev/mcp',json=request);r.raise_for_status()
  return r.json() if 'application/json' in r.headers.get('content-type','') else json.loads(next(x[6:] for x in r.text.splitlines() if x.startswith('data: ')))
 response=call();save('paid-response.json',{'request':request,'response':response})
 payload=json.loads(response['result']['content'][0]['text']);save('paid-delivery.json',payload);save('paid-receipt.json',payload.get('receipt'))
 key=json.loads((R.parent/'provider-well-known.json').read_text())['body']['signer_public_key']
 checks={'paid_mcp_success':not response['result'].get('isError'),'weather_delivered':bool(payload.get('output',{}).get('reading',{}).get('values')),'provider_receipt_verified':bool(verify_receipt(payload.get('receipt'),key))}
 assert all(checks.values()),checks
 replay=call();save('same-payment-replay.json',replay)
 replay_payload=json.loads(replay['result']['content'][0]['text'])
 checks['same_settled_payment_rejected_on_replay']=replay['result'].get('isError') is True
 assert checks['same_settled_payment_rejected_on_replay'],replay_payload
 save('checks.json',checks)
 print(json.dumps(checks));print('MCP paid receipt:',payload['receipt']['nonce'])
