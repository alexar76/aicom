from pathlib import Path
import json,datetime
import httpx
ROOT=Path(__file__).resolve().parent

def save(name,value):
 (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
with httpx.Client(timeout=35) as c:
 for name,url in [('hub-well-known.json','https://modelmarket.dev/.well-known/ai-market.json'),('provider-well-known.json','https://iot.modelmarket.dev/.well-known/ai-market.json'),('agent-card.json','https://modelmarket.dev/.well-known/agent-card.json')]:
  r=c.get(url);r.raise_for_status();save(name,{'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'url':url,'body':r.json()})
 wk=json.loads((ROOT/'hub-well-known.json').read_text())['body']
 print('Payment configuration:',json.dumps({k:v for k,v in wk.items() if any(s in k for s in ['credit','topup','payment','trial'])},ensure_ascii=False))
 addresses=['0x097e3F339D0b023605e12A6B81E2d6Cb7571475a','0x4B838FEC0f6B0Bf493A612ce281F903AADC9f092','0xfDd37A6f8c62Ad321f733EE4356c78c6023D42b7']
 rows=[]
 for address in addresses:
  def rpc(method,params):
   resp=c.post('https://mainnet.base.org',json={'jsonrpc':'2.0','id':1,'method':method,'params':params});resp.raise_for_status();d=resp.json();
   if 'error' in d: raise RuntimeError(d['error'])
   return d['result']
  row={'address':address,'chain_id':int(rpc('eth_chainId',[]),16),'eth_wei':str(int(rpc('eth_getBalance',[address,'latest']),16)),'usdc_atomic':str(int(rpc('eth_call',[{'to':'0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913','data':'0x70a08231'+address[2:].lower().zfill(64)},'latest']),16))}
  rows.append(row);print(json.dumps(row))
 save('wallet-public-preflight.json',{'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wallets':rows})
