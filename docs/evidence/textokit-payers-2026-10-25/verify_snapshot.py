"""Independent arithmetic/coverage check of captured public evidence; no imports from HISTOR."""

from collections import Counter, defaultdict
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
TOKEN = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
EVENT = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


def main():
    ledger = json.loads((ROOT / 'receipts.json').read_text())
    chain = json.loads((ROOT / 'chain.json').read_text())
    report = json.loads((ROOT / 'payers.json').read_text())
    external = [r for r in ledger['sales'] if r['ownWallet'] is False]
    assert len(ledger['sales']) == 80 and len(external) == 24
    assert len({r['payer'].lower() for r in external}) == 5
    assert sum(int(r['amountAtomic']) for r in external) == 55_000
    window = chain['window']
    ranges = sorted((int(r['params'][0]['fromBlock'], 16), int(r['params'][0]['toBlock'], 16))
                    for r in chain['rpc_reads'] if r['method'] == 'eth_getLogs' and r['ok'])
    assert len(ranges) == 605 and ranges[0][0] == window['from_block']
    assert ranges[-1][1] == window['to_block']
    assert all(ranges[i][0] == ranges[i - 1][1] + 1 for i in range(1, len(ranges)))
    assert window['complete'] and not window['failed_ranges']
    assert len(chain['logs']) == 23_254
    assert all(r['ok'] for r in chain['rpc_reads']) and len(chain['rpc_reads']) == 634
    groups = defaultdict(list)
    seen = set()
    zero = 0
    for log in chain['logs']:
        assert log['address'].lower() == TOKEN and log['topics'][0].lower() == EVENT
        assert window['from_block'] <= int(log['blockNumber'], 16) <= window['to_block']
        assert not log.get('removed')
        key = log['transactionHash'].lower(), int(log['logIndex'], 16)
        assert key not in seen
        seen.add(key)
        payer = '0x' + log['topics'][1][-40:].lower()
        recipient = '0x' + log['topics'][2][-40:].lower()
        amount = int(log['data'], 16)
        zero += amount == 0
        if amount > 0 and payer != recipient:
            groups[payer].append((recipient, amount))
    assert zero == 2
    checked = {r['transaction']: r['receipt'] for r in chain['settlements']}
    used = set()
    for sale in external:
        receipt = checked[sale['transaction']]
        assert receipt['status'] == '0x1' and receipt['transactionHash'].lower() == sale['transaction'].lower()
        found = []
        for log in receipt['logs']:
            if log['address'].lower() != TOKEN or log['topics'][0].lower() != EVENT:
                continue
            if ('0x' + log['topics'][1][-40:].lower() == sale['payer'].lower()
                    and '0x' + log['topics'][2][-40:].lower() == ledger['seller'].lower()
                    and int(log['data'], 16) == int(sale['amountAtomic'])):
                found.append((sale['transaction'], log['logIndex']))
        assert len(found) == 1 and found[0] not in used
        used.add(found[0])
    for payer in report['payers']:
        if payer['ownership'] != 'seller-reported-external':
            continue
        activity = groups[payer['payer']]
        recipients = Counter(to for to, _ in activity)
        assert payer['chain_activity']['transfers'] == len(activity)
        assert payer['chain_activity']['recipients'] == len(recipients)
        assert payer['chain_activity']['singleton_recipients'] == sum(n == 1 for n in recipients.values())
        assert payer['chain_activity']['small_transfers'] == sum(amount <= 10_000 for _, amount in activity)
        assert payer['settlements_verified'] == payer['sales']
    assert report['summary']['external_verified_amount_atomic'] == 55_000
    result = {'ok': True, 'external_payments': 24, 'verified_exact_transfers': len(used),
              'external_amount_atomic': 55_000, 'complete_ranges': len(ranges),
              'raw_events': len(chain['logs']), 'zero_events_excluded': zero,
              'independent_of_histor_reducer': True}
    (ROOT / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
