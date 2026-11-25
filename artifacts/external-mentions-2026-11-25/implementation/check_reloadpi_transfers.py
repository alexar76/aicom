"""Validate the recorded Base USDC logs and optionally check a supplied one-order mapping."""
import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

USDC_BASE = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
HEX_WORD = re.compile(r'0x[0-9a-f]{64}')
EVIDENCE = Path(__file__).with_name('reloadpi-base-evidence.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def transfer(capture):
    receipt, block = capture['receipt'], capture['block']
    tx_hash = receipt['transactionHash']
    require(HEX_WORD.fullmatch(tx_hash) is not None and receipt['status'] == '0x1', 'Invalid receipt')
    require((receipt['blockHash'], receipt['blockNumber']) == (block['blockHash'], block['number']),
            f'{tx_hash}: block metadata does not match receipt')
    matches = [log for log in receipt['logs']
               if log['address'].lower() == USDC_BASE and log['topics'][:1] == [TRANSFER]]
    require(len(matches) == 1, f'{tx_hash}: expected exactly one native USDC Transfer')
    log = matches[0]
    require(log['transactionHash'] == tx_hash and log['blockHash'] == receipt['blockHash']
            and log['blockNumber'] == receipt['blockNumber'] and not log.get('removed'),
            f'{tx_hash}: log does not belong to the receipt')
    topics = log['topics']
    require(len(topics) == 3 and all(re.fullmatch(r'0x0{24}[0-9a-f]{40}', t) for t in topics[1:])
            and HEX_WORD.fullmatch(log['data']) is not None, f'{tx_hash}: invalid Transfer ABI fields')
    return {'tx_hash': tx_hash, 'from': '0x' + topics[1][-40:], 'to': '0x' + topics[2][-40:],
            'amount_atomic': int(log['data'], 16),
            'block_time': datetime.fromtimestamp(int(block['timestamp'], 16), tz=timezone.utc)}


def check_order(order, payment, refunds):
    require(isinstance(order['order_id'], str) and order['order_id'].strip(), 'Order ID is required')
    require(order['state'] == 'FULFILLMENT_FAILED', 'Expected FULFILLMENT_FAILED from the operator')
    require(order['payment_tx_hash'].lower() == payment['tx_hash'], 'Payment is outside this evidence bundle')
    refund = next((r for r in refunds if r['tx_hash'] == order['refund_tx_hash'].lower()), None)
    require(refund is not None, 'Refund is outside this evidence bundle')
    failed_at = datetime.fromisoformat(order['failed_at'].replace('Z', '+00:00'))
    require(failed_at.tzinfo is not None, 'An explicit time zone is required')
    require(payment['block_time'] <= failed_at <= refund['block_time'], 'Status time falls outside the transfer window')
    return {'order_id': order['order_id'], 'association': 'operator-supplied mapping consistent with receipts',
            'failed_at': failed_at.astimezone(timezone.utc).isoformat(), 'refund_tx_hash': refund['tx_hash']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operator-order', type=Path, help='Redacted mapping provided by the vendor')
    args = parser.parse_args()
    evidence = json.loads(EVIDENCE.read_text())
    require(evidence['chain_id'] == 8453, 'Expected Base mainnet')
    captures = evidence['transactions']
    payment = transfer(captures[evidence['published_payment']])
    refunds = [transfer(captures[ref]) for ref in evidence['published_refunds']]
    hashes = {r['tx_hash'] for r in refunds}
    require(len(hashes) == len(refunds) == 3 and payment['tx_hash'] not in hashes, 'Expected three distinct refunds')
    require(payment['amount_atomic'] == 1_610_000, 'Unexpected payment amount')
    for r in refunds:
        require(r['from'] == payment['to'] and r['to'] == payment['from'], 'Unexpected refund direction')
        require(r['amount_atomic'] == payment['amount_atomic'], 'Unexpected refund amount')
        require(r['block_time'] > payment['block_time'], 'Refund precedes the published payment')
    total = sum(r['amount_atomic'] for r in refunds)
    output = {'chain_id': 8453, 'payouts_verified': len(refunds), 'usdc_per_payout': '1.61',
              'total_usdc': str(Decimal(total) / 1_000_000),
              'payment': payment, 'refunds': refunds, 'order_association': 'pending vendor status evidence'}
    if args.operator_order:
        output['order_association'] = check_order(json.loads(args.operator_order.read_text()), payment, refunds)
    print(json.dumps(output, indent=2, default=datetime.isoformat))


if __name__ == '__main__':
    try:
        main()
    except (KeyError, TypeError, ValueError) as e:
        raise SystemExit(str(e)) from e
