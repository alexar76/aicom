"""Failure injection for the evidence writer; no network or money movement."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_finality


class FinalityEvidenceTests(unittest.TestCase):
    def exercise(self, *, finalized=110, wrong_hash=False, reverted=False):
        class FakeRpc:
            def call(self, method, params):
                if method == 'eth_chainId':
                    return hex(8453)
                if method == 'eth_getTransactionReceipt':
                    return {'transactionHash': params[0], 'status': '0x0' if reverted else '0x1',
                            'blockNumber': hex(100), 'blockHash': 'canonical'}
                if method == 'eth_getBlockByNumber':
                    height = finalized if params[0] == 'finalized' else int(params[0], 16)
                    return {'number': hex(height), 'hash': 'other' if wrong_hash and height == 100 else 'canonical'}
                raise AssertionError('Unexpected RPC method: ' + method)

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            here = Path(tmp)
            (here / 'verification-summary.json').write_text(json.dumps({'payment_tx': 'payment', 'refund_tx': 'refund'}))
            result = here / 'l1-finality-verification.json'
            with patch.object(verify_finality, 'HERE', here), patch.object(verify_finality, 'Rpc', FakeRpc), contextlib.redirect_stdout(io.StringIO()):
                if finalized < 100 or wrong_hash or reverted:
                    with self.assertRaises(AssertionError):
                        verify_finality.main()
                    self.assertFalse(result.exists(), 'A failed check must not write positive finality evidence')
                else:
                    verify_finality.main()
                    self.assertTrue(json.loads(result.read_text())['both_finalized'])

    def test_finalized_success(self):
        self.exercise()

    def test_confirmed_but_not_finalized_rejected(self):
        self.exercise(finalized=99)

    def test_noncanonical_receipt_rejected(self):
        self.exercise(wrong_hash=True)

    def test_reverted_transaction_rejected(self):
        self.exercise(reverted=True)


if __name__ == '__main__':
    unittest.main()
