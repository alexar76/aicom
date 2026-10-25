"""Read-only check that both recorded Base receipts remain canonical and finalized."""
from datetime import datetime, timezone
import json
from pathlib import Path

from verify_chain import Rpc

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / 'verification-summary.json').read_text())
    rpc = Rpc()
    try:
        assert int(rpc.call('eth_chainId', []), 16) == 8453
        finalized = rpc.call('eth_getBlockByNumber', ['finalized', False])
        assert finalized and finalized.get('hash')
        finalized_height = int(finalized['number'], 16)
        receipts = {}
        for name in ('payment', 'refund'):
            tx = summary[name + '_tx']
            receipt = rpc.call('eth_getTransactionReceipt', [tx])
            assert receipt and receipt['transactionHash'].lower() == tx.lower()
            assert int(receipt['status'], 16) == 1
            block = rpc.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
            assert block and block['hash'] == receipt['blockHash']
            height = int(receipt['blockNumber'], 16)
            assert height <= finalized_height, name + ' is not finalized yet'
            receipts[name] = {'tx': tx, 'block': height, 'block_hash': block['hash'],
                              'success': True, 'canonical': True, 'finalized': True}
        # Re-read the exact finalized checkpoint to detect inconsistent providers.
        checkpoint = rpc.call('eth_getBlockByNumber', [finalized['number'], False])
        assert checkpoint['hash'] == finalized['hash']
        result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                  'chain_id': 8453, 'finality_tag': 'finalized',
                  'finalized_block': finalized_height, 'finalized_hash': finalized['hash'],
                  'transactions': receipts, 'both_finalized': True,
                  'new_transfers_sent': 0}
        (HERE / 'l1-finality-verification.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        rpc.close()


if __name__ == '__main__':
    main()
