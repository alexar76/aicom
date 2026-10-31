"""One explicit Base-mainnet x402 settlement; no automatic re-signing or re-payment.

Private keys remain in the wallet process. Evidence excludes keys, raw signed
transactions, and API keys. Re-running after the journal exists is refused.
"""
from pathlib import Path
from decimal import Decimal
import asyncio,datetime,email.utils,importlib,json,os,sys,time
from types import SimpleNamespace
import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from aimarket_agent import A2AClient
from aimarket_agent.a2a import payment_required,task_receipt,task_state,task_result
from aimarket_agent.topup import typed_data,calldata
from aimarket_hub.native_price import native_price
ROOT=Path(__file__).resolve().parent
order=os.getenv('AICOM_PAYMENT_ORDER','original')
if order not in ('original','a2a-fixed','mcp-paid'):raise SystemExit('Unknown audit order')
R=ROOT if order=='original' else ROOT/order
R.mkdir(exist_ok=True)
P=Path('/private/tmp/aimarket-first-agent-call-live-paid-20261031.private.json')
RPC='https://mainnet.base.org'
TOKEN='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
PAYEE='0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a'
PAYER='0x097e3F339D0b023605e12A6B81E2d6Cb7571475a'
JOURNAL=R/'payment-journal.json'

def save(name,d):
 (R/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
if JOURNAL.exists():raise SystemExit('Prior payment journal exists: inspect saved transaction, never re-sign.')
http=httpx.Client(timeout=35)
def rpc(method,params):
 r=http.post(RPC,json={'jsonrpc':'2.0','id':1,'method':method,'params':params});r.raise_for_status();d=r.json()
 if 'error' in d:raise RuntimeError(str(d['error']))
 return d['result']
def balance(address):
 return int(rpc('eth_call',[{'to':TOKEN,'data':'0x70a08231'+address[2:].lower().zfill(64)},'latest']),16)
async def price():
 async with httpx.AsyncClient(timeout=20) as c:
  async def arpc(client,url,method,params):
   r=await client.post(url,json={'jsonrpc':'2.0','id':1,'method':method,'params':params});r.raise_for_status();d=r.json()
   if 'error' in d:raise RuntimeError(str(d['error']))
   return d['result']
  return await native_price(c,RPC,arpc)
# The host clock is ahead of all live endpoints. Keep production freshness checks;
# supply this audit process with agreeing HTTPS time and monotonic elapsed time.
clock_samples=[]
for url in ['https://api.coinbase.com/v2/time','https://modelmarket.dev/ai-market/v2/health']:
 r=http.get(url);r.raise_for_status()
 stamp=email.utils.parsedate_to_datetime(r.headers['date']).timestamp()
 if 'coinbase.com' in url and abs(stamp-r.json()['data']['epoch'])>2:raise RuntimeError('Coinbase time disagreement')
 clock_samples.append({'url':url,'server_unix':stamp,'host_unix':time.time()})
if abs(clock_samples[0]['server_unix']-clock_samples[1]['server_unix'])>10:raise RuntimeError('Network time disagreement')
clock_epoch=max(r['server_unix'] for r in clock_samples);clock_tick=time.monotonic()
def trusted_now():return clock_epoch+time.monotonic()-clock_tick
importlib.import_module('aimarket_hub.native_price').time=SimpleNamespace(time=trusted_now)
save('payment-clock-check.json',{'samples':clock_samples,'method':'HTTPS Date agreement; monotonic elapsed; independent Base block/feed freshness validation retained'})
a2a=A2AClient('https://modelmarket.dev')
try:
 task=json.loads(P.read_text())['payment_task']
 if order != 'mcp-paid': task=a2a.resume(task) # Refresh the same invoice before signing.
 save('fresh-payment-required-task.json',task)
 terms=payment_required(task)
 if not terms or task_state(task)!='TASK_STATE_INPUT_REQUIRED':raise RuntimeError('Task is not waiting for payment')
 offer=terms['accepts'][0];extra=offer['extra'];amount=int(offer['amount'])
 if (offer['scheme']!='exact' or offer['network']!='eip155:8453' or offer['asset'].lower()!=TOKEN.lower() or offer['payTo'].lower()!=PAYEE.lower() or amount!=1000):raise RuntimeError('Unexpected payment terms')
 if extra['name']!='USD Coin' or str(extra['version'])!='2':raise RuntimeError('Unexpected signing domain')
 if int(rpc('eth_chainId',[]),16)!=8453:raise RuntimeError('Wrong chain')
 price_check=asyncio.run(price());ceiling=Decimal(price_check['native_usd_ceiling'])
 before={'payer_usdc_atomic':str(balance(PAYER)),'payee_usdc_atomic':str(balance(PAYEE)),'payer_eth_wei':str(int(rpc('eth_getBalance',[PAYER,'latest']),16))}
 if int(before['payer_usdc_atomic'])<amount:raise RuntimeError('Insufficient USDC')
 secret=json.loads((Path.home()/'.aicom-pov-buyer.json').read_text());account=Account.from_key(secret.pop('private_key'));secret.clear()
 if account.address.lower()!=PAYER.lower():raise RuntimeError('Wrong buyer wallet')
 topup_shape={'nonce':extra['nonce'],'accepts':[{**offer,'extra':{**extra,'chainId':8453,'verifyingContract':TOKEN}}]}
 typed=typed_data(topup_shape,sender=PAYER,valid_before=int(trusted_now())+240)
 signed_auth=account.sign_message(encode_typed_data(full_message=typed)).signature.hex()
 data=calldata(typed,signed_auth)
 gas_est=int(rpc('eth_estimateGas',[{'from':PAYER,'to':TOKEN,'data':data}]),16)
 gas=(gas_est*125+99)//100
 price_wei=int(rpc('eth_gasPrice',[]),16)
 priority=min(price_wei,1000000);maxfee=2*price_wei
 l1=int(rpc('eth_call',[{'to':'0x420000000000000000000000000000000000000F','data':'0x'+keccak(text='getL1FeeUpperBound(uint256)')[:4].hex()+format(1024,'064x')},'latest']),16)
 bound_wei=gas*maxfee+100*l1
 bound_usd=Decimal(amount)/10**6+Decimal(bound_wei)/10**18*ceiling
 save('payment-budget.json',{'at_utc':now(),'service_usdc':str(Decimal(amount)/10**6),'max_total_usd':'0.01','native_price':price_check,'gas_limit':gas,'max_fee_per_gas_wei':str(maxfee),'l1_fee_upper_bound_wei':str(l1),'l1_safety_multiplier':100,'l1_upper_bound_transaction_bytes':1024,'fee_bound_wei':str(bound_wei),'conservative_total_usd':str(bound_usd),'balance_before':before})
 if bound_usd>Decimal('0.01') or int(before['payer_eth_wei'])<bound_wei:raise RuntimeError('Conservative all-in budget exceeds $0.01 or insufficient ETH')
 tx={'chainId':8453,'nonce':int(rpc('eth_getTransactionCount',[PAYER,'pending']),16),'to':TOKEN,'value':0,'data':data,'gas':gas,'maxFeePerGas':maxfee,'maxPriorityFeePerGas':priority,'type':2}
 signed=account.sign_transaction(tx)
 if len(signed.raw_transaction)>1024:raise RuntimeError('Signed transaction exceeds L1 estimate size bound')
 txhash='0x'+keccak(signed.raw_transaction).hex()
 journal={'at_utc':now(),'task_id':task['id'],'chain_id':8453,'payer':PAYER,'payee':PAYEE,'asset':TOKEN,'amount_atomic':str(amount),'authorization_nonce':extra['nonce'],'transaction_hash':txhash,'broadcast_attempted':True}
 # Exclusive creation before broadcast prevents a second authorization on rerun.
 fd=os.open(JOURNAL,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
 with os.fdopen(fd,'w') as f:json.dump(journal,f,indent=2);f.write('\n')
 sent=rpc('eth_sendRawTransaction',['0x'+signed.raw_transaction.hex()])
 if sent.lower()!=txhash.lower():raise RuntimeError('RPC returned another hash')
 print('Broadcast:',txhash,flush=True)
 receipt=None
 for _ in range(30):
  receipt=rpc('eth_getTransactionReceipt',[txhash])
  if receipt and int(rpc('eth_blockNumber',[]),16)>=int(receipt['blockNumber'],16)+2:break
  time.sleep(2)
 else:raise RuntimeError('Confirmations pending; use saved transaction, never re-pay')
 save('chain-transaction-receipt.json',receipt)
 if int(receipt['status'],16)!=1:raise RuntimeError('Payment transaction reverted')
 save('chain-transaction.json',rpc('eth_getTransactionByHash',[txhash]))
 save('wallet-balances-after.json',{'at_utc':now(),'payer_usdc_atomic':str(balance(PAYER)),'payee_usdc_atomic':str(balance(PAYEE)),'payer_eth_wei':str(int(rpc('eth_getBalance',[PAYER,'latest']),16))})
 if os.getenv('AICOM_BROADCAST_ONLY')=='1':
  print('Settlement confirmed; resume the saved order with this same transaction.',flush=True)
  sys.exit(0)
 def record(r):
  r.read();save('paid-a2a-http.json',{'at_utc':now(),'url':str(r.request.url),'request_body':json.loads(r.request.content) if r.request.content else None,'status_code':r.status_code,'response_body':r.json()})
 a2a.session.event_hooks['response']=[record]
 paid=a2a.pay_x402(task,txhash,message_id='first-agent-call-paid-20261031-once')
 save('paid-task.json',paid)
 save('paid-receipt.json',task_receipt(paid))
 print(json.dumps({'state':task_state(paid),'receipt_verified':paid.get('receipt_verified'),'receipt_verify_reason':paid.get('receipt_verify_reason'),'result_is_null':task_result(paid) is None,'tx_hash':txhash}))
finally:
 a2a.close();http.close()
