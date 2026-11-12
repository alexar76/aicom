"""Public Base chain reads only via one owned SSH host; no credentials or mutations."""
import json
from pathlib import Path
import subprocess

CODE = r'''
import json,time,urllib.request
TX='0x47a095061a12704908f1c4b012ab55bab348b5050d272ed9f1b0fd3e2ff4a541'
PAYER='0x097e3F339D0b023605e12A6B81E2d6Cb7571475a'
out={'transaction_hash':TX,'expected_payer_nonce':27,'expected_amount_atomic':2000,'financial_mutations':0,'credential_reads':0,'checked_server_unix':time.time(),'public_rpc_attempts':[]}
def rpc(url,method,params):
    raw=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    request=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json','User-Agent':'AIMarket-PublicReceiptCheck/1.0'})
    with urllib.request.urlopen(request,timeout=10) as response:
        body=response.read(1000001)
    if len(body)>1000000:raise ValueError('RPC response bound')
    document=json.loads(body)
    if 'error' in document:raise ValueError('Public RPC error')
    return document['result']
for url in ['https://base-rpc.publicnode.com','https://mainnet.base.org']:
    attempt={'public_endpoint':url}
    out['public_rpc_attempts'].append(attempt)
    try:
        chain=int(rpc(url,'eth_chainId',[]),16)
        if chain!=8453:raise ValueError('Wrong public chain')
        receipt=rpc(url,'eth_getTransactionReceipt',[TX])
        tx=rpc(url,'eth_getTransactionByHash',[TX])
        head=int(rpc(url,'eth_blockNumber',[]),16)
        attempt.update(chain_id=chain,receipt=receipt,transaction=tx,head_number=head)
        if receipt:
            block=rpc(url,'eth_getBlockByNumber',[receipt['blockNumber'],False])
            attempt['mined_block']={k:block[k] for k in ['number','hash','timestamp']}
            attempt['confirmations']=max(0,head-int(receipt['blockNumber'],16)+1)
        attempt['payer_latest_nonce']=int(rpc(url,'eth_getTransactionCount',[PAYER,'latest']),16)
        attempt['payer_pending_nonce']=int(rpc(url,'eth_getTransactionCount',[PAYER,'pending']),16)
        attempt['ok']=True
        break
    except Exception as exc:
        attempt.update(ok=False,error_type=type(exc).__name__)
print(json.dumps(out))
'''

result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=12',
                         '-o', 'StrictHostKeyChecking=yes', 'indep', 'python3', '-'],
                        input=CODE, capture_output=True, text=True, timeout=110)
if result.returncode:
    raise SystemExit('Public-chain remote read failed; SSH diagnostic not persisted')
document = json.loads(result.stdout)
document['read_only_host'] = 'indep'
target = Path(__file__).resolve().parents[1] / 'factory-chain-rescue.json'
target.write_text(json.dumps(document, indent=2) + '\n')
print(json.dumps({'saved': str(target), 'attempts': [{k:v for k,v in item.items()
      if k in ['public_endpoint','ok','error_type','confirmations','payer_latest_nonce','payer_pending_nonce']}
      for item in document['public_rpc_attempts']]}))
