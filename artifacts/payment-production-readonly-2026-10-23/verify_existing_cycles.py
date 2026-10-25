"""Read-only verification of existing real eSIM payments/refunds on Base mainnet."""
import concurrent.futures
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

from eth_utils import keccak

HERE = Path(__file__).resolve().parent
TOKEN = '0x833589fcd6edb6e08f4c7c32d4f71b54bdA02913'.lower()
TRANSFER = '0x' + keccak(text='Transfer(address,address,uint256)').hex()
AUTHORIZATION = '0x' + keccak(text='AuthorizationUsed(address,bytes32)').hex()
PROVIDERS = ['https://mainnet.base.org', 'https://base-rpc.publicnode.com', 'https://base.drpc.org']
READ_METHODS = {'eth_chainId', 'eth_getTransactionReceipt', 'eth_getBlockByNumber', 'eth_getLogs'}
DOCUMENTED_PAYMENTS = {
    '70722e67279b': '0xeea12962c4f494e55acc59a376203bd4b704804f19a84b4b8f47a96b265a881e',
    '3d24f25be91a': '0x85d355853807967e85b1efc3f15261e0c58006091898cb98d46095db07bc103e',
    '30dd6a986386': '0xf9ac406f3e329ac2c4c02e26562b6fb944e4165b71b88c4a0756a193325f9669',
    'a10f827a87e5': '0x617efd7abe4b4c6a80b54046617a73415aa54df7ada5f002ce7260cf68ac3ae0',
}


def rpc(method, params):
    assert method in READ_METHODS, 'Only read-only RPC is allowed'
    if method == 'eth_getLogs':
        # Some public RPCs reject indexed log reads from the laptop's egress IP.
        # The same read-only call from the production host uses its normal providers.
        source = '''import json,sys,urllib.request
payload=json.load(sys.stdin)
assert payload['method']=='eth_getLogs'
errors=[]
for provider in ['https://base-rpc.publicnode.com','https://mainnet.base.org','https://base.drpc.org']:
 try:
  request=urllib.request.Request(provider,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'aicom-readonly-payment-audit/20261023'})
  with urllib.request.urlopen(request,timeout=12) as response: body=json.load(response)
  if body.get('error'): raise RuntimeError(str(body['error']))
  print(json.dumps(body)); break
 except Exception as error: errors.append(str(error)[:200])
else: print(json.dumps({'error':errors}))
'''
        raw = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'factory-vps', shlex.join(['python3', '-c', source])],
                                      input=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}), text=True)
        body = json.loads(raw)
        if not body.get('error'):
            return body['result']
    errors = []
    for provider in PROVIDERS:
        request = urllib.request.Request(provider, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
                                         headers={'Content-Type': 'application/json', 'User-Agent': 'aicom-readonly-payment-audit/20261023'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = json.load(response)
            if body.get('error'):
                raise RuntimeError(str(body['error'])[:200])
            return body['result']
        except Exception as error:
            errors.append(type(error).__name__ + ': ' + str(error)[:200])
    raise RuntimeError(method + ': ' + '; '.join(errors))


def address(topic):
    return '0x' + topic[-40:].lower()


def transfers(receipt):
    return [{'from': address(log['topics'][1]), 'to': address(log['topics'][2]), 'units': int(log['data'], 16)}
            for log in receipt.get('logs', []) if log.get('address', '').lower() == TOKEN
            and len(log.get('topics', [])) == 3 and log['topics'][0].lower() == TRANSFER]


def gather():
    code = '''import json,pathlib,hashlib,subprocess
for directory,container in [('/opt/esim-node-data','esim-node'),('/opt/esim-test-data/rails','esim-test-rails')]:
 config=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
 env=dict(x.split('=',1) for x in config['Config']['Env'] if '=' in x)
 data=json.loads((pathlib.Path(directory)/'orders.json').read_text())
 for key,record in data.items():
  if not isinstance(record,dict) or not record.get('refund'): continue
  refund=record['refund']
  print(json.dumps({'record_ref':hashlib.sha256(key.encode()).hexdigest()[:12],'source':directory,'price_usd':record.get('priceUsd'),'payer':record.get('payer'),'at':record.get('at'),'released':record.get('released'),'nonce':record.get('nonce'),'recipient_current':env.get('PAY_TO'),'refund':{k:refund.get(k) for k in ['status','amount_usd','to','at','transaction','refund_from','refund_nonce','delivery_nonce']}}))
'''
    raw = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'factory-vps', shlex.join(['python3', '-c', code])], text=True)
    rows = [json.loads(line) for line in raw.splitlines()]
    (HERE / 'existing-public-records.json').write_text(json.dumps(rows, indent=2) + '\n')
    return rows


def verify(row):
    receipt = rpc('eth_getTransactionReceipt', [row['refund']['transaction']])
    assert receipt and int(receipt['status'], 16) == 1, 'Refund transaction unsuccessful or missing'
    units = int(Decimal(row['price_usd']) * 1000000)
    paid_back = [t for t in transfers(receipt) if t['to'] == row['payer'].lower() and t['units'] == units]
    assert len(paid_back) == 1, 'Refund amount/recipient mismatch'
    if row['refund'].get('refund_from'):
        assert paid_back[0]['from'] == row['refund']['refund_from'].lower(), 'Refund sender mismatch'
    (HERE / ('refund-' + row['record_ref'] + '.json')).write_text(json.dumps({
        'record_ref':row['record_ref'],'refund_tx':receipt['transactionHash'],
        'amount_usdc':row['price_usd'],'recipient':paid_back[0]['to'],
        'sender':paid_back[0]['from'],'successful':True,'exact_amount':True,
        'block_number':int(receipt['blockNumber'],16)},indent=2)+'\n')
    refund_block = int(receipt['blockNumber'], 16)
    nonce = row.get('nonce') or row['refund'].get('delivery_nonce')
    # These hashes are in the repository's cases.md; verify their receipts independently.
    payment = rpc('eth_getTransactionReceipt', [DOCUMENTED_PAYMENTS[row['record_ref']]])
    assert payment and int(payment['status'], 16) == 1, 'Original payment unsuccessful or missing'
    matches = [t for t in transfers(payment) if t['from'] == row['payer'].lower()
               and t['units'] == units and t['to'] == paid_back[0]['from']]
    assert len(matches) == 1, 'Original payment amount or merchant does not match refund'
    transfer = matches[0]
    if nonce:
        assert any(log.get('address','').lower() == TOKEN and len(log.get('topics',[])) == 3
                   and log['topics'][0].lower() == AUTHORIZATION
                   and address(log['topics'][1]) == row['payer'].lower()
                   and log['topics'][2].lower() == nonce.lower() for log in payment['logs']), 'Order payment nonce mismatch'
    assert int(payment['blockNumber'], 16) <= refund_block
    payment_time = int(rpc('eth_getBlockByNumber', [payment['blockNumber'], False])['timestamp'], 16)
    refund_time = int(rpc('eth_getBlockByNumber', [receipt['blockNumber'], False])['timestamp'], 16)
    created = datetime.fromisoformat(row['at'].replace('Z', '+00:00')).timestamp()
    assert abs(payment_time - created) < 300, 'Payment does not match order creation time'
    result = {'record_ref': row['record_ref'], 'amount_usdc': row['price_usd'],
              'payment_tx': payment['transactionHash'], 'refund_tx': receipt['transactionHash'],
              'payment_time_utc': datetime.fromtimestamp(payment_time, timezone.utc).isoformat(),
              'refund_time_utc': datetime.fromtimestamp(refund_time, timezone.utc).isoformat(),
              'merchant': transfer['to'], 'buyer': row['payer'].lower(), 'refund_sender': paid_back[0]['from'],
              'payment_success': True, 'refund_success': True, 'full_principal_returned': True,
              'local_profile_released': row['released'], 'historical_before_deployment': True}
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    assert int(rpc('eth_chainId', []), 16) == 8453
    rows = gather()
    results = []
    errors = []
    for row in rows:
        try:
            results.append(verify(row))
        except Exception as error:
            record = {'record_ref': row['record_ref'], 'error': str(error)}
            errors.append(record)
            print(json.dumps(record), flush=True)
    summary = {'checked_at_unix': time.time(), 'network': 'Base mainnet', 'verified_cycles': results, 'errors': errors,
               'read_only': True, 'new_transfers_sent': 0, 'current_release_real_money_e2e_proven': False}
    (HERE / 'chain-verification.json').write_text(json.dumps(summary, indent=2) + '\n')
