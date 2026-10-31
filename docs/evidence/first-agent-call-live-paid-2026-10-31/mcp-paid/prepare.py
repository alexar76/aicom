from pathlib import Path
import json,os
import httpx
R=Path(__file__).resolve().parent
P=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
if (R/'payment-journal.json').exists():raise SystemExit('Already paid; never create a replacement invoice')
private=json.loads(P.read_text());args=private['mcp_invoke_args']
request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'market_invoke','arguments':args}}
with httpx.Client(timeout=45) as c:
 r=c.post('https://modelmarket.dev/mcp',json=request);r.raise_for_status()
 answer=r.json() if 'application/json' in r.headers.get('content-type','') else json.loads(next(x[6:] for x in r.text.splitlines() if x.startswith('data: ')))
 body=json.loads(answer['result']['content'][0]['text'])
 assert answer['result'].get('isError') and body['error']=='payment_required'
 offer=body['accepts'][0]
 assert offer['network']=='base' and offer['maxAmountRequired']=='1000'
 terms={'x402Version':2,'nonce':body['nonce'],'accepts':[{**offer,'network':'eip155:8453','amount':offer['maxAmountRequired']}]}
 private['mcp_paid_quote']=body
 private['payment_task']={'id':'mcp-call-first-agent-paid-20261031','status':{'state':'TASK_STATE_INPUT_REQUIRED','message':{'metadata':{'x402.payment.required':terms}}}}
 fd=os.open(P,os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:json.dump(private,f)
 public=json.dumps({'response':answer,'normalized_terms_for_signing':terms},ensure_ascii=False,indent=2).replace(body['payment_secret'],'[REDACTED]')
 (R/'payment-required.json').write_text(public+'\n')
 print('MCP invoice prepared: 0.001 USDC; payment secret retained only in private state.')
