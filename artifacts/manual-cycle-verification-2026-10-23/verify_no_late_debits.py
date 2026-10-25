"""Read all USDC debits for both test wallets from payment through current head."""
from decimal import Decimal
import json
from pathlib import Path
import time

from verify_chain import Rpc, TOKEN, TRANSFER, BALANCE_OF, transfers

HERE=Path(__file__).resolve().parent
summary=json.loads((HERE/'verification-summary.json').read_text())
production=json.loads((HERE/'production-evidence.json').read_text())
payer=production['order']['payer'].lower()
merchant=production['merchant'].lower()
rpc=Rpc()
try:
    start=summary['finality']['payment_block']-1
    latest=rpc.call('eth_getBlockByNumber',['latest',False])
    end=int(latest['number'],16)
    events=[]
    for lo in range(start,end+1,40):
        hi=min(end,lo+39)
        logs=rpc.call('eth_getLogs',[{'address':TOKEN,'fromBlock':hex(lo),'toBlock':hex(hi),
                                     'topics':[TRANSFER,['0x'+payer[2:].rjust(64,'0'),'0x'+merchant[2:].rjust(64,'0')]]}])
        events.extend(transfers(logs))
        print(json.dumps({'scan_from':lo,'scan_to':hi,'outgoing_transfers_found':len(events)}),flush=True)
    expected={summary['payment_tx'].lower(),summary['refund_tx'].lower()}
    assert len(events)==2 and {x['transaction'].lower() for x in events}==expected
    assert all(x['units']==310000 for x in events)
    balances={}
    for name,wallet in [('buyer',payer),('merchant',merchant)]:
        units=int(rpc.call('eth_call',[{'to':TOKEN,'data':BALANCE_OF+wallet[2:].rjust(64,'0')},latest['number']]),16)
        eth=int(rpc.call('eth_getBalance',[wallet,latest['number']]),16)
        balances[name]={'usdc_units':units,'eth_wei':eth}
        assert balances[name]==summary['balances'][name]['before']
    canonical=rpc.call('eth_getBlockByNumber',[latest['number'],False])
    assert canonical['hash']==latest['hash']
    finalized=rpc.call('eth_getBlockByNumber',['finalized',False])
    result={'checked_at_unix':time.time(),'from_block':start,'through_block':end,
            'from_test_to_head_seconds':int(latest['timestamp'],16)-int(__import__('datetime').datetime.fromisoformat(summary['payment_time_utc']).timestamp()),
            'outgoing_usdc_events':events,'current_balances':balances,'only_original_payment_and_refund':True,
            'no_late_debits':True,'balances_still_restored':True,
            'both_transactions_finalized':int(finalized['number'],16)>=summary['finality']['refund_block'],
            'finalized_block':int(finalized['number'],16),'new_transfers_sent':0}
    (HERE/'post-refund-monitor-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'no_late_debits':True,'balances_still_restored':True,'both_finalized':result['both_transactions_finalized'],
                      'checked_blocks':end-start+1,'seconds_since_payment':result['from_test_to_head_seconds']}),flush=True)
finally:
    rpc.close()
