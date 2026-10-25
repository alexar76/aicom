"""Verify the user-executed payment/refund. All RPC methods are read-only."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_utils import keccak

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / 'manual-esim-cycle-2026-10-23'
TOKEN = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
TRANSFER = '0x' + keccak(text='Transfer(address,address,uint256)').hex()
AUTH_USED = '0x' + keccak(text='AuthorizationUsed(address,bytes32)').hex()
BALANCE_OF = '0x70a08231'
AUTH_STATE = '0x' + keccak(text='authorizationState(address,bytes32)').hex()[:8]
ALLOWED = {'eth_chainId','eth_getTransactionReceipt','eth_getBlockByNumber','eth_getLogs','eth_call','eth_getBalance'}
CHECKS = []


def check(name, condition, **details):
    result = {'check':name,'ok':bool(condition),**details}
    CHECKS.append(result)
    print(json.dumps(result),flush=True)
    return bool(condition)


class Rpc:
    def __init__(self):
        source = r'''import json,os,sys,time,httpx
allowed={'eth_chainId','eth_getTransactionReceipt','eth_getBlockByNumber','eth_getLogs','eth_call','eth_getBalance'}
url=os.environ['KOVA_URL'].rstrip('/')+'/v1/chains/base'
with httpx.Client(timeout=25,headers={'X-API-Key':os.environ['KOVA_API_KEY'],'User-Agent':'attested-saas-gateway/1'}) as client:
 for line in sys.stdin:
  payload=json.loads(line)
  assert payload['method'] in allowed
  for attempt in range(16):
   try:
    response=client.post(url,json=payload)
    if response.status_code==429:
     time.sleep(4); continue
    if response.status_code!=200: body={'error':{'http':response.status_code}}
    else: body=response.json()
    if body.get('error',{}).get('code') in {-32005,-32000} and attempt<5:
     time.sleep(1);continue
    break
   except httpx.HTTPError:
    body={'error':'read-only RPC unavailable'}
    if attempt<2:time.sleep(1);continue
    break
  else: body={'error':'read-only RPC rate limit'}
  print(json.dumps(body),flush=True)
'''
        command = ['docker','exec','-i','aicom-saas-gateway-1','python','-u','-c',source]
        self.process = subprocess.Popen(['ssh','-o','BatchMode=yes','attested',shlex.join(command)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        self.cache = {}
        self.provider_notes = []

    def call(self, method, params):
        assert method in ALLOWED
        key = json.dumps([method,params],sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        if method != 'eth_getLogs':
            for provider in ['https://mainnet.base.org','https://base.drpc.org','https://base-rpc.publicnode.com']:
                try:
                    request=urllib.request.Request(provider,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),
                      headers={'Content-Type':'application/json','User-Agent':'aicom-readonly-payment-audit/20261023'})
                    with urllib.request.urlopen(request,timeout=12) as response: body=json.load(response)
                    if not body.get('error') and 'result' in body:
                        self.cache[key]=body['result']
                        return body['result']
                except Exception:
                    pass
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})+'\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line: raise RuntimeError('Read-only RPC connection closed')
        result = json.loads(line)
        if result.get('error'):
            self.provider_notes.append({'method':method,'error':result['error']})
            raise RuntimeError(method+': '+str(result['error']))
        self.cache[key] = result['result']
        return result['result']

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)


def address(topic):
    return '0x'+topic[-40:].lower()


def transfers(logs):
    return [{'from':address(x['topics'][1]),'to':address(x['topics'][2]),'units':int(x['data'],16),
             'transaction':x.get('transactionHash'),'block':int(x['blockNumber'],16)}
            for x in logs if x.get('address','').lower()==TOKEN and len(x.get('topics',[]))==3
            and x['topics'][0].lower()==TRANSFER]


def auth_used(logs, payer, nonce):
    return sum(x.get('address','').lower()==TOKEN and len(x.get('topics',[]))==3
               and x['topics'][0].lower()==AUTH_USED and address(x['topics'][1])==payer
               and x['topics'][2].lower()==nonce.lower() for x in logs)


def verify_signature(public_key, value):
    public_key.verify(base64.b64decode(value['receipt_signature']),json.dumps(value['receipt'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())


def main():
    production=json.loads((HERE/'production-evidence.json').read_text())
    statement_path=HERE/'supplier-statement-verification.json'
    statement=json.loads(statement_path.read_text()) if statement_path.exists() else {}
    statement_verified=statement.get('status')=='verified' and statement.get('net_supplier_loss_verified') is True
    delivery=json.loads((INPUT/'delivery.json').read_text())['delivery']
    refund=json.loads((INPUT/'refund-result.json').read_text())['result']
    refund_nonce=refund.get('refund_nonce') or refund['receipt']['refund_nonce']
    public_key=Ed25519PublicKey.from_public_bytes(base64.b64decode(production['health']['provider_pubkey']))
    verify_signature(public_key,delivery)
    verify_signature(public_key,refund)
    check('delivery_and_refund_receipt_signatures_valid',True)
    payer=delivery['receipt']['payer'].lower()
    merchant=delivery['receipt']['pay_to'].lower()
    amount=int(Decimal(production['order']['priceUsd'])*1000000)
    check('same_order_amount_payer_and_nonce',delivery['esim_tran_no']==refund['esim_tran_no']==production['order']['profileId']
          and production['order']['nonce']==delivery['receipt']['nonce']==refund['receipt']['delivery_nonce']
          and payer==production['order']['payer'].lower()==refund['to'].lower()
          and merchant==refund['receipt']['refund_from'].lower()
          and amount==int(Decimal(refund['amount_usd'])*1000000)==310000)
    rpc=Rpc()
    try:
        check('base_mainnet',int(rpc.call('eth_chainId',[]),16)==8453)
        paid=rpc.call('eth_getTransactionReceipt',[production['order']['settlement']['tx']])
        returned=rpc.call('eth_getTransactionReceipt',[refund['transaction']])
        (HERE/'payment-receipt.json').write_text(json.dumps(paid,indent=2)+'\n')
        (HERE/'refund-receipt.json').write_text(json.dumps(returned,indent=2)+'\n')
        check('both_transactions_successful',int(paid['status'],16)==int(returned['status'],16)==1)
        pb=int(paid['blockNumber'],16); rb=int(returned['blockNumber'],16)
        finalized=rpc.call('eth_getBlockByNumber',['finalized',False])
        payment_block=rpc.call('eth_getBlockByNumber',[hex(pb),False])
        refund_block=rpc.call('eth_getBlockByNumber',[hex(rb),False])
        latest=rpc.call('eth_getBlockByNumber',['latest',False])
        check('both_transactions_canonical_and_confirmed',paid['blockHash']==payment_block['hash']
              and returned['blockHash']==refund_block['hash'] and pb<=rb and int(latest['number'],16)-rb+1>=3,
              refund_confirmations=int(latest['number'],16)-rb+1)
        finality={'both_finalized':rb<=int(finalized['number'],16),'finalized_block':int(finalized['number'],16),
                  'payment_block':pb,'refund_block':rb,'latest_block':int(latest['number'],16)}
        print(json.dumps({'finality':finality}),flush=True)
        incoming=[t for t in transfers(paid['logs']) if t['from']==payer]
        outgoing=[t for t in transfers(returned['logs']) if t['from']==merchant]
        check('exactly_one_payment_and_full_refund',len(incoming)==len(outgoing)==1
              and incoming[0]['to']==merchant and incoming[0]['units']==amount
              and outgoing[0]['to']==payer and outgoing[0]['units']==amount)
        check('authorization_nonces_used_once',auth_used(paid['logs'],payer,production['order']['nonce'])==1
              and auth_used(returned['logs'],merchant,refund_nonce)==1)
        start=pb-1;end=rb+1
        all_out=[];all_in=[]
        for lo in range(start,end+1,40):
            hi=min(end,lo+39)
            for kind,topics in [('out',[TRANSFER,'0x'+payer[2:].rjust(64,'0')]),('in',[TRANSFER,None,'0x'+payer[2:].rjust(64,'0')])]:
                logs=rpc.call('eth_getLogs',[{'address':TOKEN,'fromBlock':hex(lo),'toBlock':hex(hi),'topics':topics}])
                (all_out if kind=='out' else all_in).extend(transfers(logs))
        check('no_extra_buyer_usdc_transfers_during_cycle',len(all_out)==len(all_in)==1
              and all_out[0]['units']==all_in[0]['units']==amount
              and all_out[0]['transaction'].lower()==paid['transactionHash'].lower()
              and all_in[0]['transaction'].lower()==returned['transactionHash'].lower(),outgoing_count=len(all_out),incoming_count=len(all_in),from_block=start,to_block=end)
        balances={}
        for name,wallet in [('buyer',payer),('merchant',merchant)]:
            balances[name]={}
            for tag,block in [('before',hex(pb-1)),('after',hex(rb))]:
                value=rpc.call('eth_call',[{'to':TOKEN,'data':BALANCE_OF+wallet[2:].rjust(64,'0')},block])
                eth=rpc.call('eth_getBalance',[wallet,block])
                balances[name][tag]={'usdc_units':int(value,16),'eth_wei':int(eth,16)}
            check(name+'_balances_restored',balances[name]['before']==balances[name]['after'],
                  usdc_before=str(Decimal(balances[name]['before']['usdc_units'])/1000000),
                  usdc_after=str(Decimal(balances[name]['after']['usdc_units'])/1000000),
                  eth_delta_wei=balances[name]['after']['eth_wei']-balances[name]['before']['eth_wei'])
        check('gas_paid_by_other_transaction_senders',paid['from'].lower() not in {payer,merchant}
              and returned['from'].lower() not in {payer,merchant})
        for name,wallet,nonce in [('payment',payer,production['order']['nonce']),('refund',merchant,refund_nonce)]:
            state=rpc.call('eth_call',[{'to':TOKEN,'data':AUTH_STATE+wallet[2:].rjust(64,'0')+nonce[2:]},'latest'])
            check(name+'_nonce_consumed_onchain',int(state,16)==1)
        check('one_production_order_one_refund_ledger_entry',len(production['same_payer_orders_since_test'])==1
              and len(production['refund_budget_entries'])==1
              and production['refund_budget_entries'][0]['status']=='refunded'
              and production['refund_budget_entries'][0]['result']['transaction'].lower()==returned['transactionHash'].lower())
        check('supplier_profile_cancelled_unused',len(production['profiles'])==1
              and production['profiles'][0]['state']=='CANCEL'
              and production['profiles'][0]['installed'] is False
              and production['profiles'][0]['dataUsedBytes']==0
              and not production['profiles'][0]['activated'] and production['order']['released'] is True)
        check('exactly_one_supplier_profile_for_order',production['supplier_order_profiles_count']==1
              and production['supplier_financial_fields'][0]['transactionId']==production['order']['transactionId'])
        summary={'checked_at_unix':time.time(),'profile':production['order']['profileId'],'offer_id':production['order']['offerId'],
                 'amount_usdc':str(Decimal(amount)/1000000),'payment_tx':paid['transactionHash'],'refund_tx':returned['transactionHash'],
                 'payment_time_utc':datetime.fromtimestamp(int(payment_block['timestamp'],16),timezone.utc).isoformat(),
                 'refund_time_utc':datetime.fromtimestamp(int(refund_block['timestamp'],16),timezone.utc).isoformat(),
                 'balances':balances,'finality':finality,'supplier_balance_usd':production['supplier_balance_usd'],'wholesale_cost_usd':production['order']['costUsd'],
                 'supplier_statement_verified':statement_verified,
                 'supplier_financial_limit':None if statement_verified else 'No immediately-before-test supplier balance snapshot or supplier transaction statement is available; cancellation and current balance are independently queried.',
                 'checks':CHECKS,'all_checks_passed':all(x['ok'] for x in CHECKS),'new_transfers_sent_by_assistant':0,'github_writes':False}
        (HERE/'verification-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'all_checks_passed':summary['all_checks_passed'],'checks':len(CHECKS),'payment_tx':summary['payment_tx'],'refund_tx':summary['refund_tx']}),flush=True)
        if not summary['all_checks_passed']:
            raise AssertionError('One or more production payment checks failed; inspect verification-summary.json')
    finally:
        rpc.close()


if __name__=='__main__':
    try:
        main()
    finally:
        (HERE/'checks-progress.json').write_text(json.dumps(CHECKS,indent=2)+'\n')
